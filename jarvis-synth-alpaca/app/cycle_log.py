"""Append-only cycle decision log (JSON Lines) for read-only diagnostics.

Used by the sidecar `/cycles` endpoint so I can see what the bot decided
across restarts without you forwarding screenshots.
"""
from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

log = structlog.get_logger()


class CycleLog:
    """JSONL append-only ring log. Last-N is read tail-style; writes are atomic-ish."""

    def __init__(self, path: str, max_lines: int = 2000):
        self.path = Path(path)
        self.max_lines = max_lines
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: Dict[str, Any]) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        try:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("cycle_log_append_failed", error=str(e))
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
