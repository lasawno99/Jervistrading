"""/api/shadow/* — read-only access to live pod telemetry."""
from __future__ import annotations

from fastapi import APIRouter
import shadow_pods as sp


def build_router(db) -> APIRouter:
    router = APIRouter(prefix="/shadow", tags=["shadow"])

    @router.get("/latest")
    async def latest():
        """Most recent ensemble + per-pod vote for each tracked instrument."""
        rows = await sp.latest_per_symbol(db)
        return {"instruments": sp.TRACKED_INSTRUMENTS, "votes": rows}

    @router.get("/history/{symbol}")
    async def history(symbol: str, limit: int = 50):
        """Recent vote history for one symbol (newest first)."""
        # URL-decode common slash-syntax e.g. BTC%2FUSD
        symbol = symbol.replace("%2F", "/")
        rows = await sp.recent_history(db, symbol=symbol, limit=limit)
        return {"symbol": symbol, "votes": rows}

    @router.get("/agreement")
    async def agreement(hours: int = 24):
        """How often the ensemble fired LONG/SHORT (vs HOLD) per symbol in last N hours."""
        return await sp.agreement_tally(db, hours=hours)

    return router
