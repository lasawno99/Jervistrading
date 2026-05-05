"""Tests for profit-lock ledger logic."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.profit_lock import ProfitLock


def _make(tmp_path: Path, threshold: float = 5.0, hint: float = 100_000.0) -> ProfitLock:
    return ProfitLock(
        path=str(tmp_path / "ledger.json"),
        threshold_pct=threshold,
        starting_balance_hint=hint,
    )


def test_initial_state_no_lock(tmp_path):
    pl = _make(tmp_path)
    assert pl.baseline == 100_000.0
    assert pl.total_locked == 0.0
    assert pl.check_and_lock(100_500.0) is None  # only +0.5%


def test_lock_fires_at_exact_threshold(tmp_path):
    pl = _make(tmp_path, threshold=5.0)
    event = pl.check_and_lock(105_000.0)
    assert event is not None
    assert event.locked_amount == 5_000.0
    assert pl.baseline == 105_000.0
    assert pl.total_locked == 5_000.0


def test_lock_does_not_fire_below_threshold(tmp_path):
    pl = _make(tmp_path)
    assert pl.check_and_lock(104_999.0) is None
    assert pl.baseline == 100_000.0
    assert pl.total_locked == 0.0


def test_consecutive_locks_compound(tmp_path):
    pl = _make(tmp_path)
    # First lock at $105k
    pl.check_and_lock(105_000.0)
    # Now baseline is $105k → next threshold is $110,250
    assert pl.check_and_lock(110_249.0) is None
    event2 = pl.check_and_lock(110_250.0)
    assert event2 is not None
    assert event2.locked_amount == 5_250.0  # 5% of new baseline
    assert pl.total_locked == 10_250.0


def test_persistence_roundtrip(tmp_path):
    pl1 = _make(tmp_path)
    pl1.check_and_lock(105_000.0)
    # New instance reads from disk
    pl2 = _make(tmp_path)
    assert pl2.baseline == 105_000.0
    assert pl2.total_locked == 5_000.0
    assert len(pl2.snapshot()["last_event"]) > 0


def test_drawdown_does_not_unwind_ledger(tmp_path):
    pl = _make(tmp_path)
    pl.check_and_lock(105_000.0)
    # Account drops below baseline — no rollback
    assert pl.check_and_lock(102_000.0) is None
    assert pl.baseline == 105_000.0
    assert pl.total_locked == 5_000.0


def test_total_wealth_computation(tmp_path):
    pl = _make(tmp_path)
    pl.check_and_lock(105_000.0)   # locks $5k, baseline now $105k
    # NAV drifts down to $103k — total wealth = $103k + $5k locked = $108k
    assert pl.total_wealth(103_000.0) == 108_000.0


def test_zero_threshold_disables_lock(tmp_path):
    pl = _make(tmp_path, threshold=0.0)
    assert pl.check_and_lock(200_000.0) is None
