"""Tests for position_sizer — pure function, no I/O."""
from app.position_sizer import (
    conviction_multiplier,
    size,
    volatility_multiplier,
)


# ----------------- conviction_multiplier ------------------------------------

def test_conviction_floor_at_7():
    assert conviction_multiplier(7) == 1.0


def test_conviction_8_is_1_3x():
    assert conviction_multiplier(8) == 1.3


def test_conviction_9_is_1_6x():
    assert conviction_multiplier(9) == 1.6


def test_conviction_10_caps_at_2x():
    assert conviction_multiplier(10) == 2.0


def test_conviction_below_floor_treated_as_7():
    # synth.py already gates < 7 — but be defensive.
    assert conviction_multiplier(5) == 1.0
    assert conviction_multiplier(0) == 1.0


def test_conviction_above_10_caps():
    assert conviction_multiplier(15) == 2.0


# ----------------- volatility_multiplier ------------------------------------

def test_vol_calm_below_1_3_full_size():
    assert volatility_multiplier(0.8) == 1.0
    assert volatility_multiplier(1.0) == 1.0
    assert volatility_multiplier(1.3) == 1.0  # equal-to threshold = calm


def test_vol_chop_half_size():
    assert volatility_multiplier(1.4) == 0.5
    assert volatility_multiplier(1.7) == 0.5
    assert volatility_multiplier(1.99) == 0.5


def test_vol_block_zero_size():
    assert volatility_multiplier(2.0) == 0.0
    assert volatility_multiplier(3.0) == 0.0


def test_vol_none_defaults_to_calm():
    assert volatility_multiplier(None) == 1.0


# ----------------- size() — combined ----------------------------------------

def test_size_high_conviction_calm_market_scales_up():
    r = size(base_units=100, tauric_confidence=10, kronos_vol_amp=1.0)
    assert r.final_units == 200  # 100 × 2.0 × 1.0
    assert r.conviction_mult == 2.0
    assert r.vol_mult == 1.0


def test_size_floor_conviction_calm_unchanged():
    r = size(base_units=100, tauric_confidence=7, kronos_vol_amp=1.0)
    assert r.final_units == 100  # 100 × 1.0 × 1.0


def test_size_high_conviction_chop_halves():
    r = size(base_units=100, tauric_confidence=10, kronos_vol_amp=1.5)
    assert r.final_units == 100  # 100 × 2.0 × 0.5
    assert r.vol_mult == 0.5


def test_size_low_conviction_chop_smallest():
    r = size(base_units=100, tauric_confidence=7, kronos_vol_amp=1.7)
    assert r.final_units == 50   # 100 × 1.0 × 0.5


def test_size_blocked_when_vol_too_high():
    r = size(base_units=100, tauric_confidence=10, kronos_vol_amp=2.5)
    assert r.final_units == 0
    assert r.vol_mult == 0.0
    assert "vol-blocked" in r.reason


def test_size_zero_base_returns_zero():
    r = size(base_units=0, tauric_confidence=10, kronos_vol_amp=1.0)
    assert r.final_units == 0


def test_size_enforces_min_units():
    # tiny base × half = 0.5 → rounded to 1 (min_units)
    r = size(base_units=1, tauric_confidence=7, kronos_vol_amp=1.5)
    assert r.final_units == 1


def test_size_50_base_high_conviction_calm():
    r = size(base_units=50, tauric_confidence=9, kronos_vol_amp=0.9)
    assert r.final_units == 80   # 50 × 1.6 × 1.0


def test_size_reason_string_includes_context():
    r = size(base_units=100, tauric_confidence=9, kronos_vol_amp=1.0)
    assert "conviction" in r.reason.lower()
    assert "vol" in r.reason.lower()
    assert "9/10" in r.reason
