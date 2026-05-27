"""Tests for indicators.atr and adaptive_sl_pips / adaptive_sl_pct."""
import pandas as pd

from app.indicators import (
    adaptive_sl_pct,
    adaptive_sl_pips,
    atr,
    atr_in_pips,
    pip_size,
)


def _bars(n=30, base=1.1000, range_=0.0005):
    """Synthetic OHLC frame around `base` with consistent intrabar range."""
    rows = []
    px = base
    for i in range(n):
        h = px + range_
        low_v = px - range_
        c = px + (range_ if i % 2 else -range_)
        rows.append({"high": h, "low": low_v, "close": c})
        px = c
    return pd.DataFrame(rows)


def test_atr_returns_positive_float_for_enough_bars():
    df = _bars(30)
    val = atr(df, period=14)
    assert isinstance(val, float)
    assert val > 0


def test_atr_returns_none_when_too_few_bars():
    df = _bars(5)
    assert atr(df, period=14) is None


def test_atr_missing_columns_returns_none():
    df = pd.DataFrame({"open": [1, 2, 3], "close": [1, 2, 3]})
    assert atr(df, period=14) is None


def test_pip_size_jpy_pairs():
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("EUR_JPY") == 0.01


def test_pip_size_xau():
    assert pip_size("XAU_USD") == 0.01


def test_pip_size_default_fx():
    assert pip_size("EUR_USD") == 0.0001
    assert pip_size("GBP_USD") == 0.0001


def test_atr_in_pips_converts_correctly():
    df = _bars(30, base=1.1000, range_=0.0005)
    a = atr(df, period=14)
    p = atr_in_pips(df, "EUR_USD", period=14)
    assert a is not None and p is not None
    # 1 pip = 0.0001 for EUR_USD
    assert abs(p - a / 0.0001) < 1e-9


def test_adaptive_sl_pips_clamps_within_bounds():
    df = _bars(30)
    sl = adaptive_sl_pips(df, "EUR_USD", multiplier=1.5, floor_pips=6, ceiling_pips=80)
    assert sl is not None
    assert 6.0 <= sl <= 80.0


def test_adaptive_sl_pips_returns_none_for_short_data():
    df = _bars(5)
    assert adaptive_sl_pips(df, "EUR_USD") is None


def test_adaptive_sl_pct_returns_percentage():
    df = _bars(30, base=100.0, range_=0.5)  # ~0.5% range
    pct = adaptive_sl_pct(df, multiplier=1.5)
    assert pct is not None
    assert 0.5 <= pct <= 8.0


def test_adaptive_sl_pct_clamps_floor():
    df = _bars(30, base=100.0, range_=0.001)  # very tiny range
    pct = adaptive_sl_pct(df, multiplier=1.5, floor_pct=0.5)
    assert pct == 0.5
