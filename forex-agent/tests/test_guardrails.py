"""One test per guardrail rule (8 rules → 8 tests) plus idempotency check."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.guardrails import (
    AccountState,
    GuardrailRejection,
    GuardrailState,
    Order,
    check_order,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("OANDA_ENVIRONMENT", "practice")
    monkeypatch.setenv("MAX_POSITION_UNITS", "1000")
    monkeypatch.setenv("DAILY_LOSS_LIMIT_PCT", "2")


def _ok_order(**overrides) -> Order:
    base = dict(
        instrument="EUR_USD",
        side="buy",
        units=100,
        stop_loss=1.0500,
        take_profit=1.0700,
        rationale="test",
    )
    base.update(overrides)
    return Order(**base)


def _healthy_account() -> AccountState:
    return AccountState(starting_balance=10_000.0, realized_pl=0.0, unrealized_pl=0.0)


# Rule 0 — kill switch
def test_rule_0_kill_switch_rejects():
    state = GuardrailState(kill_switch_active=True)
    with pytest.raises(GuardrailRejection, match="Kill switch"):
        check_order(_ok_order(), state, _healthy_account())


# Rule 1 — TRADING_MODE must be paper
def test_rule_1_trading_mode_must_be_paper(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(GuardrailRejection, match="TRADING_MODE"):
        check_order(_ok_order(), GuardrailState(), _healthy_account())


# Rule 2 — OANDA_ENVIRONMENT must be practice
def test_rule_2_oanda_environment_must_be_practice(monkeypatch):
    monkeypatch.setenv("OANDA_ENVIRONMENT", "live")
    with pytest.raises(GuardrailRejection, match="OANDA_ENVIRONMENT"):
        check_order(_ok_order(), GuardrailState(), _healthy_account())


# Rule 3 — already halted earlier today
def test_rule_3_already_halted_today():
    state = GuardrailState()
    state.halt_today()
    with pytest.raises(GuardrailRejection, match="halted for the UTC day"):
        check_order(_ok_order(), state, _healthy_account())


# Rule 4 — stop_loss is required
def test_rule_4_stop_loss_required():
    with pytest.raises(GuardrailRejection, match="stop_loss is required"):
        check_order(
            _ok_order(stop_loss=None), GuardrailState(), _healthy_account()
        )


# Rule 5 — units must be > 0 and <= MAX_POSITION_UNITS
def test_rule_5_units_over_cap():
    with pytest.raises(GuardrailRejection, match="exceeds MAX_POSITION_UNITS"):
        check_order(_ok_order(units=10_000), GuardrailState(), _healthy_account())


def test_rule_5_units_zero():
    with pytest.raises(GuardrailRejection, match="must be > 0"):
        check_order(_ok_order(units=0), GuardrailState(), _healthy_account())


# Rule 6 — daily loss limit halts the day, fires alert exactly once
def test_rule_6_daily_loss_limit_halts_and_alerts_once():
    state = GuardrailState()
    losing_account = AccountState(
        starting_balance=10_000.0, realized_pl=-150.0, unrealized_pl=-100.0
    )  # 2.5% loss > 2% limit
    alert = MagicMock()

    with pytest.raises(GuardrailRejection, match="Daily loss limit hit"):
        check_order(_ok_order(), state, losing_account, on_daily_halt=alert)

    assert state.is_halted_today()
    assert alert.call_count == 1
    assert "🛑" in alert.call_args.args[0]

    # A subsequent call same UTC day must NOT re-fire the alert (idempotent)
    with pytest.raises(GuardrailRejection):
        check_order(_ok_order(), state, losing_account, on_daily_halt=alert)
    assert alert.call_count == 1


# Rule 7 — >5 orders in 60s rolling window
def test_rule_7_rate_limit_more_than_5_orders_in_60s():
    state = GuardrailState()
    now = time.time()
    # Five orders pass
    for i in range(5):
        check_order(
            _ok_order(),
            state,
            _healthy_account(),
            now=now + i * 0.1,
        )
    # Sixth within 60s window must be rejected
    with pytest.raises(GuardrailRejection, match="Rate limit"):
        check_order(_ok_order(), state, _healthy_account(), now=now + 1.0)


# Sanity — happy path passes
def test_happy_path_records_order_timestamp():
    state = GuardrailState()
    check_order(_ok_order(), state, _healthy_account())
    assert state.recent_order_count(60.0) == 1
