"""Append-only cycle decision log (JSON Lines) for read-only diagnostics.

Also best-effort POSTs each entry to the JARVIS dashboard's
``/api/bot-brain/cycles`` webhook so the Bot Brain panel updates in
real time (without exposing the worker's HTTP sidecar publicly).
"""
from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog

log = structlog.get_logger()


def _push_to_dashboard(payload: Dict[str, Any]) -> None:
    """Fire-and-forget POST to dashboard. Never blocks the trading loop."""
    url = os.environ.get("DASHBOARD_LOCK_WEBHOOK_URL", "").strip()
    token = os.environ.get("DASHBOARD_LOCK_TOKEN", "").strip()
    if not url or not token:
        return
    # The profit-lock URL ends in /broker/profit-locks; derive the bot-brain URL.
    brain_url = url.replace("/broker/profit-locks", "/bot-brain/cycles")
    if "/bot-brain/cycles" not in brain_url:
        return  # unrecognized base
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.post(
                brain_url,
                json=payload,
                headers={"X-Lock-Token": token, "Content-Type": "application/json"},
            )
        if not (200 <= r.status_code < 300):
            log.debug("bot_brain_push_non2xx", status=r.status_code)
    except Exception as e:
        log.debug("bot_brain_push_failed", error=str(e))


class CycleLog:
    """JSONL append-only ring log. Last-N is read tail-style; writes are atomic-ish."""

    def __init__(self, path: str, max_lines: int = 2000, worker: Optional[str] = None):
        self.path = Path(path)
        self.max_lines = max_lines
        # Worker name autoset from env so dashboard can attribute pushes
        self.worker = (
            worker
            or os.environ.get("WORKER_NAME")
            or ("jarvis-synth-alpaca" if "alpaca" in str(self.path) else "jarvis-synth")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: Dict[str, Any]) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
        try:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("cycle_log_append_failed", error=str(e))

        # Mirror to dashboard webhook in a daemon thread (never block the pipeline)
        payload = {"worker": self.worker, **entry}
        threading.Thread(
            target=_push_to_dashboard, args=(payload,), daemon=True
        ).start()

        # Best-effort truncation when file grows too big
        try:
            if self.path.stat().st_size > 4 * 1024 * 1024:  # >4MB
                self._compact()
        except Exception:
            pass

    def _compact(self) -> None:
        lines = self.tail(self.max_lines)
        with self.path.open("w") as f:
            for entry in lines:
                f.write(json.dumps(entry) + "\n")

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r") as f:
                buf: deque[str] = deque(f, maxlen=int(n))
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for line in buf:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


def default_log(env_var: str = "CYCLE_LOG_PATH") -> CycleLog:
    path = os.environ.get(env_var, "/app/data/cycle_log.jsonl").strip()
    return CycleLog(path=path)
