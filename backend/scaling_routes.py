"""/api/scaling/* — instrument scaling readiness gate.

The user's P1 goal: scale jarvis-synth from 5 → 10 instruments, but ONLY when
the live system has proven itself (WR ≥ 40% across ≥ 20 closed trades).

This endpoint never modifies worker behavior. It only reports:
  • current closed-trade count + WR
  • whether the gate is clear
  • the proposed additional 5 instruments

Promoting (when the gate clears) writes the new INSTRUMENTS list to a
`scaling_state` doc that the dashboard can surface as a Railway env-var
command to copy-paste. Workers are NOT modified — by user direction.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("scaling_routes")

# Current live instruments (matches jarvis-synth Railway env defaults).
CURRENT_INSTRUMENTS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "XAU_USD"]

# Proposed +5 majors to scale up to 10 once the gate clears. Picked from OANDA
# tier-1 majors so they remain inside the practice account's instrument list.
PROPOSED_INSTRUMENTS = ["USD_CHF", "USD_CAD", "NZD_USD", "EUR_GBP", "EUR_JPY"]

GATE_MIN_TRADES = int(os.environ.get("SCALING_MIN_TRADES", "20"))
GATE_MIN_WR = float(os.environ.get("SCALING_MIN_WR", "40.0"))


class PromoteRequest(BaseModel):
    confirm: bool = True


def build_router(db) -> APIRouter:
    # Local router instance — multiple build_router() calls return independent
    # routers (essential for unit tests and for swappable dbs).
    router = APIRouter(prefix="/scaling", tags=["scaling"])

    @router.get("/readiness")
    async def readiness():
        """Report current trade stats + whether the scaling gate is clear."""
        total = await db.closed_trades.count_documents({})
        wins = await db.closed_trades.count_documents({"pl_pct": {"$gt": 0}})
        wr = (wins / total * 100.0) if total > 0 else 0.0

        # Are we already scaled? Honoured if the user previously promoted.
        promoted_doc = await db.scaling_state.find_one({"_id": "jarvis-synth"}, {"_id": 0})
        already_promoted = bool(promoted_doc and promoted_doc.get("promoted"))

        gate_clear = (total >= GATE_MIN_TRADES and wr >= GATE_MIN_WR)
        return {
            "worker": "jarvis-synth",
            "current_instruments": CURRENT_INSTRUMENTS,
            "proposed_instruments": PROPOSED_INSTRUMENTS,
            "scaled_instruments": CURRENT_INSTRUMENTS + PROPOSED_INSTRUMENTS,
            "stats": {
                "closed_trades": total,
                "wins": wins,
                "win_rate": round(wr, 2),
            },
            "gate": {
                "min_trades": GATE_MIN_TRADES,
                "min_win_rate": GATE_MIN_WR,
                "trades_ok": bool(total >= GATE_MIN_TRADES),
                "wr_ok": bool(wr >= GATE_MIN_WR),
                "clear": bool(gate_clear),
            },
            "already_promoted": already_promoted,
            "promoted_at": (promoted_doc or {}).get("promoted_at"),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    @router.post("/promote")
    async def promote(payload: PromoteRequest):
        """Record the user's decision to scale to 10 instruments.

        The gate MUST be clear or this is rejected. The worker still needs the
        Railway INSTRUMENTS env var updated — but this endpoint stores the
        decision + timestamp so the dashboard can show the exact command to copy.
        """
        if not payload.confirm:
            raise HTTPException(status_code=400, detail="confirm must be true")

        total = await db.closed_trades.count_documents({})
        wins = await db.closed_trades.count_documents({"pl_pct": {"$gt": 0}})
        wr = (wins / total * 100.0) if total > 0 else 0.0
        if total < GATE_MIN_TRADES or wr < GATE_MIN_WR:
            raise HTTPException(
                status_code=409,
                detail=f"scaling gate not clear: {total}/{GATE_MIN_TRADES} trades, "
                       f"{wr:.1f}%/{GATE_MIN_WR}% WR",
            )

        scaled = CURRENT_INSTRUMENTS + PROPOSED_INSTRUMENTS
        doc = {
            "_id": "jarvis-synth",
            "promoted": True,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "instruments": scaled,
            "snapshot_stats": {
                "closed_trades": total,
                "wins": wins,
                "win_rate": round(wr, 2),
            },
            "railway_env_command": f"INSTRUMENTS={','.join(scaled)}",
        }
        await db.scaling_state.replace_one({"_id": "jarvis-synth"}, doc, upsert=True)
        log.info("scaling_promoted instruments=%s trades=%d wr=%.2f", scaled, total, wr)
        return {"status": "promoted", **{k: v for k, v in doc.items() if k != "_id"}}

    return router
