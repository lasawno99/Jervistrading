"""Best-effort webhook to push profit-lock events to the JARVIS dashboard.

Posts to ``DASHBOARD_LOCK_WEBHOOK_URL`` with header ``X-Lock-Token``. All
errors are swallowed and logged — this MUST NOT break the trading loop if the
dashboard is down or unreachable.
"""
from __future__ import annotations

from typing import Optional

import httpx
import structlog

log = structlog.get_logger()


async def post_lock_event(
    *,
    webhook_url: Optional[str],
    webhook_token: Optional[str],
    timestamp: str,
    amount: float,
    nav_at_lock: float,
    baseline_before: float,
    baseline_after: float,
    timeout_seconds: float = 5.0,
) -> bool:
    """POST a single lock event. Returns True on 2xx, False otherwise.

    Idempotent on the dashboard side via the ``timestamp`` field.
    """
    if not webhook_url or not webhook_token:
        log.debug("dashboard_webhook_disabled")
        return False

    payload = {
        "timestamp": timestamp,
        "amount": float(amount),
        "nav_at_lock": float(nav_at_lock),
        "baseline_before": float(baseline_before),
        "baseline_after": float(baseline_after),
        "source": "jarvis-synth",
    }
    headers = {"X-Lock-Token": webhook_token, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            r = await client.post(webhook_url, json=payload, headers=headers)
        if 200 <= r.status_code < 300:
            log.info(
                "dashboard_webhook_ok",
                status=r.status_code,
                amount=amount,
                duplicate=("duplicate" in r.text),
            )
            return True
        log.warning(
            "dashboard_webhook_non2xx",
            status=r.status_code,
            body=r.text[:200],
        )
        return False
    except Exception as e:
        log.error("dashboard_webhook_failed", error=str(e))
        return False
