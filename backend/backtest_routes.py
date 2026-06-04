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


class EnsembleRequest(BaseModel):
    symbol: str
    period: str = "60d"
    interval: str = "1h"
    base_units: int = Field(1000, ge=1, le=100000)
    tauric_floor: int = Field(8, ge=1, le=10)
    upside_high: float = Field(0.70, ge=0.5, le=0.95)
    upside_low: float = Field(0.30, ge=0.05, le=0.5)
    atr_mult: float = Field(1.5, ge=0.5, le=4.0)
    rr_base: float = Field(2.0, ge=0.5, le=5.0)
    per_pod_timeout_s: float = Field(30.0, ge=1.0, le=120.0)


class CompareRequest(BaseModel):
    """Run Tauric-only AND 3-pod ensemble on the same symbol/window — head-to-head."""
    symbol: str
    period: str = "180d"
    interval: str = "1h"
    base_units: int = Field(1000, ge=1, le=100000)
    tauric_floor: int = Field(8, ge=1, le=10)
    upside_high: float = Field(0.70, ge=0.5, le=0.95)
    upside_low: float = Field(0.30, ge=0.05, le=0.5)
    atr_mult: float = Field(1.5, ge=0.5, le=4.0)
    rr_base: float = Field(2.0, ge=0.5, le=5.0)


_ensemble_runs: dict[str, dict] = {}
_compare_runs: dict[str, dict] = {}


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


async def _run_ensemble_and_save(db, payload: EnsembleRequest, run_id: str):
    _ensemble_runs[run_id] = {"status": "running", "symbol": payload.symbol,
                              "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        out = await bt.run_backtest_ensemble(
            symbol=payload.symbol, period=payload.period, interval=payload.interval,
            base_units=payload.base_units,
            tauric_floor=payload.tauric_floor,
            upside_high=payload.upside_high,
            upside_low=payload.upside_low,
            atr_mult=payload.atr_mult,
            rr_base=payload.rr_base,
            per_pod_timeout_s=payload.per_pod_timeout_s,
        )
        doc = asdict(out)
        doc["_id"] = run_id
        doc["request"] = payload.model_dump()
        await db.backtest_ensembles.replace_one({"_id": run_id}, doc, upsert=True)
        _ensemble_runs[run_id] = {
            "status": "done", "symbol": payload.symbol,
            "finished_at": doc.get("finished_at"),
            "win_rate": doc.get("win_rate"),
            "trades": doc.get("total_trades"),
            "profit_factor": doc.get("profit_factor"),
            "sharpe_ratio": doc.get("sharpe_ratio"),
            "max_drawdown_pct": doc.get("max_drawdown_pct"),
        }
    except Exception as e:
        log.exception("ensemble_run_failed")
        _ensemble_runs[run_id] = {"status": "error", "error": str(e)}


async def _run_compare_and_save(db, payload: CompareRequest, run_id: str):
    """Run Tauric-only and ensemble back-to-back on the SAME window, then summarize."""
    _compare_runs[run_id] = {"status": "running", "symbol": payload.symbol,
                             "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        # Sequential (not parallel) — yfinance throttles on parallel downloads of
        # the same ticker, and the second run reuses the cached HTTP response.
        single = await bt.run_backtest(
            symbol=payload.symbol, period=payload.period, interval=payload.interval,
            base_units=payload.base_units, use_tauric=False,
            tauric_floor=payload.tauric_floor,
            upside_high=payload.upside_high,
            upside_low=payload.upside_low,
            atr_mult=payload.atr_mult,
            rr_base=payload.rr_base,
        )
        ensemble = await bt.run_backtest_ensemble(
            symbol=payload.symbol, period=payload.period, interval=payload.interval,
            base_units=payload.base_units,
            tauric_floor=payload.tauric_floor,
            upside_high=payload.upside_high,
            upside_low=payload.upside_low,
            atr_mult=payload.atr_mult,
            rr_base=payload.rr_base,
        )

        def _summary(r) -> dict:
            return {
                "total_trades": r.total_trades,
                "win_rate": round(r.win_rate, 2),
                "expectancy": round(r.expectancy, 3),
                "total_pl_pct": round(r.total_pl_pct, 2),
                "profit_factor": r.profit_factor,
                "sharpe_ratio": r.sharpe_ratio,
                "max_drawdown_pct": round(r.max_drawdown_pct, 2),
                "elapsed_seconds": round(r.elapsed_seconds, 2),
                "error": r.error,
            }

        single_s = _summary(single)
        ens_s = _summary(ensemble)
        # Headline: did ensemble beat single-pod on the 4 promote-gate metrics?
        # Cast to plain Python bool — numpy.bool_ is not BSON-encodable.
        promote_gate = {
            "win_rate_up": bool(ens_s["win_rate"] > single_s["win_rate"]),
            "profit_factor_up": bool(ens_s["profit_factor"] > single_s["profit_factor"]),
            "sharpe_up": bool(ens_s["sharpe_ratio"] > single_s["sharpe_ratio"]),
            "drawdown_down": bool(ens_s["max_drawdown_pct"] < single_s["max_drawdown_pct"]),
        }
        promote = bool(sum(promote_gate.values()) >= 3)  # ≥3 of 4 must improve

        doc = {
            "_id": run_id,
            "symbol": payload.symbol,
            "period": payload.period,
            "interval": payload.interval,
            "request": payload.model_dump(),
            "single_pod": single_s,
            "ensemble": ens_s,
            "promote_gate": promote_gate,
            "promote_to_paper": promote,
            "started_at": _compare_runs[run_id]["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.backtest_compares.replace_one({"_id": run_id}, doc, upsert=True)
        _compare_runs[run_id] = {
            "status": "done", "symbol": payload.symbol,
            "finished_at": doc["finished_at"],
            "promote_to_paper": promote,
            "promote_gate": promote_gate,
            "single_pod": single_s,
            "ensemble": ens_s,
        }
    except Exception as e:
        log.exception("compare_run_failed")
        _compare_runs[run_id] = {"status": "error", "error": str(e)}


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

    # ----- Ensemble (3-pod) endpoints -----------------------------------

    @router.post("/ensemble/run")
    async def ensemble_run(payload: EnsembleRequest, background: BackgroundTasks):
        import uuid as _uuid
        run_id = _uuid.uuid4().hex[:12]
        background.add_task(_run_ensemble_and_save, db, payload, run_id)
        _ensemble_runs[run_id] = {"status": "queued", "symbol": payload.symbol}
        return {"run_id": run_id, "status": "queued"}

    @router.get("/ensemble/active")
    async def ensemble_active():
        return {"runs": _ensemble_runs}

    @router.get("/ensemble/runs/{run_id}")
    async def ensemble_get(run_id: str):
        d = await db.backtest_ensembles.find_one({"_id": run_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="ensemble run not found")
        return d

    @router.post("/ensemble/compare")
    async def ensemble_compare(payload: CompareRequest, background: BackgroundTasks):
        """Run single-pod (Pod A only) + 3-pod ensemble on the SAME window."""
        import uuid as _uuid
        run_id = _uuid.uuid4().hex[:12]
        background.add_task(_run_compare_and_save, db, payload, run_id)
        _compare_runs[run_id] = {"status": "queued", "symbol": payload.symbol}
        return {"compare_id": run_id, "status": "queued"}

    @router.get("/ensemble/compares/active")
    async def ensemble_compares_active():
        return {"runs": _compare_runs}

    @router.get("/ensemble/compares/{compare_id}")
    async def ensemble_compare_get(compare_id: str):
        d = await db.backtest_compares.find_one({"_id": compare_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="compare run not found")
        return d

    return router
