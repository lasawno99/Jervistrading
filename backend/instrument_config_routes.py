"""/api/instrument-configs/* — per-symbol parameter overrides.

The dashboard's Auto-Tune feature finds the best (Tauric, Upside, ATR, R:R) per
symbol. Once the user clicks "Apply to Live Workers", the winning config lands
here and the Railway workers (jarvis-synth, jarvis-synth-alpaca) pick it up on
their next cycle. No redeploy needed — pure feedback loop.

Storage: MongoDB collection `instrument_configs` with one document per symbol.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("instrument_configs")

router = APIRouter(prefix="/instrument-configs", tags=["instrument-configs"])


class ConfigParams(BaseModel):
    tauric_floor: int = Field(..., ge=1, le=10)
    upside_high: float = Field(..., gt=0.5, lt=1.0)
    upside_low: float = Field(..., gt=0.0, lt=0.5)
    atr_mult: float = Field(..., gt=0.0, le=10.0)
    rr_base: float = Field(..., gt=0.5, le=10.0)


class ApplyConfigRequest(BaseModel):
    symbol: str
    params: ConfigParams
    source_tune_id: Optional[str] = None
    notes: Optional[str] = None


def build_router(db) -> APIRouter:

    @router.get("")
    async def list_configs():
        """List ALL stored configs — workers fetch this once per cycle."""
        out: List[Dict[str, Any]] = []
        async for d in db.instrument_configs.find({}, {"_id": 0}):
            out.append(d)
        return {"configs": out, "count": len(out), "as_of": datetime.now(timezone.utc).isoformat()}

    @router.get("/by-symbol")
    async def get_config(symbol: str):
        d = await db.instrument_configs.find_one({"symbol": symbol}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail=f"no config for {symbol}")
        return d

    @router.post("/apply")
    async def apply_config(payload: ApplyConfigRequest):
        """Persist the best-tune config as the canonical override for this symbol."""
        doc = {
            "symbol": payload.symbol,
            "params": payload.params.model_dump(),
            "source_tune_id": payload.source_tune_id,
            "notes": payload.notes,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.instrument_configs.replace_one(
            {"symbol": payload.symbol}, doc, upsert=True
        )
        log.info("applied_config symbol=%s params=%s", payload.symbol, payload.params.model_dump())
        return {"status": "applied", "symbol": payload.symbol, "applied_at": doc["applied_at"], "params": doc["params"]}

    @router.delete("/by-symbol")
    async def delete_config(symbol: str):
        r = await db.instrument_configs.delete_one({"symbol": symbol})
        if r.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"no config for {symbol}")
        return {"status": "deleted", "symbol": symbol}

    return router
