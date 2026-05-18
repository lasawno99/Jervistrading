"""Layer 0 — Pre-Tauric filters that lift win-rate by rejecting weak setups.

Three filters, each one cheap (no LLM call), all gate-style:
  1. ``mtf_trend_filter``       — Multi-timeframe EMA-20 slope agreement
  2. ``indicator_confluence``    — RSI + MACD + Bollinger Band alignment
  3. ``session_filter``          — Reject trades during low-liquidity windows

Each returns a (allowed: bool, reason: str, details: dict) tuple. The pipeline
calls all three; first ``allowed=False`` short-circuits to HOLD with structured
rationale so the cycle log records WHY each trade was rejected.

Inputs: a pandas DataFrame of OHLCV (must have ``close`` column) representing
the most recent bars (newest last). Multi-TF gets multiple frames.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reason: str
    details: Dict[str, object]


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    diffs = np.diff(close)
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _macd_hist(close: np.ndarray) -> float:
    if len(close) < 35:
        return 0.0
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    return float((macd - signal)[-1])


def _bb_position(close: np.ndarray, period: int = 20) -> float:
    """Return 0..1 — how far close is between BB lower (0) and upper (1)."""
    if len(close) < period:
        return 0.5
    window = close[-period:]
    mid = window.mean()
    std = window.std()
    if std == 0:
        return 0.5
    upper = mid + 2 * std
    lower = mid - 2 * std
    pos = (close[-1] - lower) / (upper - lower)
    return float(max(0.0, min(1.0, pos)))


# ---------- Filter 1: Multi-timeframe trend ----------

def mtf_trend_filter(
    proposed_direction: str,
    bars_by_timeframe: Dict[str, pd.DataFrame],
    min_agree: int = 2,
) -> FilterResult:
    """At least ``min_agree`` of the provided timeframes must agree on EMA-20 slope direction.

    proposed_direction: "LONG" or "SHORT"
    bars_by_timeframe: {"4H": df_4h, "1H": df_1h, "15M": df_15m}
    """
    if proposed_direction not in ("LONG", "SHORT"):
        return FilterResult(True, "n/a — hold", {})

    votes: Dict[str, str] = {}
    for tf, df in bars_by_timeframe.items():
        if df is None or len(df) < 22 or "close" not in df.columns:
            votes[tf] = "skip"
            continue
        closes = df["close"].to_numpy(dtype=float)
        ema = _ema(closes[-30:], 20)
        slope = ema[-1] - ema[-5]
        votes[tf] = "LONG" if slope > 0 else ("SHORT" if slope < 0 else "FLAT")

    agreeing = sum(1 for v in votes.values() if v == proposed_direction)
    allowed = agreeing >= min_agree
    return FilterResult(
        allowed=allowed,
        reason=(
            f"MTF trend OK ({agreeing}/{len(votes)} agree)" if allowed
            else f"MTF trend conflict ({agreeing}/{len(votes)} agree, need {min_agree})"
        ),
        details={"votes": votes, "proposed": proposed_direction, "min_agree": min_agree},
    )


# ---------- Filter 2: Indicator confluence ----------

def indicator_confluence(
    proposed_direction: str,
    bars: pd.DataFrame,
    min_indicators_aligned: int = 2,
) -> FilterResult:
    """RSI + MACD + BB-position must align with proposed direction.

    LONG-aligned:  RSI < 70 (not overbought), MACD hist > 0, BB pos < 0.85
    SHORT-aligned: RSI > 30 (not oversold),   MACD hist < 0, BB pos > 0.15

    Requires ``min_indicators_aligned`` of 3.
    """
    if proposed_direction not in ("LONG", "SHORT"):
        return FilterResult(True, "n/a — hold", {})
    if bars is None or len(bars) < 30 or "close" not in bars.columns:
        return FilterResult(True, "insufficient data — pass-through", {})

    closes = bars["close"].to_numpy(dtype=float)
    rsi = _rsi(closes)
    macd_h = _macd_hist(closes)
    bb_pos = _bb_position(closes)

    if proposed_direction == "LONG":
        # LONG needs uptrend momentum: RSI in trend zone (not extreme either way),
        # MACD histogram positive, price in upper half of BB range.
        votes = {
            "rsi": 45 <= rsi <= 75,
            "macd": macd_h > 0,
            "bb": bb_pos >= 0.40,
        }
    else:
        # SHORT needs downtrend momentum: RSI in trend zone,
        # MACD histogram negative, price in lower half of BB range.
        votes = {
            "rsi": 25 <= rsi <= 55,
            "macd": macd_h < 0,
            "bb": bb_pos <= 0.60,
        }
    aligned = sum(1 for v in votes.values() if v)
    allowed = aligned >= min_indicators_aligned
    return FilterResult(
        allowed=allowed,
        reason=(
            f"Indicators aligned ({aligned}/3)" if allowed
            else f"Indicators conflict ({aligned}/3 aligned, need {min_indicators_aligned})"
        ),
        details={
            "rsi": round(rsi, 2), "macd_hist": round(macd_h, 6), "bb_pos": round(bb_pos, 3),
            "votes": votes, "proposed": proposed_direction,
        },
    )


# ---------- Filter 3: Session / volatility window ----------

# UTC hour windows when forex liquidity is strong (London 8-12, NY 13-17, overlap 13-16)
FOREX_GOOD_HOURS = set(range(8, 18))
# Crypto is 24/7 but Sunday UTC tends to be lowest-volume
CRYPTO_BAD_HOURS_WEEKDAY = {6: set(range(0, 4))}  # Sunday 00-04 UTC


def session_filter(
    instrument: str,
    asset_kind: str = "auto",
    now: Optional[datetime] = None,
) -> FilterResult:
    """Reject trades during low-liquidity sessions.

    asset_kind: "forex" | "crypto" | "stock" | "auto"
    For "stock", US RTH is enforced upstream by the broker — we just pass-through.
    """
    now = now or datetime.now(timezone.utc)
    weekday = now.weekday()  # Mon=0, Sun=6
    hour = now.hour

    kind = asset_kind
    if kind == "auto":
        if "/" in instrument:
            kind = "crypto"
        elif "_" in instrument:
            kind = "forex"
        else:
            kind = "stock"

    if kind == "forex":
        # Skip weekends entirely + skip Asia overnight chop
        if weekday in (5, 6):  # Sat, Sun
            return FilterResult(False, "forex market closed (weekend)", {"weekday": weekday})
        if hour not in FOREX_GOOD_HOURS:
            return FilterResult(
                False,
                f"forex low-liquidity hour (UTC {hour:02d}:00, prefer 08-17)",
                {"hour": hour, "good_hours": sorted(FOREX_GOOD_HOURS)},
            )
        return FilterResult(True, f"forex session OK (UTC {hour:02d}:00)", {"hour": hour})

    if kind == "crypto":
        bad = CRYPTO_BAD_HOURS_WEEKDAY.get(weekday, set())
        if hour in bad:
            return FilterResult(False, f"crypto low-volume window (Sun {hour:02d} UTC)", {"hour": hour})
        return FilterResult(True, "crypto 24/7 session OK", {"hour": hour, "weekday": weekday})

    # Stock — pass through, broker enforces RTH
    return FilterResult(True, "stock session — broker enforces RTH", {"asset_kind": "stock"})


# ---------- Combined runner ----------

def run_pre_tauric_filters(
    instrument: str,
    proposed_direction: str,
    primary_bars: pd.DataFrame,
    mtf_bars: Optional[Dict[str, pd.DataFrame]] = None,
    asset_kind: str = "auto",
) -> Tuple[bool, List[Dict[str, object]]]:
    """Run all three filters in order. Returns (overall_allowed, [filter_results_as_dict])."""
    results: List[FilterResult] = []
    if mtf_bars:
        results.append(mtf_trend_filter(proposed_direction, mtf_bars))
    results.append(indicator_confluence(proposed_direction, primary_bars))
    results.append(session_filter(instrument, asset_kind=asset_kind))

    overall = all(r.allowed for r in results)
    return overall, [
        {"name": name, "allowed": r.allowed, "reason": r.reason, "details": r.details}
        for name, r in zip(
            (["mtf_trend"] if mtf_bars else []) + ["indicators", "session"],
            results,
        )
    ]
