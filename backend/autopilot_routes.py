"""/api/autopilot/* — read + control the autonomous compare-promote pipeline."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

import autopilot as ap


class SettingsRequest(BaseModel):
    enabled: bool | None = None
    auto_promote: bool | None = None


class PromoteRequest(BaseModel):
    symbol: str


def build_router(db) -> APIRouter:
    router = APIRouter(prefix="/autopilot", tags=["autopilot"])

    @router.get("/status")
    async def status():
        settings = await ap._get_settings(db)
        pending = await ap.latest_pending(db)
        feed = await ap.recent_feed(db, limit=10)
        last = feed[0] if feed else None
        return {
            "settings": settings,
            "thresholds": {
                "min_rate_pct": ap.AUTOPILOT_MIN_RATE,
                "min_samples": ap.AUTOPILOT_MIN_SAMPLES,
                "cooldown_hours": ap.AUTOPILOT_COOLDOWN_HOURS,
                "interval_hours": ap.AUTOPILOT_INTERVAL_S / 3600,
                "period": ap.AUTOPILOT_PERIOD,
                "interval": ap.AUTOPILOT_INTERVAL,
            },
            "pending_count": len(pending),
            "pending": pending,
            "last_run": last.get("finished_at") if last else None,
            "recent": feed,
        }

    @router.post("/settings")
    async def update_settings(payload: SettingsRequest):
        current = await ap._get_settings(db)
        merged = dict(current)
        if payload.enabled is not None:
            merged["enabled"] = bool(payload.enabled)
        if payload.auto_promote is not None:
            merged["auto_promote"] = bool(payload.auto_promote)
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.autopilot_settings.update_one(
            {"_id": "global"}, {"$set": merged}, upsert=True,
        )
        return {"status": "updated", **merged}

    @router.post("/run-now")
    async def run_now(background: BackgroundTasks):
        """Trigger an immediate scan + compare cycle (out-of-schedule)."""
        background.add_task(ap.autopilot_tick, db)
        return {"status": "queued"}

    @router.post("/promote")
    async def promote(payload: PromoteRequest):
        """Manually promote a pending auto-compare (one-tap from the dashboard)."""
        last = await ap.by_symbol(db, payload.symbol)
        if not last:
            raise HTTPException(status_code=404, detail="no auto-compare found")
        if last["status"] not in ("pending_review", "auto_promoted"):
            raise HTTPException(
                status_code=409,
                detail=f"compare for {payload.symbol} is '{last['status']}', not promotable",
            )
        if not last.get("promote_gate", {}).get("clear"):
            raise HTTPException(status_code=409, detail="gate not clear")

        await ap._apply_params(
            db, payload.symbol, ap.AUTOPILOT_DEFAULTS,
            notes=f"Manually promoted via AutoPilot · "
                  f"WR {last['ensemble']['win_rate']}% PF {last['ensemble']['profit_factor']}",
        )
        # Flip the persisted doc's status so it disappears from `pending`.
        await db.auto_compares.update_many(
            {"symbol": payload.symbol, "status": "pending_review"},
            {"$set": {"status": "user_promoted",
                      "promoted_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"status": "promoted", "symbol": payload.symbol}

    @router.post("/dismiss")
    async def dismiss(payload: PromoteRequest):
        """Mark a pending compare as 'dismissed' so it stops showing up."""
        await db.auto_compares.update_many(
            {"symbol": payload.symbol, "status": "pending_review"},
            {"$set": {"status": "dismissed",
                      "dismissed_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"status": "dismissed", "symbol": payload.symbol}

    return router
