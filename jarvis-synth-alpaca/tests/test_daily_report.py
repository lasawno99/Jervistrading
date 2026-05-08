"""Tests for daily-summary report logic."""
from __future__ import annotations

from pathlib import Path

from app.daily_report import DailyReport, DailySnapshot, format_daily_summary


def _make(tmp_path: Path, hint: float = 100_000.0) -> DailyReport:
    return DailyReport(
        path=str(tmp_path / "history.json"),
        inception_balance_hint=hint,
    )


def test_inception_initialized(tmp_path):
    r = _make(tmp_path)
    assert r.inception_balance == 100_000.0
    assert r.snapshots == []


def test_first_snapshot_uses_inception_as_open(tmp_path):
    r = _make(tmp_path)
    snap = r.record_snapshot(nav_close=100_500.0, open_positions=1, total_locked=0.0)
    assert snap.nav_open == 100_000.0
    assert snap.realized_today == 500.0
    assert snap.total_wealth == 100_500.0


def test_subsequent_snapshot_uses_prior_close_as_open(tmp_path):
    r = _make(tmp_path)
    r.record_snapshot(nav_close=100_500.0, open_positions=0, total_locked=0.0)
    # Second snapshot — note same-day guard means we must hack the date
    r._history.snapshots[-1].date = "2026-04-30"  # backdate
    snap2 = r.record_snapshot(nav_close=101_200.0, open_positions=2, total_locked=0.0)
    assert snap2.nav_open == 100_500.0
    assert snap2.realized_today == 700.0


def test_persistence_roundtrip(tmp_path):
    r1 = _make(tmp_path)
    r1.record_snapshot(nav_close=100_500.0, open_positions=1, total_locked=0.0)
    r2 = _make(tmp_path)
    assert len(r2.snapshots) == 1
    assert r2.snapshots[0].nav_close == 100_500.0


def test_summary_format_includes_all_sections(tmp_path):
    r = _make(tmp_path, hint=100_000.0)
    snap = r.record_snapshot(nav_close=100_500.0, open_positions=1, total_locked=5_000.0)
    msg = format_daily_summary(snap, r._history, current_nav=100_500.0)
    assert "TODAY" in msg
    assert "THIS WEEK" in msg
    assert "ALL-TIME" in msg
    assert "Locked profits" in msg
    assert "Total wealth" in msg
    assert "+$500" in msg


def test_total_return_includes_locked(tmp_path):
    r = _make(tmp_path, hint=100_000.0)
    # NAV has dropped to $98k but $5k is locked → total wealth = $103k → +$3k return
    snap = r.record_snapshot(nav_close=98_000.0, open_positions=0, total_locked=5_000.0)
    msg = format_daily_summary(snap, r._history, current_nav=98_000.0)
    # Total wealth $103k = +$3k from $100k inception
    assert "103,000" in msg
    assert "+$3,000" in msg
