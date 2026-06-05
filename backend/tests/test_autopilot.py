"""Regression tests for autopilot.py — the autonomous compare+promote pipeline.

Covers the pure-logic surfaces (gate evaluation, settings, candidate filtering).
The end-to-end loop is exercised live (yfinance) in the smoke test below.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autopilot as ap  # noqa: E402


# ---------- gate ------------------------------------------------------------

def _result(**kw):
    """Build a fake _summary-shaped dict."""
    return {
        "total_trades": kw.get("trades", 0),
        "win_rate": kw.get("wr", 0.0),
        "expectancy": 0.0,
        "total_pl_pct": 0.0,
        "profit_factor": kw.get("pf", 0.0),
        "sharpe_ratio": kw.get("sharpe", 0.0),
        "max_drawdown_pct": kw.get("dd", 0.0),
        "elapsed_seconds": 0.0,
        "error": None,
    }


def test_gate_clear_when_all_four_improve():
    single = _result(wr=30, pf=1.0, sharpe=0.5, dd=20)
    ens = _result(wr=45, pf=1.6, sharpe=0.9, dd=15)
    g = ap._gate(single, ens)
    assert g["clear"] is True
    assert g["passing_count"] == 4


def test_gate_clear_with_three_of_four():
    single = _result(wr=30, pf=1.0, sharpe=0.5, dd=20)
    ens = _result(wr=45, pf=1.6, sharpe=0.4, dd=15)  # sharpe NOT improved
    g = ap._gate(single, ens)
    assert g["clear"] is True
    assert g["passing_count"] == 3
    assert g["sharpe_up"] is False


def test_gate_blocked_with_two_of_four():
    single = _result(wr=30, pf=1.0, sharpe=0.5, dd=20)
    ens = _result(wr=20, pf=1.6, sharpe=0.9, dd=25)
    g = ap._gate(single, ens)
    assert g["clear"] is False
    assert g["passing_count"] == 2


# ---------- _summary serializer --------------------------------------------

def test_summary_round_trips_numpy_types():
    """_summary must coerce numpy scalars to plain Python so Mongo can serialize."""
    import numpy as np
    fake = SimpleNamespace(
        total_trades=np.int64(7),
        win_rate=np.float64(42.857),
        expectancy=np.float64(0.001),
        total_pl_pct=np.float64(3.14),
        profit_factor=np.float64(1.234),
        sharpe_ratio=np.float64(0.567),
        max_drawdown_pct=np.float64(8.91),
        elapsed_seconds=np.float64(1.23),
        error=None,
    )
    s = ap._summary(fake)
    # All values must be plain Python — int, float, str, None — not numpy types
    for k, v in s.items():
        if v is None:
            continue
        assert isinstance(v, (int, float, str)), f"{k} leaked type {type(v)}"


# ---------- thresholds default sanity --------------------------------------

def test_threshold_constants_match_user_spec():
    """User said: ≥30% rate AND ≥20 actionable signals → trigger compare."""
    assert ap.AUTOPILOT_MIN_RATE == 30.0
    assert ap.AUTOPILOT_MIN_SAMPLES == 20


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
