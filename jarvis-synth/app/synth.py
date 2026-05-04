"""LAYER 4 — JARVIS synthesis.

Combines Tauric verdict + Kronos signal into a final decision with sizing.

Decision matrix (rough):

  Tauric \\ Kronos    | buy            | sell           | skip
  --------------------+---------------+---------------+-----
  BUY                | LONG  full     | HOLD          | LONG  half
  OVERWEIGHT         | LONG  half     | HOLD          | HOLD
  HOLD               | HOLD          | HOLD          | HOLD
  UNDERWEIGHT        | HOLD          | SHORT half    | HOLD
  SELL               | HOLD          | SHORT full    | SHORT half

"Half" = base_position_units / 2 (rounded down).
Confidence floor: if Tauric.confidence < 5 OR Kronos.confidence == "low", force HOLD.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import structlog

from app.signal import Signal as KronosSignal
from app.tauric import TauricVerdict

log = structlog.get_logger()


@dataclass
class FinalDecision:
    action: str      # LONG | SHORT | HOLD
    units: int       # 0 if HOLD
    reasoning: str   # human-readable summary
    tauric_verdict: str
    tauric_confidence: int
    kronos_direction: str
    kronos_confidence: str


def _kronos_dir(s: KronosSignal) -> str:
    return s.direction  # buy | sell | skip


_FULL = "full"
_HALF = "half"
_NONE = "none"


_MATRIX = {
    "BUY":         {"buy": _FULL, "sell": _NONE, "skip": _HALF},
    "OVERWEIGHT":  {"buy": _HALF, "sell": _NONE, "skip": _NONE},
    "HOLD":        {"buy": _NONE, "sell": _NONE, "skip": _NONE},
    "UNDERWEIGHT": {"buy": _NONE, "sell": _HALF, "skip": _NONE},
    "SELL":        {"buy": _NONE, "sell": _FULL, "skip": _HALF},
}


def synthesize(
    instrument: str,
    tauric: TauricVerdict,
    kronos: KronosSignal,
    base_units: int,
) -> FinalDecision:
    # Confidence floor
    if tauric.confidence < 5 or kronos.confidence == "low":
        return FinalDecision(
            action="HOLD",
            units=0,
            reasoning=(
                f"Confidence floor: Tauric={tauric.verdict}/{tauric.confidence}, "
                f"Kronos={kronos.direction}/{kronos.confidence}. "
                "At least one layer is below threshold — skip."
            ),
            tauric_verdict=tauric.verdict,
            tauric_confidence=tauric.confidence,
            kronos_direction=kronos.direction,
            kronos_confidence=kronos.confidence,
        )

    sizing = _MATRIX.get(tauric.verdict, {}).get(_kronos_dir(kronos), _NONE)
    if sizing == _NONE:
        action, units = "HOLD", 0
    elif sizing == _HALF:
        units = max(1, base_units // 2)
        if tauric.verdict in ("SELL", "UNDERWEIGHT"):
            action = "SHORT"
        else:
            action = "LONG"
    else:  # full
        units = base_units
        action = "LONG" if tauric.verdict in ("BUY", "OVERWEIGHT") else "SHORT"

    reasoning = (
        f"Tauric={tauric.verdict}/{tauric.confidence}, "
        f"Kronos={kronos.direction}/{kronos.confidence} (upside {kronos.upside_prob:.0%}, "
        f"vol_amp {kronos.vol_amp:.2f}x). Matrix → {sizing}. "
        f"Risk Manager: {tauric.risk_manager}"
    )
    return FinalDecision(
        action=action,
        units=units,
        reasoning=reasoning,
        tauric_verdict=tauric.verdict,
        tauric_confidence=tauric.confidence,
        kronos_direction=kronos.direction,
        kronos_confidence=kronos.confidence,
    )
