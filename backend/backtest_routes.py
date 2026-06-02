"""/api/backtest/* — historical replay of the JARVIS signal pipeline."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

import backtest_engine as bt

log = logging.getLogger("backtest_routes")

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str = Field(..., description="JARVIS symbol e.g. EUR_USD, BTC/USD, NVDA")
    period: str = Field("60d", description="yfinance period: 30d, 60d, 180d, 1y, 2y")
    interval: str = Field("1h", description="yfinance interval: 1h, 4h, 1d")
    base_units: int = Field(1000, ge=1, le=100000)
    use_tauric: bool = Field(False, description="If true, calls Claude (capped to max_llm_calls)")
    max_llm_calls: int = Field(50, ge=0, le=500)


_active_runs: dict[str, dict] = {}


async def _run_and_save(db, payload: BacktestRequest, run_id: str):
    """Background runner — persists result on completion."""
    _active_runs[run_id] = {
        "status": "running", "symbol": payload.symbol,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = await bt.run_backtest(
            symbol=payload.symbol,
            period=payload.period,
            interval=payload.interval,
            base_units=payload.base_units,
            use_tauric=payload.use_tauric,
            max_llm_calls=payload.max_llm_calls,
        )
        doc = asdict(result)
        doc["_id"] = run_id
        doc["request"] = payload.model_dump()
        await db.backtest_runs.replace_one({"_id": run_id}, doc, upsert=True)
        _active_runs[run_id] = {
            "status": "done", "symbol": payload.symbol,
            "finished_at": doc.get("finished_at"),
            "win_rate": doc.get("win_rate"), "trades": doc.get("total_trades"),
        }
    except Exception as e:
        log.exception("backtest_run_failed")
        _active_runs[run_id] = {"status": "error", "error": str(e)}


class TuneRequest(BaseModel):
    symbol: str
    period: str = "180d"
    interval: str = "1h"
    base_units: int = Field(1000, ge=1, le=100000)


_tune_runs: dict[str, dict] = {}


async def _run_tune_and_save(db, payload: TuneRequest, run_id: str):
    _tune_runs[run_id] = {"status": "running", "symbol": payload.symbol,
                          "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        out = await bt.run_tune(
            symbol=payload.symbol, period=payload.period,
            interval=payload.interval, base_units=payload.base_units,
        )
        doc = {**out, "_id": run_id, "request": payload.model_dump()}
        await db.backtest_tunes.replace_one({"_id": run_id}, doc, upsert=True)
        _tune_runs[run_id] = {
            "status": "done", "symbol": payload.symbol,
            "finished_at": doc.get("finished_at"),
            "best": doc.get("best"),
            "combos_tested": doc.get("combos_tested"),
        }
    except Exception as e:
        log.exception("tune_run_failed")
        _tune_runs[run_id] = {"status": "error", "error": str(e)}


def build_router(db) -> APIRouter:
    """Bind the router to a Motor db handle and return it for inclusion."""

    @router.post("/run")
    async def run(payload: BacktestRequest, background: BackgroundTasks):
        import uuid as _uuid
        run_id = _uuid.uuid4().hex[:12]
        background.add_task(_run_and_save, db, payload, run_id)
        _active_runs[run_id] = {"status": "queued", "symbol": payload.symbol}
        return {"run_id": run_id, "status": "queued"}

    @router.get("/active")
    async def active():
        return {"runs": _active_runs}

    @router.get("/runs")
    async def list_runs(limit: int = 25):
        cursor = db.backtest_runs.find(
            {}, {"_id": 1, "symbol": 1, "win_rate": 1, "total_trades": 1,
                 "total_pl_pct": 1, "max_drawdown_pct": 1, "expectancy": 1,
                 "use_tauric": 1, "finished_at": 1, "elapsed_seconds": 1,
                 "request": 1, "error": 1, "bars": 1}
        ).sort("finished_at", -1).limit(int(limit))
        out = []
        async for d in cursor:
            d["run_id"] = d.pop("_id")
            out.append(d)
        return {"runs": out}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        d = await db.backtest_runs.find_one({"_id": run_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="run not found")
        return d

    @router.post("/tune")
    async def tune(payload: TuneRequest, background: BackgroundTasks):
        import uuid as _uuid
        run_id = _uuid.uuid4().hex[:12]
        background.add_task(_run_tune_and_save, db, payload, run_id)
        _tune_runs[run_id] = {"status": "queued", "symbol": payload.symbol}
        return {"tune_id": run_id, "status": "queued"}

    @router.get("/tunes/active")
    async def tunes_active():
        return {"runs": _tune_runs}

    @router.get("/tunes/{tune_id}")
    async def get_tune(tune_id: str):
        d = await db.backtest_tunes.find_one({"_id": tune_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="tune not found")
        return d

    return router
