"""Tests for trailing_stops.decide — pure decision logic, no I/O."""
from app.trailing_stops import decide


def _trade(side="buy", entry=1.1000, sl=1.0980, trade_id="T1", instrument="EUR_USD"):
    return {
        "trade_id": trade_id,
        "instrument": instrument,
        "side": side,
        "units": 1000,
        "entry": entry,
        "stop_loss": sl,
        "unrealized_pl": 0.0,
    }


def test_buy_below_breakeven_trigger_does_nothing():
    # R = 20 pips; move = 10 pips (0.5R) — too small
    tr = _trade(side="buy", entry=1.1000, sl=1.0980)
    d = decide(tr, current_price=1.1010)
    assert d.new_sl is None


def test_buy_at_one_r_moves_to_breakeven():
    # R = 20 pips; move = exactly 20 pips (1.0R)
    tr = _trade(side="buy", entry=1.1000, sl=1.0980)
    d = decide(tr, current_price=1.1020)
    assert d.new_sl is not None
    assert abs(d.new_sl - 1.1000) < 1e-9  # breakeven
    assert "breakeven" in d.reason


def test_buy_at_two_r_trails_to_plus_one_r():
    # R = 20 pips; move = 40 pips (2.0R) → trail to entry + 1R = 1.1020
    tr = _trade(side="buy", entry=1.1000, sl=1.0980)
    d = decide(tr, current_price=1.1040)
    assert d.new_sl is not None
    assert abs(d.new_sl - 1.1020) < 1e-9
    assert "trail" in d.reason.lower()


def test_sell_at_one_r_moves_to_breakeven():
    tr = _trade(side="sell", entry=1.1000, sl=1.1020)
    d = decide(tr, current_price=1.0980)  # 20 pips in favor for short
    assert d.new_sl is not None
    assert abs(d.new_sl - 1.1000) < 1e-9


def test_sell_at_two_r_trails_to_plus_one_r():
    tr = _trade(side="sell", entry=1.1000, sl=1.1020)
    d = decide(tr, current_price=1.0960)  # 40 pips in favor → trail to 1.0980
    assert d.new_sl is not None
    assert abs(d.new_sl - 1.0980) < 1e-9


def test_buy_ratchet_one_way():
    # SL already tightened to entry +1R; price still at 2R → trail target equals
    # current SL → ratchet should reject (no widening, no re-firing the same level).
    tr = _trade(side="buy", entry=1.1000, sl=1.1010)  # R = 10 pips
    d = decide(tr, current_price=1.1030)              # move = 30 pips = 3R → trail to 1.1010
    assert d.new_sl is None
    assert "ratchet" in d.reason


def test_sell_ratchet_one_way():
    tr = _trade(side="sell", entry=1.1000, sl=1.0990)  # R = 10 pips
    d = decide(tr, current_price=1.0970)               # move = 30 pips = 3R → trail to 1.0990
    assert d.new_sl is None
    assert "ratchet" in d.reason


def test_zero_r_returns_no_change():
    tr = _trade(side="buy", entry=1.1000, sl=1.1000)
    d = decide(tr, current_price=1.1100)
    assert d.new_sl is None
    assert "zero R" in d.reason


def test_missing_sl_returns_no_change():
    tr = _trade(side="buy", entry=1.1000, sl=None)
    d = decide(tr, current_price=1.1100)
    assert d.new_sl is None
