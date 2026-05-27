"""Pre-execution Risk-Off gate.

Optional integration: when `DASHBOARD_RISK_STATUS_URL` is set (e.g.
`https://your-dashboard.preview.emergentagent.com/api/risk/status`), the worker
polls it before sending new entries. If `active=true` is returned, new
LONG/SHORT entries are vetoed (downgraded to HOLD). Existing positions and
their stop-losses are untouched.

Fails OPEN: if the dashboard is unreachable, we allow trades — the worker's
own guardrails (daily loss limit, kill switch) still apply.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("risk_gate")


@dataclass(frozen=True)
class RiskGateDecision:
    allowed: bool
    reason: str
    source: str  # "auto" | "manual" | "unreachable" | "disabled"


async def check(timeout_seconds: float = 4.0) -> RiskGateDecision:
    url = os.environ.get("DASHBOARD_RISK_STATUS_URL", "").strip()
    if not url:
        return RiskGateDecision(allowed=True, reason="risk-gate disabled", source="disabled")

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("risk_gate unreachable: %s — failing open", e)
        return RiskGateDecision(allowed=True, reason=f"risk-gate unreachable: {e}", source="unreachable")

    active = bool(data.get("active"))
    source = str(data.get("source") or "auto")
    reason = str(data.get("reason") or "")

    if active:
        return RiskGateDecision(
            allowed=False,
            reason=f"Risk-Off ACTIVE ({source}): {reason}",
            source=source,
        )

    return RiskGateDecision(
        allowed=True,
        reason=f"Risk-On (standby) — {reason}",
        source=source,
    )


def check_sync(timeout_seconds: float = 4.0) -> RiskGateDecision:
    """Synchronous helper for code paths that aren't async."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async loop — caller should use await check()
            return RiskGateDecision(allowed=True, reason="sync call inside async loop — skipping", source="disabled")
        return loop.run_until_complete(check(timeout_seconds))
    except RuntimeError:
        return asyncio.run(check(timeout_seconds))
