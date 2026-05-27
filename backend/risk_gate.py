"""Risk-Off mode — auto-pauses new trade entries during BEAR + extreme-fear conditions.

State precedence (highest → lowest):
  1. Manual override stored in MongoDB collection `risk_state` (doc _id="main").
  2. Auto-evaluation: CMC regime + Fear & Greed.

Workers consume this by polling `/api/risk/status` before placing orders.
The dashboard reads it to show a banner + toggle the regime pill into Risk-Off mode.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import cmc_client as cmc

log = logging.getLogger("risk_gate")

_DOC_ID = "main"

# Thresholds for auto risk-off (only applied when no manual override is set).
BEAR_FG_THRESHOLD = 30   # Fear & Greed at or below this triggers auto risk-off in BEAR regimes.
CHOP_FG_THRESHOLD = 20   # In CHOP, only flip risk-off if F&G is in extreme fear territory.


async def _load_override(db) -> Optional[Dict[str, Any]]:
    doc = await db.risk_state.find_one({"_id": _DOC_ID}, {"_id": 0})
    if doc and doc.get("override") in ("on", "off"):
        return doc
    return None


async def _persist_override(db, mode: str, by: str = "user") -> Dict[str, Any]:
    """mode ∈ {'on', 'off', 'auto'} — 'auto' clears any manual override."""
    if mode not in ("on", "off", "auto"):
        raise ValueError("mode must be on|off|auto")

    now = datetime.now(timezone.utc).isoformat()
    if mode == "auto":
        await db.risk_state.update_one(
            {"_id": _DOC_ID},
            {"$set": {"override": None, "updated_at": now, "updated_by": by}},
            upsert=True,
        )
    else:
        await db.risk_state.update_one(
            {"_id": _DOC_ID},
            {"$set": {"override": mode, "since": now, "updated_at": now, "updated_by": by}},
            upsert=True,
        )
    return await db.risk_state.find_one({"_id": _DOC_ID}, {"_id": 0})


async def _evaluate_auto() -> Dict[str, Any]:
    """Pull live CMC signals and decide if auto risk-off should be active."""
    try:
        gm = await cmc.fetch("/v1/global-metrics/quotes/latest", {"convert": "USD"})
        fg = await cmc.fetch("/v3/fear-and-greed/latest", {})
    except RuntimeError as e:
        log.warning("risk_eval cmc unavailable: %s", e)
        return {
            "regime": "unknown",
            "fg_value": None,
            "auto_risk_off": False,
            "reason": "CMC unavailable — defaulting to risk-ON (allow trades).",
        }

    d = gm.get("data") or {}
    q = (d.get("quote") or {}).get("USD") or {}
    mc_pct_24h = q.get("total_market_cap_yesterday_percentage_change")
    fg_value = int((fg.get("data") or {}).get("value") or 50)

    regime = "chop"
    if mc_pct_24h is not None:
        if mc_pct_24h > 0.5 and fg_value >= 55:
            regime = "bull"
        elif mc_pct_24h < -0.5 or fg_value <= 30:
            regime = "bear"

    auto_off = False
    reason = "Market conditions look constructive — workers active."
    if regime == "bear" and fg_value <= BEAR_FG_THRESHOLD:
        auto_off = True
        reason = f"BEAR regime + Fear&Greed {fg_value} ≤ {BEAR_FG_THRESHOLD} — pausing new entries."
    elif fg_value <= CHOP_FG_THRESHOLD:
        auto_off = True
        reason = f"Extreme fear ({fg_value} ≤ {CHOP_FG_THRESHOLD}) — defensive mode."
    elif regime == "bear":
        reason = f"BEAR regime but Fear&Greed {fg_value} not extreme — workers still active."

    return {
        "regime": regime,
        "fg_value": fg_value,
        "mc_pct_24h": mc_pct_24h,
        "auto_risk_off": auto_off,
        "reason": reason,
    }


async def get_status(db) -> Dict[str, Any]:
    """Returns the full risk-gate status for dashboard + workers."""
    override = await _load_override(db)
    auto = await _evaluate_auto()

    if override and override.get("override") == "on":
        active = True
        source = "manual"
        reason = "Risk-Off forced ON manually — no new entries permitted."
    elif override and override.get("override") == "off":
        active = False
        source = "manual"
        reason = "Risk-Off forced OFF manually — workers active regardless of regime."
    else:
        active = auto["auto_risk_off"]
        source = "auto"
        reason = auto["reason"]

    return {
        "active": active,
        "source": source,
        "reason": reason,
        "regime": auto["regime"],
        "fg_value": auto["fg_value"],
        "mc_pct_24h": auto.get("mc_pct_24h"),
        "manual_override": override.get("override") if override else None,
        "since": override.get("since") if override and override.get("override") in ("on", "off") else None,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


async def set_override(db, mode: str, by: str = "user") -> Dict[str, Any]:
    await _persist_override(db, mode, by)
    return await get_status(db)
