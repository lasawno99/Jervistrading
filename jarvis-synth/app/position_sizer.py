"""Position sizer — turns the synth matrix's base unit count into a final size
that respects conviction (Tauric confidence) and volatility (Kronos vol_amp).

Pure function. Both inputs come from layers we already compute, so this is a
trivial slot-in between synth() and executor.execute().
"""
from __future__ import annotations

from dataclasses import dataclass


# Tauric confidence multipliers — 7 is the floor (already gated in synth).
# Above 7 we scale up linearly so high-conviction trades carry more capital.
_CONVICTION_MULT = {
    7: 1.0,
    8: 1.3,
    9: 1.6,
    10: 2.0,
}


# Volatility regimes — Kronos blocks anything > 2.0x. We shrink between 1.3-2.0x
# so trades in choppy/expanding-vol periods carry half size.
_VOL_CHOP_THRESHOLD = 1.3
_VOL_BLOCK_THRESHOLD = 2.0


@dataclass(frozen=True)
class SizingResult:
    final_units: int
    base_units: int
    conviction_mult: float
    vol_mult: float
    reason: str


def conviction_multiplier(confidence: int) -> float:
    """Tauric confidence -> position multiplier. Clamps to known buckets."""
    if confidence <= 7:
        return _CONVICTION_MULT[7]
    if confidence >= 10:
        return _CONVICTION_MULT[10]
    return _CONVICTION_MULT[int(confidence)]


def volatility_multiplier(vol_amp: float) -> float:
    """Kronos vol_amp -> sizing dampener.

    - vol_amp ≤ 1.3      → 1.0 (calm; full size)
    - 1.3 < vol_amp < 2.0 → 0.5 (choppy/expanding; half size)
    - vol_amp ≥ 2.0      → 0.0 (synth.py should already block — defense-in-depth)
    """
    if vol_amp is None or vol_amp <= _VOL_CHOP_THRESHOLD:
        return 1.0
    if vol_amp >= _VOL_BLOCK_THRESHOLD:
        return 0.0
    return 0.5


def size(
    base_units: int,
    tauric_confidence: int,
    kronos_vol_amp: float,
    *,
    min_units: int = 1,
) -> SizingResult:
    """Return the final unit count after applying conviction + volatility scaling.

    Always rounds to int and enforces min_units so we never accidentally place
    a 0-unit order. If base_units is already 0 (HOLD), we return 0 untouched.
    """
    if base_units <= 0:
        return SizingResult(
            final_units=0,
            base_units=int(base_units),
            conviction_mult=1.0,
            vol_mult=1.0,
            reason="base=0 (HOLD)",
        )

    c_mult = conviction_multiplier(tauric_confidence)
    v_mult = volatility_multiplier(kronos_vol_amp)
    raw = base_units * c_mult * v_mult

    if v_mult == 0.0:
        return SizingResult(
            final_units=0,
            base_units=int(base_units),
            conviction_mult=c_mult,
            vol_mult=0.0,
            reason=f"vol_amp {kronos_vol_amp:.2f}x ≥ {_VOL_BLOCK_THRESHOLD} — vol-blocked",
        )

    final = max(min_units, int(round(raw)))
    reason = (
        f"base {base_units} × conviction {c_mult:.2f}x "
        f"(Tauric {tauric_confidence}/10) × vol {v_mult:.2f}x "
        f"(amp {kronos_vol_amp:.2f}x) → {final}u"
    )
    return SizingResult(
        final_units=final,
        base_units=int(base_units),
        conviction_mult=c_mult,
        vol_mult=v_mult,
        reason=reason,
    )
