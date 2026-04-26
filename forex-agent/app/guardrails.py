"""Deterministic, code-side safety checks for every order.

The LLM proposes; this module decides. Nothing here trusts model output.
All checks are pure functions of the order + an in-memory account state
maintained by the OANDA tool.

Public surface:
    - GuardrailRejection (exception)
    - Order (lightweight value object)
    - GuardrailState (rate-limit + halt bookkeeping; one per process)
    - check_order(order, state, account) -> None  (raises on rejection)
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Deque, List, Optional
from collections import deque

import structlog

log = structlog.get_logger()


class GuardrailRejection(Exception):
    """Raised when a proposed order fails a hard safety check."""


@dataclass
class Order:
    instrument: str
    side: str  # "buy" or "sell"
    units: int
    stop_loss: Optional[float]
    take_profit: Optional[float]
    rationale: str = ""


@dataclass
class AccountState:
    """Snapshot of the practice account used for daily-loss math.

    starting_balance is the account NAV at the start of the current UTC day.
    realized_pl + unrealized_pl is checked against DAILY_LOSS_LIMIT_PCT.
    """

    starting_balance: float
    realized_pl: float
    unrealized_pl: float

    @property
    def total_pl(self) -> float:
        return self.realized_pl + self.unrealized_pl

    @property
    def loss_pct(self) -> float:
        if self.starting_balance <= 0:
            return 0.0
        if self.total_pl >= 0:
            return 0.0
        return abs(self.total_pl) / self.starting_balance * 100.0


@dataclass
class GuardrailState:
    """Per-process rate-limit + daily-halt bookkeeping."""

    order_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=64))
    halted_for_utc_date: Optional[str] = None
    daily_alert_sent_date: Optional[str] = None
    kill_switch_active: bool = False

    def record_order(self, now: Optional[float] = None) -> None:
        self.order_timestamps.append(now if now is not None else time.time())

    def recent_order_count(
        self, window_seconds: float = 60.0, now: Optional[float] = None
    ) -> int:
        n = now if now is not None else time.time()
        cutoff = n - window_seconds
        return sum(1 for t in self.order_timestamps if t >= cutoff)

    @staticmethod
    def _utc_date_str(now: Optional[datetime] = None) -> str:
        return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")

    def is_halted_today(self, now: Optional[datetime] = None) -> bool:
        return self.halted_for_utc_date == self._utc_date_str(now)

    def halt_today(self, now: Optional[datetime] = None) -> None:
        self.halted_for_utc_date = self._utc_date_str(now)

    def alert_already_sent_today(self, now: Optional[datetime] = None) -> bool:
        return self.daily_alert_sent_date == self._utc_date_str(now)

    def mark_alert_sent(self, now: Optional[datetime] = None) -> None:
        self.daily_alert_sent_date = self._utc_date_str(now)


def _max_position_units() -> int:
    return int(os.environ["MAX_POSITION_UNITS"])


def _daily_loss_limit_pct() -> float:
    return float(os.environ["DAILY_LOSS_LIMIT_PCT"])


def check_order(
    order: Order,
    state: GuardrailState,
    account: AccountState,
    *,
    now: Optional[float] = None,
    on_daily_halt: Optional[Callable[[str], None]] = None,
) -> None:
    """Raise GuardrailRejection if the order fails any hard safety rule.

    Rules (in order; cheapest first, manual override above all automated checks):
      0. Kill switch active → reject (manual override).
      1. TRADING_MODE must be 'paper'.
      2. OANDA_ENVIRONMENT must be 'practice'.
      3. Already halted earlier this UTC day → reject.
      4. order.stop_loss must be present.
      5. order.units must be > 0 and <= MAX_POSITION_UNITS.
      6. Daily loss (realized + unrealized) must not exceed DAILY_LOSS_LIMIT_PCT.
         If exceeded, halt for the rest of the UTC day and fire on_daily_halt
         exactly once per UTC day (idempotent across concurrent callers).
      7. No more than 5 orders in any 60-second window.

    on_daily_halt is invoked at most once per UTC day with a Telegram-ready string.
    """
    # 0
    if state.kill_switch_active:
        raise GuardrailRejection("Kill switch is ON — all trading halted.")

    # 1
    if os.environ.get("TRADING_MODE", "").strip().lower() != "paper":
        raise GuardrailRejection("TRADING_MODE is not 'paper' — all orders rejected")

    # 2
    if os.environ.get("OANDA_ENVIRONMENT", "").strip().lower() != "practice":
        raise GuardrailRejection(
            "OANDA_ENVIRONMENT is not 'practice' — all orders rejected"
        )

    # 3 — already halted earlier today
    if state.is_halted_today():
        raise GuardrailRejection(
            "Daily loss limit already triggered — trading halted for the UTC day"
        )

    # 4
    if order.stop_loss is None:
        raise GuardrailRejection("stop_loss is required on every order")

    # 5
    if order.units <= 0:
        raise GuardrailRejection(f"order.units must be > 0 (got {order.units})")
    if order.units > _max_position_units():
        raise GuardrailRejection(
            f"order.units {order.units} exceeds MAX_POSITION_UNITS {_max_position_units()}"
        )

    # 6 — fresh check against current account snapshot
    limit_pct = _daily_loss_limit_pct()
    if account.loss_pct >= limit_pct:
        state.halt_today()
        msg = (
            f"🛑 Daily loss limit hit ({account.loss_pct:.2f}% >= {limit_pct:.2f}%), "
            "trading halted."
        )
        if on_daily_halt and not state.alert_already_sent_today():
            state.mark_alert_sent()
            try:
                on_daily_halt(msg)
            except Exception as e:
                log.error("daily_halt_alert_failed", error=str(e))
        raise GuardrailRejection(msg)

    # 7
    if state.recent_order_count(60.0, now=now) >= 5:
        raise GuardrailRejection(
            "Rate limit: more than 5 orders in the last 60 seconds"
        )

    state.record_order(now=now)
    log.info(
        "guardrails_passed",
        instrument=order.instrument,
        side=order.side,
        units=order.units,
    )


def fire_telegram_alert(send_coro_factory: Callable[[str], "asyncio.Future"]) -> Callable[[str], None]:
    """Adapter so check_order's sync `on_daily_halt` can dispatch an async send.

    Schedules the coroutine on the running event loop without blocking.
    """
    def _fire(msg: str) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_coro_factory(msg))
        except RuntimeError:
            # No running loop (e.g. unit tests) — log and move on.
            log.warning("daily_halt_alert_skipped_no_loop", msg=msg)

    return _fire
