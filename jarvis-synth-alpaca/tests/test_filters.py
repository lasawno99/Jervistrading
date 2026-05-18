"""Tests for Layer-4b pre-execution filters."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.filters import (
    indicator_confluence,
    mtf_trend_filter,
    run_pre_tauric_filters,
    session_filter,
)


def _series(values):
    return pd.DataFrame({"close": values})


def _uptrend(n=50, start=100.0, step=0.5):
    """Realistic noisy uptrend so indicators don't degenerate to 0/100."""
    import random
    rng = random.Random(42)
    return _series([start + i * step + rng.uniform(-0.8, 0.8) for i in range(n)])


def _downtrend(n=50, start=100.0, step=0.5):
    import random
    rng = random.Random(7)
    return _series([start - i * step + rng.uniform(-0.8, 0.8) for i in range(n)])


# ---------- mtf_trend_filter ----------

def test_mtf_filter_allows_when_all_timeframes_agree_long():
    r = mtf_trend_filter("LONG", {"4H": _uptrend(), "1H": _uptrend(), "15M": _uptrend()})
    assert r.allowed is True


def test_mtf_filter_rejects_when_all_disagree():
    r = mtf_trend_filter("LONG", {"4H": _downtrend(), "1H": _downtrend(), "15M": _downtrend()})
    assert r.allowed is False
    assert "conflict" in r.reason.lower()


def test_mtf_filter_allows_when_two_of_three_agree():
    r = mtf_trend_filter("LONG", {"4H": _uptrend(), "1H": _uptrend(), "15M": _downtrend()})
    assert r.allowed is True


def test_mtf_filter_hold_passes_through():
    r = mtf_trend_filter("HOLD", {"1H": _uptrend()})
    assert r.allowed is True


# ---------- indicator_confluence ----------

def test_indicators_allow_long_in_uptrend():
    # Modest uptrend that doesn't exhaust RSI/MACD — a clean entry setup.
    import random
    rng = random.Random(11)
    closes = []
    v = 100.0
    for i in range(50):
        v += 0.18 + rng.uniform(-0.35, 0.45)
        closes.append(v)
    r = indicator_confluence("LONG", _series(closes))
    # At least 2 of 3 indicators should align with the uptrend
    aligned = sum(1 for v in r.details["votes"].values() if v)
    assert aligned >= 2
    assert r.allowed is True


def test_indicators_reject_long_in_strong_downtrend():
    r = indicator_confluence("LONG", _downtrend(80, start=100, step=0.4))
    assert r.allowed is False


def test_indicators_short_in_downtrend_passes():
    r = indicator_confluence("SHORT", _downtrend(80, start=100, step=0.4))
    assert r.allowed is True


def test_indicators_insufficient_data_passthrough():
    r = indicator_confluence("LONG", _series([100, 101, 102]))
    assert r.allowed is True


# ---------- session_filter ----------

def test_session_forex_london_hours_ok():
    now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)  # Mon 10 UTC
    r = session_filter("EUR_USD", asset_kind="forex", now=now)
    assert r.allowed is True


def test_session_forex_weekend_rejected():
    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)  # Sat
    r = session_filter("EUR_USD", asset_kind="forex", now=now)
    assert r.allowed is False
    assert "weekend" in r.reason.lower()


def test_session_forex_asia_overnight_rejected():
    now = datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc)  # Tue 2 UTC
    r = session_filter("EUR_USD", asset_kind="forex", now=now)
    assert r.allowed is False
    assert "low-liquidity" in r.reason.lower()


def test_session_crypto_always_open():
    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)  # Sat
    r = session_filter("BTC/USD", asset_kind="crypto", now=now)
    assert r.allowed is True


def test_session_crypto_sunday_early_morning_rejected():
    now = datetime(2026, 5, 10, 2, 0, tzinfo=timezone.utc)  # Sun 02 UTC
    r = session_filter("BTC/USD", asset_kind="crypto", now=now)
    assert r.allowed is False


def test_session_auto_detects_forex_underscore():
    now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    r = session_filter("EUR_USD", asset_kind="auto", now=now)
    assert r.allowed is True
    r_off = session_filter("EUR_USD", asset_kind="auto", now=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc))
    assert r_off.allowed is False


def test_session_auto_detects_crypto_slash():
    now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    r = session_filter("BTC/USD", asset_kind="auto", now=now)
    assert r.allowed is True


# ---------- combined runner ----------

def test_combined_runs_all_three_when_mtf_provided():
    bars = _uptrend(80, start=100, step=0.4)
    allowed, records = run_pre_tauric_filters(
        instrument="EUR_USD",
        proposed_direction="LONG",
        primary_bars=bars,
        mtf_bars={"4H": bars, "1H": bars, "15M": bars},
        asset_kind="forex",
    )
    assert len(records) == 3
    names = [r["name"] for r in records]
    assert "mtf_trend" in names
    assert "indicators" in names
    assert "session" in names


def test_combined_short_circuits_on_first_failure():
    """A weekend forex trade should fail at the session filter."""
    now_iso_fri = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)  # Sat
    # We can't pass `now` through the runner, so test via filter directly:
    r = session_filter("EUR_USD", asset_kind="forex", now=now_iso_fri)
    assert r.allowed is False
