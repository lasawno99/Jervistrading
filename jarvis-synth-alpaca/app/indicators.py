"""Technical indicators used for risk-adaptive stop & target sizing.

Kept dependency-free (just pandas) and pure for easy pytest.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def atr(bars: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Average True Range — last value, expressed in the instrument's price units.

    Returns None if the bars frame is too short to compute a meaningful ATR.

    True Range for bar t = max(
        high_t - low_t,
        |high_t - close_{t-1}|,
        |low_t  - close_{t-1}|,
    )
    """
    needed_cols = {"high", "low", "close"}
    if not isinstance(bars, pd.DataFrame) or not needed_cols.issubset(bars.columns):
        return None
    if len(bars) < period + 1:
        return None

    df = bars[["high", "low", "close"]].astype(float).copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing (EMA with alpha = 1/period)
    val = tr.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def pip_size(instrument: str) -> float:
    """OANDA-style pip size — 0.01 for XAU/XAG and JPY pairs, 0.0001 elsewhere.

    Used to convert ATR (price units) into pips for the executor API.
    """
    inst = instrument.upper()
    if inst.startswith("XAU") or inst.startswith("XAG"):
        return 0.01
    if inst.endswith("JPY") or "_JPY" in inst:
        return 0.01
    return 0.0001


def atr_in_pips(bars: pd.DataFrame, instrument: str, period: int = 14) -> Optional[float]:
    a = atr(bars, period=period)
    if a is None:
        return None
    return a / pip_size(instrument)


def adaptive_sl_pct(
    bars: pd.DataFrame,
    multiplier: float = 1.5,
    floor_pct: float = 0.5,
    ceiling_pct: float = 8.0,
    period: int = 14,
) -> Optional[float]:
    """For non-FX assets (crypto, stocks) — SL distance as percent of last close.

    Returns clamp(multiplier × ATR(period) / last_close × 100, floor_pct, ceiling_pct)
    so the Alpaca executor's percent-of-price stop fits each asset's volatility.
    """
    a = atr(bars, period=period)
    if a is None or "close" not in bars.columns:
        return None
    last_close = float(bars["close"].iloc[-1])
    if last_close <= 0:
        return None
    pct = (multiplier * a / last_close) * 100.0
    return float(max(floor_pct, min(ceiling_pct, pct)))


def adaptive_sl_pips(
    bars: pd.DataFrame,
    instrument: str,
    multiplier: float = 1.5,
    floor_pips: float = 6.0,
    ceiling_pips: float = 80.0,
    period: int = 14,
) -> Optional[float]:
    """Compute a stop-loss distance in pips sized to instrument volatility.

    sl_pips = clamp(multiplier × ATR(period), floor_pips, ceiling_pips).
    Returns None if ATR can't be computed — caller should fall back to a default.
    """
    apips = atr_in_pips(bars, instrument, period=period)
    if apips is None:
        return None
    val = multiplier * apips
    return float(max(floor_pips, min(ceiling_pips, val)))
