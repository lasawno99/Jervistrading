"""Turn a Kronos prediction + recent history into a tradable signal."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Signal:
    instrument: str
    current_price: float
    mean_target: float
    upside_prob: float   # share of Monte-Carlo paths that closed above current
    vol_amp: float       # predicted realized vol / historical vol (ratio)
    direction: str       # "buy", "sell", "skip"
    confidence: str      # "high", "medium", "low"


def build_signal(
    instrument: str,
    history: pd.DataFrame,
    prediction: pd.DataFrame,
    upside_high: float,
    upside_low: float,
    max_vol_amp: float,
) -> Signal:
    current_price = float(history["close"].iloc[-1])
    mean_target = float(prediction["close"].mean())

    # upside_prob — if the predictor returns multiple samples they're averaged
    # already in `predict`; approximate probability from the direction of each
    # predicted step versus current price.
    up = (prediction["close"] > current_price).mean()
    upside_prob = float(up)

    # Realized vol ratio: predicted log-return stdev / historical log-return stdev
    hist_ret = history["close"].pct_change().dropna()
    pred_ret = prediction["close"].pct_change().dropna()
    hist_std = float(hist_ret.std()) if len(hist_ret) > 1 else 0.0
    pred_std = float(pred_ret.std()) if len(pred_ret) > 1 else 0.0
    vol_amp = (pred_std / hist_std) if hist_std > 0 else 1.0

    direction = "skip"
    confidence = "low"
    if vol_amp <= max_vol_amp:
        if upside_prob >= upside_high:
            direction = "buy"
            confidence = "high" if upside_prob >= upside_high + 0.1 else "medium"
        elif upside_prob <= upside_low:
            direction = "sell"
            confidence = "high" if upside_prob <= upside_low - 0.1 else "medium"

    return Signal(
        instrument=instrument,
        current_price=current_price,
        mean_target=mean_target,
        upside_prob=upside_prob,
        vol_amp=vol_amp,
        direction=direction,
        confidence=confidence,
    )


def format_signal(s: Signal) -> str:
    arrow = {"buy": "🟢 BUY", "sell": "🔴 SELL", "skip": "⚪ SKIP"}[s.direction]
    change_pct = (s.mean_target - s.current_price) / s.current_price * 100
    return (
        f"🔮 Kronos — {s.instrument}\n"
        f"{arrow} · confidence: {s.confidence}\n"
        f"Price: {s.current_price:.5f} → target: {s.mean_target:.5f} ({change_pct:+.2f}%)\n"
        f"Upside prob: {s.upside_prob:.0%} · Vol amp: {s.vol_amp:.2f}x"
    )
