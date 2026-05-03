"""In-memory state: don't re-alert on the same (topic, stage) within a week."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class AlertState:
    """Key: (topic, stage). Value: unix-epoch seconds of last alert."""
    _sent: Dict[Tuple[str, str], float] = field(default_factory=dict)
    cooldown_seconds: float = 7 * 24 * 3600  # a week

    def should_send(self, topic: str, stage: str) -> bool:
        key = (topic, stage)
        last = self._sent.get(key)
        if last is None:
            return True
        return (time.time() - last) > self.cooldown_seconds

    def mark_sent(self, topic: str, stage: str) -> None:
        self._sent[(topic, stage)] = time.time()
