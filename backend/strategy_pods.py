"""Three independent strategy pods + 2-of-3 ensemble voter.

Each pod consumes the SAME inputs (numpy arrays of closes/highs/lows up to bar i)
and returns the SAME shape:

    {"action": "LONG"|"SHORT"|"HOLD", "confidence": int 1..10, "reason": str}

This shape lets `ensemble_vote()` combine outputs in O(pods) without any
per-pod special-casing.

Pods:
  • Pod A — Tauric + Kronos surrogate (delegates to backtest_engine.synthesize)
  • Pod B — Mean-Reversion (RSI + Bollinger Bands, gated by LOW volatility)
  • Pod C — Momentum / Breakout (Donchian channels + ADX, gated by HIGH volatility)

The pods are intentionally pure-numpy (no I/O, no LLM) so they can be
asyncio.gather'd with a 30s timeout each — see `vote_concurrently()`.

DO NOT modify Pod A's underlying logic (kronos_surrogate / synthesize /
tauric_deterministic) — Pod A is a thin adapter only, by design.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import numpy as np

log = logging.getLogger("strategy_pods")


# ---------- shared indicators (kept self-contained for parity) --------------

def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = np.diff(closes)
    gains = np.where(diffs > 0, diffs, 0.0)[-period:]
    losses = np.where(diffs < 0, -diffs, 0.0)[-period:]
    avg_g = gains.mean() if len(gains) else 0.0
    avg_l = losses.mean() if len(losses) else 0.0
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return float(100.0 - (100.0 / (1.0 + rs)))


def _bbands(closes: np.ndarray, period: int = 20, k: float = 2.0):
    if len(closes) < period:
        m = float(closes[-1])
        return m, m, m
    window = closes[-period:]
    mid = float(np.mean(window))
    sd = float(np.std(window))
    return mid - k * sd, mid, mid + k * sd


def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Average Directional Index — quick numpy approximation (Wilder's smoothing)."""
    n = len(closes)
    if n < period * 2 + 1:
        return 0.0
    up = highs[1:] - highs[:-1]
    dn = lows[:-1] - lows[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    # Wilder smoothing (RMA)
    def _rma(x: np.ndarray) -> float:
        val = float(x[:period].mean())
        for v in x[period:]:
            val = (val * (period - 1) + float(v)) / period
        return val
    atr = _rma(tr)
    if atr <= 0:
        return 0.0
    plus_di = 100.0 * _rma(plus_dm) / atr
    minus_di = 100.0 * _rma(minus_dm) / atr
    denom = plus_di + minus_di
    if denom <= 0:
        return 0.0
    dx = 100.0 * abs(plus_di - minus_di) / denom
    return float(dx)


def _vol_amp(closes: np.ndarray) -> float:
    """Same volatility ratio used by Pod A's Kronos surrogate (recent vs older std).

    Re-implemented here so Pods B/C see the SAME regime tag as Pod A.
    """
    if len(closes) < 100:
        if len(closes) < 25:
            return 1.0
        # Fall back to a self-vs-self ratio so we don't fake "high vol" on thin data.
        return 1.0
    recent = closes[-20:]
    older = closes[-100:-20]
    r_std = float(np.std(np.diff(recent) / recent[:-1])) if len(recent) > 5 else 0.0
    o_std = float(np.std(np.diff(older) / older[:-1])) if len(older) > 5 else r_std
    return (r_std / o_std) if o_std > 0 else 1.0


# ---------- Pod A: Tauric + Kronos (thin adapter — no logic changes) --------

def pod_a_tauric_kronos(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    *,
    tauric_floor: int = 8,
    upside_high: float = 0.70,
    upside_low: float = 0.30,
    base_units: int = 1000,
) -> Dict[str, Any]:
    """Adapter — calls existing Kronos surrogate + deterministic Tauric + synth.

    This DOES NOT change Pod A logic — it just packages the output into the
    standard pod-vote shape so `ensemble_vote()` can consume it uniformly.
    """
    # Lazy import to avoid a hard cycle (backtest_engine imports this module too).
    import backtest_engine as bt

    kronos = bt.kronos_surrogate(
        closes, highs, lows,
        upside_high=upside_high, upside_low=upside_low,
    )
    if kronos["direction"] == "skip":
        return {"action": "HOLD", "confidence": 5, "reason": "kronos skip"}

    vote = bt.tauric_deterministic(kronos)
    decision = bt.synthesize(
        vote["verdict"], vote["confidence"], kronos, base_units,
        tauric_floor=tauric_floor,
    )
    if decision["action"] == "HOLD":
        return {"action": "HOLD", "confidence": vote["confidence"], "reason": decision["reason"]}
    return {
        "action": decision["action"],  # LONG | SHORT
        "confidence": int(vote["confidence"]),
        "reason": f"podA:{vote['verdict']}/{vote['confidence']}+{kronos['direction']}",
        # extras Pod A also computes — kept so engine can reuse them
        "kronos": kronos,
        "tauric_verdict": vote["verdict"],
    }


# ---------- Pod B: Mean-Reversion (low-vol regimes only) --------------------

def pod_b_mean_reversion(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    *,
    rsi_period: int = 14,
    bb_period: int = 20,
    bb_k: float = 2.0,
    low_vol_threshold: float = 1.10,  # vol_amp < 1.10 → market is calm
) -> Dict[str, Any]:
    """RSI + Bollinger fade — ONLY votes in calm markets.

    Long when RSI < 30 AND price < lower band → expect reversion up.
    Short when RSI > 70 AND price > upper band → expect reversion down.
    Refuses to vote (HOLD) if volatility is elevated (regime mismatch).
    """
    if len(closes) < max(bb_period, rsi_period) + 5:
        return {"action": "HOLD", "confidence": 4, "reason": "podB:warmup"}

    vol = _vol_amp(closes)
    if vol > low_vol_threshold:
        return {"action": "HOLD", "confidence": 4, "reason": f"podB:regime-mismatch vol={vol:.2f}"}

    rsi = _rsi(closes, rsi_period)
    lo, mid, hi = _bbands(closes, bb_period, bb_k)
    price = float(closes[-1])

    # Confidence scales with how stretched RSI is, capped 1..10.
    def _conf_from(rsi_dev: float, band_dev_pct: float) -> int:
        # rsi_dev in [0..40], band_dev_pct in [0..0.05]+
        s = (rsi_dev / 40.0) * 0.6 + min(1.0, band_dev_pct / 0.03) * 0.4
        return int(round(max(1, min(10, s * 10))))

    if rsi < 30 and price < lo:
        band_dev = (lo - price) / max(1e-9, lo)
        return {
            "action": "LONG",
            "confidence": _conf_from(30 - rsi, band_dev),
            "reason": f"podB:RSI={rsi:.1f}<30 price<lowBB ({band_dev:.2%})",
        }
    if rsi > 70 and price > hi:
        band_dev = (price - hi) / max(1e-9, hi)
        return {
            "action": "SHORT",
            "confidence": _conf_from(rsi - 70, band_dev),
            "reason": f"podB:RSI={rsi:.1f}>70 price>highBB ({band_dev:.2%})",
        }
    return {"action": "HOLD", "confidence": 5,
            "reason": f"podB:no-edge RSI={rsi:.1f} vol={vol:.2f}"}


# ---------- Pod C: Momentum / Breakout (high-vol regimes only) --------------

def pod_c_momentum_breakout(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    *,
    donchian_period: int = 20,
    adx_period: int = 14,
    adx_floor: float = 22.0,
    high_vol_threshold: float = 0.95,  # vol_amp >= 0.95 → enough movement to ride
) -> Dict[str, Any]:
    """Donchian breakout filtered by ADX trend strength.

    Long when close pierces the 20-period high AND ADX >= floor.
    Short when close pierces the 20-period low AND ADX >= floor.
    Refuses to vote in chop (low ADX) or thin volatility.
    """
    if len(closes) < max(donchian_period, adx_period * 2) + 5:
        return {"action": "HOLD", "confidence": 4, "reason": "podC:warmup"}

    vol = _vol_amp(closes)
    if vol < high_vol_threshold:
        return {"action": "HOLD", "confidence": 4, "reason": f"podC:regime-mismatch vol={vol:.2f}"}

    don_hi = float(np.max(highs[-(donchian_period + 1):-1]))  # prior N bars, excludes current
    don_lo = float(np.min(lows[-(donchian_period + 1):-1]))
    adx = _adx(highs, lows, closes, period=adx_period)
    price = float(closes[-1])

    if adx < adx_floor:
        return {"action": "HOLD", "confidence": 5,
                "reason": f"podC:no-trend ADX={adx:.1f}<{adx_floor}"}

    def _conf_from(adx_v: float, break_pct: float) -> int:
        s = min(1.0, max(0.0, (adx_v - adx_floor) / 25.0)) * 0.5 + \
            min(1.0, break_pct / 0.01) * 0.5
        return int(round(max(1, min(10, 4 + s * 6))))

    if price > don_hi:
        break_pct = (price - don_hi) / max(1e-9, don_hi)
        return {
            "action": "LONG",
            "confidence": _conf_from(adx, break_pct),
            "reason": f"podC:break ADX={adx:.1f} >{donchian_period}H ({break_pct:.2%})",
        }
    if price < don_lo:
        break_pct = (don_lo - price) / max(1e-9, don_lo)
        return {
            "action": "SHORT",
            "confidence": _conf_from(adx, break_pct),
            "reason": f"podC:break ADX={adx:.1f} <{donchian_period}L ({break_pct:.2%})",
        }
    return {"action": "HOLD", "confidence": 5,
            "reason": f"podC:inside ADX={adx:.1f} vol={vol:.2f}"}


# ---------- 2-of-3 ensemble vote --------------------------------------------

def ensemble_vote(votes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine 3 pod votes via 2-of-3 directional agreement.

    Trade only when ≥2 pods agree on LONG or SHORT. Otherwise HOLD.
    Final confidence = mean of agreeing pods' confidences (rounded).
    """
    longs = [v for v in votes if v.get("action") == "LONG"]
    shorts = [v for v in votes if v.get("action") == "SHORT"]

    if len(longs) >= 2 and len(longs) > len(shorts):
        conf = int(round(sum(v["confidence"] for v in longs) / len(longs)))
        return {
            "action": "LONG",
            "confidence": max(1, min(10, conf)),
            "agreeing_pods": len(longs),
            "reasons": [v.get("reason", "") for v in longs],
            "all_votes": [v.get("action") for v in votes],
        }
    if len(shorts) >= 2 and len(shorts) > len(longs):
        conf = int(round(sum(v["confidence"] for v in shorts) / len(shorts)))
        return {
            "action": "SHORT",
            "confidence": max(1, min(10, conf)),
            "agreeing_pods": len(shorts),
            "reasons": [v.get("reason", "") for v in shorts],
            "all_votes": [v.get("action") for v in votes],
        }
    return {
        "action": "HOLD",
        "confidence": 5,
        "agreeing_pods": max(len(longs), len(shorts)),
        "reasons": [v.get("reason", "") for v in votes],
        "all_votes": [v.get("action") for v in votes],
    }


# ---------- Concurrent pod execution with timeout ---------------------------

async def vote_concurrently(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    *,
    pod_a_kwargs: Optional[Dict[str, Any]] = None,
    pod_b_kwargs: Optional[Dict[str, Any]] = None,
    pod_c_kwargs: Optional[Dict[str, Any]] = None,
    per_pod_timeout_s: float = 30.0,
) -> Dict[str, Any]:
    """Run all three pods concurrently with a per-pod timeout, then ensemble.

    A pod that times out or raises is recorded as HOLD with reason="error" so
    it can never cast a directional vote it didn't actually produce.

    Returns:
        {
          "ensemble": <ensemble_vote result>,
          "pods": {"A": ..., "B": ..., "C": ...},
        }
    """
    a_kw = pod_a_kwargs or {}
    b_kw = pod_b_kwargs or {}
    c_kw = pod_c_kwargs or {}

    async def _safe(name: str, fn, kwargs):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, closes, highs, lows, **kwargs),
                timeout=per_pod_timeout_s,
            )
        except asyncio.TimeoutError:
            log.warning("pod %s timed out", name)
            return {"action": "HOLD", "confidence": 1, "reason": f"pod{name}:timeout"}
        except Exception as e:
            log.warning("pod %s errored: %s", name, e)
            return {"action": "HOLD", "confidence": 1, "reason": f"pod{name}:error:{e}"}

    a, b, c = await asyncio.gather(
        _safe("A", pod_a_tauric_kronos, a_kw),
        _safe("B", pod_b_mean_reversion, b_kw),
        _safe("C", pod_c_momentum_breakout, c_kw),
    )
    return {
        "ensemble": ensemble_vote([a, b, c]),
        "pods": {"A": a, "B": b, "C": c},
    }
