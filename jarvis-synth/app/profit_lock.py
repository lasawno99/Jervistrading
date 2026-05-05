"""Profit-Lock ledger.

Watches account NAV; when it crosses `baseline * (1 + threshold_pct/100)`,
locks the gain to a cumulative ledger, resets the baseline to the new NAV,
and emits a Telegram alert.

Persistence: a small JSON file at LEDGER_PATH. On Railway, mount a Volume
at the parent directory (default `/app/data`) so the ledger survives
redeploys. If the path isn't writable, falls back to in-memory and logs.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

import structlog

log = structlog.get_logger()


@dataclass
class LockEvent:
    timestamp: str   # ISO UTC
    nav_at_lock: float
    baseline_before: float
    baseline_after: float
    locked_amount: float


@dataclass
class LedgerState:
    starting_balance: float           # Original starting NAV (never changes)
    current_baseline: float           # Resets to NAV after each lock
    total_locked: float = 0.0
    events: List[LockEvent] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "starting_balance": self.starting_balance,
                "current_baseline": self.current_baseline,
                "total_locked": self.total_locked,
                "events": [asdict(e) for e in self.events],
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> "LedgerState":
        d = json.loads(raw)
        return cls(
            starting_balance=float(d["starting_balance"]),
            current_baseline=float(d["current_baseline"]),
            total_locked=float(d.get("total_locked", 0.0)),
            events=[LockEvent(**e) for e in d.get("events", [])],
        )


class ProfitLock:
    """Atomic-write JSON-persisted ledger with NAV-threshold sweeps."""

    def __init__(
        self,
        path: str,
        threshold_pct: float,
        starting_balance_hint: float,
    ):
        self._path = Path(path)
        self._threshold = float(threshold_pct)
        self._lock = threading.Lock()
        self._state = self._load_or_init(starting_balance_hint)

    # ---- persistence ----------------------------------------------------

    def _load_or_init(self, hint: float) -> LedgerState:
        try:
            if self._path.exists():
                state = LedgerState.from_json(self._path.read_text())
                log.info(
                    "ledger_loaded",
                    path=str(self._path),
                    baseline=state.current_baseline,
                    total_locked=state.total_locked,
                    events=len(state.events),
                )
                return state
        except Exception as e:
            log.error("ledger_load_failed", path=str(self._path), error=str(e))

        state = LedgerState(starting_balance=hint, current_baseline=hint)
        self._save(state)
        log.info(
            "ledger_initialized",
            path=str(self._path),
            starting_balance=hint,
        )
        return state

    def _save(self, state: LedgerState) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(state.to_json())
            tmp.replace(self._path)
        except Exception as e:
            log.error("ledger_save_failed", path=str(self._path), error=str(e))

    # ---- public surface -------------------------------------------------

    @property
    def baseline(self) -> float:
        return self._state.current_baseline

    @property
    def total_locked(self) -> float:
        return self._state.total_locked

    @property
    def starting_balance(self) -> float:
        return self._state.starting_balance

    def total_wealth(self, current_nav: float) -> float:
        """Total realized + still-trading wealth view."""
        return float(current_nav) + self._state.total_locked

    def snapshot(self) -> dict:
        return {
            "starting_balance": self._state.starting_balance,
            "current_baseline": self._state.current_baseline,
            "total_locked": self._state.total_locked,
            "event_count": len(self._state.events),
            "last_event": (
                asdict(self._state.events[-1])
                if self._state.events
                else None
            ),
        }

    def check_and_lock(self, current_nav: float) -> Optional[LockEvent]:
        """If NAV is at or above baseline * (1 + threshold), lock the gain.

        Returns the LockEvent if a lock fired, else None.
        """
        if self._threshold <= 0:
            return None
        with self._lock:
            target = self._state.current_baseline * (1 + self._threshold / 100.0)
            if current_nav < target:
                return None

            locked_amount = current_nav - self._state.current_baseline
            event = LockEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                nav_at_lock=float(current_nav),
                baseline_before=self._state.current_baseline,
                baseline_after=float(current_nav),
                locked_amount=float(locked_amount),
            )
            self._state.current_baseline = float(current_nav)
            self._state.total_locked += float(locked_amount)
            self._state.events.append(event)
            self._save(self._state)
            log.info(
                "profit_lock_fired",
                locked_amount=event.locked_amount,
                new_baseline=event.baseline_after,
                total_locked=self._state.total_locked,
            )
            return event


def format_lock_alert(event: LockEvent, total_locked: float, total_wealth: float) -> str:
    return (
        "💰 *Profit Lock Triggered*\n"
        f"Swept: +${event.locked_amount:,.2f} ({event.locked_amount / event.baseline_before * 100:.2f}% over baseline)\n"
        f"New trading baseline: ${event.baseline_after:,.2f}\n"
        f"Total locked: ${total_locked:,.2f}\n"
        f"Total wealth: ${total_wealth:,.2f}\n"
        f"At: {event.timestamp[:19]}Z"
    )


def format_ledger_summary(snapshot: dict, current_nav: float) -> str:
    last = snapshot.get("last_event")
    last_line = (
        f"Last lock: +${last['locked_amount']:,.2f} on {last['timestamp'][:19]}Z"
        if last
        else "No locks yet."
    )
    total_wealth = float(current_nav) + snapshot["total_locked"]
    return (
        "📒 *Profit Ledger*\n"
        f"Starting balance: ${snapshot['starting_balance']:,.2f}\n"
        f"Current trading baseline: ${snapshot['current_baseline']:,.2f}\n"
        f"Current NAV: ${current_nav:,.2f}\n"
        f"Total locked: ${snapshot['total_locked']:,.2f} ({snapshot['event_count']} events)\n"
        f"Total wealth: ${total_wealth:,.2f}\n"
        f"{last_line}"
    )
