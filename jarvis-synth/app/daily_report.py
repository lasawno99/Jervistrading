"""Daily summary report.

At end of UTC weekday, posts a Telegram message with:
- TODAY section: NAV change, realized P&L, trades today
- ALL-TIME section: cumulative locked, total wealth, growth since day-1

Persists daily snapshots to /app/data/daily_history.json so past days are
accessible (cumulative numbers compound across restarts).
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import structlog

log = structlog.get_logger()


@dataclass
class DailySnapshot:
    date: str             # YYYY-MM-DD UTC
    nav_open: float       # NAV at the start of this UTC day
    nav_close: float      # NAV at end of day (when this snapshot is recorded)
    realized_today: float # NAV close - NAV open (paper realized P&L for the day)
    open_positions: int
    total_locked: float   # cumulative locked at time of snapshot
    total_wealth: float   # nav_close + total_locked


@dataclass
class DailyHistory:
    inception_date: str
    inception_balance: float
    snapshots: List[DailySnapshot] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "inception_date": self.inception_date,
                "inception_balance": self.inception_balance,
                "snapshots": [asdict(s) for s in self.snapshots],
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> "DailyHistory":
        d = json.loads(raw)
        return cls(
            inception_date=d["inception_date"],
            inception_balance=float(d["inception_balance"]),
            snapshots=[DailySnapshot(**s) for s in d.get("snapshots", [])],
        )


class DailyReport:
    """Persistent daily-history tracker; snapshot once per UTC day."""

    def __init__(self, path: str, inception_balance_hint: float):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._history = self._load_or_init(inception_balance_hint)

    def _load_or_init(self, hint: float) -> DailyHistory:
        try:
            if self._path.exists():
                hist = DailyHistory.from_json(self._path.read_text())
                log.info(
                    "daily_history_loaded",
                    inception=hist.inception_date,
                    snapshots=len(hist.snapshots),
                )
                return hist
        except Exception as e:
            log.error("daily_history_load_failed", error=str(e))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hist = DailyHistory(inception_date=today, inception_balance=hint)
        self._save(hist)
        log.info("daily_history_initialized", inception=today, balance=hint)
        return hist

    def _save(self, hist: DailyHistory) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(hist.to_json())
            tmp.replace(self._path)
        except Exception as e:
            log.error("daily_history_save_failed", error=str(e))

    @property
    def inception_balance(self) -> float:
        return self._history.inception_balance

    @property
    def inception_date(self) -> str:
        return self._history.inception_date

    @property
    def snapshots(self) -> List[DailySnapshot]:
        return list(self._history.snapshots)

    def today_open(self) -> Optional[float]:
        """Get the NAV recorded at the most-recent snapshot's nav_close,
        or inception_balance if no snapshot exists. Used as 'opening NAV today'."""
        if self._history.snapshots:
            return self._history.snapshots[-1].nav_close
        return self._history.inception_balance

    def record_snapshot(
        self,
        nav_close: float,
        open_positions: int,
        total_locked: float,
    ) -> DailySnapshot:
        with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            nav_open = self.today_open() or nav_close
            snap = DailySnapshot(
                date=today,
                nav_open=float(nav_open),
                nav_close=float(nav_close),
                realized_today=float(nav_close) - float(nav_open),
                open_positions=int(open_positions),
                total_locked=float(total_locked),
                total_wealth=float(nav_close) + float(total_locked),
            )
            # Replace if same date (guard against re-fires)
            if self._history.snapshots and self._history.snapshots[-1].date == today:
                self._history.snapshots[-1] = snap
            else:
                self._history.snapshots.append(snap)
            self._save(self._history)
            log.info(
                "daily_snapshot_recorded",
                date=today,
                realized_today=snap.realized_today,
                total_wealth=snap.total_wealth,
            )
            return snap


def _signed_money(val: float) -> str:
    """Format as '+$500.00' or '-$500.00' (sign before $, never '$+')."""
    sign = "+" if val >= 0 else "-"
    return f"{sign}${abs(val):,.2f}"


def format_daily_summary(
    snap: DailySnapshot, hist: DailyHistory, current_nav: float
) -> str:
    """Render the two-section message."""
    delta_today_pct = (
        (snap.realized_today / snap.nav_open * 100) if snap.nav_open else 0.0
    )
    delta_today_arrow = "🟢" if snap.realized_today >= 0 else "🔴"

    inception_total = current_nav + snap.total_locked - hist.inception_balance
    inception_pct = (
        (inception_total / hist.inception_balance * 100)
        if hist.inception_balance
        else 0.0
    )
    inception_arrow = "🟢" if inception_total >= 0 else "🔴"

    days_active = len(hist.snapshots)
    avg_daily = inception_total / days_active if days_active > 0 else 0.0

    last7 = hist.snapshots[-7:]
    week_total = sum(s.realized_today for s in last7)
    week_arrow = "🟢" if week_total >= 0 else "🔴"

    return (
        f"📊 *Daily Summary — {snap.date}*\n"
        f"\n"
        f"━━ TODAY ━━\n"
        f"{delta_today_arrow} P&L: *{_signed_money(snap.realized_today)}* ({delta_today_pct:+.2f}%)\n"
        f"NAV: ${snap.nav_open:,.2f} → ${snap.nav_close:,.2f}\n"
        f"Open positions: {snap.open_positions}\n"
        f"\n"
        f"━━ THIS WEEK ━━\n"
        f"{week_arrow} 7-day P&L: *{_signed_money(week_total)}*\n"
        f"\n"
        f"━━ ALL-TIME ━━\n"
        f"Inception: {hist.inception_date}  ({days_active} days active)\n"
        f"Starting balance: ${hist.inception_balance:,.2f}\n"
        f"Current NAV: ${current_nav:,.2f}\n"
        f"Locked profits: ${snap.total_locked:,.2f}\n"
        f"Total wealth: *${snap.total_wealth:,.2f}*\n"
        f"{inception_arrow} Total return: *{_signed_money(inception_total)}* ({inception_pct:+.2f}%)\n"
        f"Avg daily: {_signed_money(avg_daily)}"
    )
