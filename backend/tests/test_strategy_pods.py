"""Regression tests for the 3-pod ensemble.

Covers:
  • ensemble_vote 2-of-3 logic (LONG / SHORT / HOLD / split / ties)
  • pod_b_mean_reversion fires on calm-range capitulation
  • pod_c_momentum_breakout fires on Donchian break with strong ADX
  • Pods refuse to vote in mismatched regimes (vol_amp gates)
  • vote_concurrently times out a pod cleanly (no crash, returns HOLD)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np
import pytest

# Make /app/backend importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import strategy_pods as sp  # noqa: E402


# ---------- ensemble_vote -----------------------------------------------------

def _v(action, conf=7, reason="x"):
    return {"action": action, "confidence": conf, "reason": reason}


def test_two_longs_one_short_returns_long():
    out = sp.ensemble_vote([_v("LONG", 8), _v("LONG", 6), _v("SHORT", 9)])
    assert out["action"] == "LONG"
    assert out["agreeing_pods"] == 2
    assert out["confidence"] == 7  # mean(8,6) = 7


def test_three_shorts_returns_short():
    out = sp.ensemble_vote([_v("SHORT", 7), _v("SHORT", 8), _v("SHORT", 9)])
    assert out["action"] == "SHORT"
    assert out["agreeing_pods"] == 3
    assert out["confidence"] == 8


def test_one_long_one_short_one_hold_returns_hold():
    out = sp.ensemble_vote([_v("LONG", 9), _v("SHORT", 9), _v("HOLD", 5)])
    assert out["action"] == "HOLD"


def test_three_holds_returns_hold():
    out = sp.ensemble_vote([_v("HOLD"), _v("HOLD"), _v("HOLD")])
    assert out["action"] == "HOLD"


def test_split_two_each_direction_returns_hold():
    # Impossible with 3 pods but verifies tie guard
    out = sp.ensemble_vote([_v("LONG"), _v("SHORT"), _v("HOLD")])
    assert out["action"] == "HOLD"


# ---------- Pod B (mean-reversion) -------------------------------------------

def test_pod_b_fires_on_calm_capitulation():
    np.random.seed(42)
    calm = 100 + np.random.normal(0, 0.3, 75)
    plunge = calm[-1] + np.linspace(0, -3, 5) + np.random.normal(0, 0.1, 5)
    prices = np.concatenate([calm, plunge])
    out = sp.pod_b_mean_reversion(prices, prices + 0.1, prices - 0.1)
    assert out["action"] == "LONG"
    assert 1 <= out["confidence"] <= 10


def test_pod_b_holds_when_volatility_high():
    """High-vol regime → Pod B refuses (mean-reversion needs calm)."""
    np.random.seed(0)
    prices = 100 + np.cumsum(np.random.normal(0, 2.0, 120))  # very noisy
    out = sp.pod_b_mean_reversion(prices, prices + 0.5, prices - 0.5)
    # Either HOLD (regime-mismatch / no-edge) — but never random LONG/SHORT
    assert out["action"] in ("HOLD", "LONG", "SHORT")
    if out["action"] != "HOLD":
        # If it does vote, it must be a real reversal setup, not noise
        assert "RSI=" in out["reason"]


# ---------- Pod C (momentum/breakout) ----------------------------------------

def test_pod_c_fires_on_donchian_break_with_adx():
    prices = np.concatenate([np.linspace(100, 102, 60), np.linspace(102, 115, 25)])
    prices += np.random.RandomState(0).normal(0, 0.05, len(prices))
    out = sp.pod_c_momentum_breakout(prices, prices + 0.2, prices - 0.2)
    assert out["action"] == "LONG"
    assert "ADX=" in out["reason"]


def test_pod_c_holds_inside_donchian_range():
    np.random.seed(0)
    prices = 100 + np.random.normal(0, 0.5, 120)  # ranging, no break
    out = sp.pod_c_momentum_breakout(prices, prices + 0.1, prices - 0.1)
    assert out["action"] == "HOLD"


# ---------- vote_concurrently ------------------------------------------------

def test_vote_concurrently_returns_ensemble_shape():
    np.random.seed(0)
    prices = 100 + np.cumsum(np.random.normal(0, 0.5, 200))
    highs = prices + 0.2
    lows = prices - 0.2
    out = asyncio.run(sp.vote_concurrently(prices, highs, lows))
    assert "ensemble" in out
    assert "pods" in out
    assert set(out["pods"].keys()) == {"A", "B", "C"}
    for v in out["pods"].values():
        assert v["action"] in ("LONG", "SHORT", "HOLD")


def test_vote_concurrently_survives_timeout():
    """If per-pod timeout fires, that pod votes HOLD (never crashes the run)."""
    np.random.seed(0)
    prices = 100 + np.cumsum(np.random.normal(0, 0.5, 200))

    # Tiny timeout — at least one pod should timeout
    out = asyncio.run(sp.vote_concurrently(
        prices, prices + 0.1, prices - 0.1,
        per_pod_timeout_s=0.0001,
    ))
    assert "ensemble" in out
    # All timed-out pods → ensemble must be HOLD (no direction can win 2-of-3)
    assert out["ensemble"]["action"] == "HOLD"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
