"""Calendar tool — STUB.

v2 will wire up Google Calendar for economic-event awareness.
"""
from __future__ import annotations

from datetime import datetime
from typing import List


def list_events(start: datetime, end: datetime) -> List[dict]:
    """List calendar events between two timestamps. Not implemented in v1.

    Args:
        start: Inclusive start of the lookup window (UTC).
        end: Exclusive end of the lookup window (UTC).

    Returns:
        A list of event dicts.

    Raises:
        NotImplementedError: Always, until v2.
    """
    raise NotImplementedError("Wire up Gmail/Calendar API in v2")
