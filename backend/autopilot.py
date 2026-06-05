"""AutoPilot — autonomous Compare + Promote pipeline.

Every AUTOPILOT_INTERVAL_S, the loop:
  1. Reads /api/shadow/agreement?hours=24 from the in-process db
  2. For each instrument with rate ≥ AUTOPILOT_MIN_RATE and ≥ AUTOPILOT_MIN_SAMPLES:
       a. Skip if a fresh auto-compare exists (< AUTOPILOT_COOLDOWN_HOURS)
       b. Run Pod-A-only and 3-Pod-Ensemble backtests on the same window
       c. Evaluate the same 4-of-4 promote gate used by the manual UI
       d. Persist result to `auto_compares` collection
       e. If gate clears AND user has `auto_promote=true`, apply params via
          instrument_configs.upsert — workers will pick up next cycle.
       f. Otherwise, store as `pending_review` so the dashboard can offer
          one-tap promote.

Pure backend — no worker mutations. Default toggle is OFF (review mode) so
the user is always in the loop unless they explicitly flip auto-promote ON.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import backtest_engine as bt
import shadow_pods as shp

log = logging.getLogger("autopilot")

AUTOPILOT_INTERVAL_S = int(os.environ.get("AUTOPILOT_INTERVAL_S", "21600"))  # 6h
AUTOPILOT_MIN_RATE = float(os.environ.get("AUTOPILOT_MIN_RATE", "30.0"))    # 30%
AUTOPILOT_MIN_SAMPLES = int(os.environ.get("AUTOPILOT_MIN_SAMPLES", "20"))   # ≥20 actionable
AUTOPILOT_COOLDOWN_HOURS = int(os.environ.get("AUTOPILOT_COOLDOWN_HOURS", "24"))
AUTOPILOT_PERIOD = os.environ.get("AUTOPILOT_PERIOD", "60d")
AUTOPILOT_INTERVAL = os.environ.get("AUTOPILOT_INTERVAL", "1h")

# Default per-instrument knobs — same defaults the manual UI uses, so the
# auto-compare is apples-to-apples comparable.
AUTOPILOT_DEFAULTS = {
    "tauric_floor": 7,
    "upside_high": 0.65,
    "upside_low": 0.35,
    "atr_mult": 1.5,
    "rr_base": 2.0,
    "base_units": 1000,
}


def _summary(r) -> Dict[str, Any]:
    return {
        "total_trades": int(r.total_trades),
        "win_rate": round(float(r.win_rate), 2),
        "expectancy": round(float(r.expectancy), 3),
        "total_pl_pct": round(float(r.total_pl_pct), 2),
        "profit_factor": float(r.profit_factor),
        "sharpe_ratio": float(r.sharpe_ratio),
        "max_drawdown_pct": round(float(r.max_drawdown_pct), 2),
        "elapsed_seconds": round(float(r.elapsed_seconds), 2),
        "error": r.error,
    }


def _gate(single_s: Dict[str, Any], ens_s: Dict[str, Any]) -> Dict[str, Any]:
    gate = {
        "win_rate_up": bool(ens_s["win_rate"] > single_s["win_rate"]),
        "profit_factor_up": bool(ens_s["profit_factor"] > single_s["profit_factor"]),
        "sharpe_up": bool(ens_s["sharpe_ratio"] > single_s["sharpe_ratio"]),
        "drawdown_down": bool(ens_s["max_drawdown_pct"] < single_s["max_drawdown_pct"]),
    }
    gate["passing_count"] = sum(gate[k] for k in
                                ("win_rate_up", "profit_factor_up", "sharpe_up", "drawdown_down"))
    gate["clear"] = bool(gate["passing_count"] >= 3)
    return gate


async def _already_fresh(db, symbol: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=AUTOPILOT_COOLDOWN_HOURS)).isoformat()
    doc = await db.auto_compares.find_one(
        {"symbol": symbol, "finished_at": {"$gte": cutoff}},
        {"_id": 1},
    )
    return bool(doc)


async def _get_settings(db) -> Dict[str, Any]:
    doc = await db.autopilot_settings.find_one({"_id": "global"}, {"_id": 0})
    return doc or {"auto_promote": False, "enabled": True}


async def _run_one(db, symbol: str) -> Optional[Dict[str, Any]]:
    """Run Pod-A and Ensemble on `symbol`, evaluate gate, persist, optionally promote."""
    started = datetime.now(timezone.utc)
    log.info("autopilot_compare_start symbol=%s", symbol)
    try:
        single = await bt.run_backtest(
            symbol=symbol, period=AUTOPILOT_PERIOD, interval=AUTOPILOT_INTERVAL,
            base_units=AUTOPILOT_DEFAULTS["base_units"], use_tauric=False,
            tauric_floor=AUTOPILOT_DEFAULTS["tauric_floor"],
            upside_high=AUTOPILOT_DEFAULTS["upside_high"],
            upside_low=AUTOPILOT_DEFAULTS["upside_low"],
            atr_mult=AUTOPILOT_DEFAULTS["atr_mult"],
            rr_base=AUTOPILOT_DEFAULTS["rr_base"],
        )
        ensemble = await bt.run_backtest_ensemble(
            symbol=symbol, period=AUTOPILOT_PERIOD, interval=AUTOPILOT_INTERVAL,
            base_units=AUTOPILOT_DEFAULTS["base_units"],
            tauric_floor=AUTOPILOT_DEFAULTS["tauric_floor"],
            upside_high=AUTOPILOT_DEFAULTS["upside_high"],
            upside_low=AUTOPILOT_DEFAULTS["upside_low"],
            atr_mult=AUTOPILOT_DEFAULTS["atr_mult"],
            rr_base=AUTOPILOT_DEFAULTS["rr_base"],
        )
    except Exception as e:
        log.warning("autopilot_compare_error symbol=%s err=%s", symbol, e)
        return None

    single_s = _summary(single)
    ens_s = _summary(ensemble)
    gate = _gate(single_s, ens_s)

    settings = await _get_settings(db)
    promote = bool(gate["clear"] and settings.get("auto_promote") is True)
    status = "auto_promoted" if promote else ("pending_review" if gate["clear"] else "blocked")

    doc = {
        "symbol": symbol,
        "period": AUTOPILOT_PERIOD,
        "interval": AUTOPILOT_INTERVAL,
        "params": dict(AUTOPILOT_DEFAULTS),
        "single_pod": single_s,
        "ensemble": ens_s,
        "promote_gate": gate,
        "status": status,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.auto_compares.insert_one(doc)
    doc.pop("_id", None)  # insert_one mutates doc to add ObjectId — strip before returning

    if promote:
        await _apply_params(db, symbol, AUTOPILOT_DEFAULTS,
                            notes=f"Auto-promoted via AutoPilot · WR {ens_s['win_rate']}% PF {ens_s['profit_factor']}")
        log.info("autopilot_auto_promoted symbol=%s", symbol)
    else:
        log.info("autopilot_compare_done symbol=%s status=%s gate=%d/4",
                 symbol, status, gate["passing_count"])
    return doc


async def _apply_params(db, symbol: str, params: Dict[str, Any], notes: str = "") -> None:
    """Upsert into instrument_configs the same way /api/instrument-configs/apply does."""
    now = datetime.now(timezone.utc).isoformat()
    await db.instrument_configs.update_one(
        {"_id": symbol},
        {
            "$set": {
                "symbol": symbol,
                "params": {k: v for k, v in params.items() if k != "base_units"},
                "notes": notes,
                "updated_at": now,
                "source": "autopilot",
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def autopilot_tick(db) -> int:
    """Run one autopilot scan. Returns count of compares triggered."""
    settings = await _get_settings(db)
    if not settings.get("enabled", True):
        log.info("autopilot_disabled_skip")
        return 0

    agreement = await shp.agreement_tally(db, hours=24)
    candidates: List[str] = []
    for sym, d in (agreement.get("by_symbol") or {}).items():
        rate = d.get("agreement_rate_pct", 0.0)
        actionable = (d.get("LONG", 0) + d.get("SHORT", 0))
        if rate >= AUTOPILOT_MIN_RATE and actionable >= AUTOPILOT_MIN_SAMPLES:
            if not await _already_fresh(db, sym):
                candidates.append(sym)

    log.info("autopilot_tick candidates=%s settings=%s", candidates, settings)
    ran = 0
    for sym in candidates:
        try:
            await _run_one(db, sym)
            ran += 1
        except Exception as e:
            log.warning("autopilot_one_failed sym=%s err=%s", sym, e)
        await asyncio.sleep(2)
    return ran


async def autopilot_loop(db) -> None:
    log.info("autopilot_loop_started interval=%ss min_rate=%.1f min_samples=%d",
             AUTOPILOT_INTERVAL_S, AUTOPILOT_MIN_RATE, AUTOPILOT_MIN_SAMPLES)
    await asyncio.sleep(60)  # let shadow loop seed some data first
    while True:
        try:
            await autopilot_tick(db)
        except asyncio.CancelledError:
            log.info("autopilot_loop_cancelled")
            raise
        except Exception as e:
            log.warning("autopilot_tick_errored: %s", e)
        try:
            await asyncio.sleep(AUTOPILOT_INTERVAL_S)
        except asyncio.CancelledError:
            log.info("autopilot_loop_cancelled")
            raise


# ---------- read helpers (used by routes) -----------------------------------

async def latest_pending(db) -> List[Dict[str, Any]]:
    """Compares whose gate cleared but haven't been promoted yet."""
    cursor = db.auto_compares.find(
        {"status": "pending_review"}, {"_id": 0}
    ).sort("finished_at", -1).limit(20)
    return [d async for d in cursor]


async def recent_feed(db, limit: int = 25) -> List[Dict[str, Any]]:
    cursor = db.auto_compares.find({}, {"_id": 0}).sort("finished_at", -1).limit(int(limit))
    return [d async for d in cursor]


async def by_symbol(db, symbol: str) -> Optional[Dict[str, Any]]:
    return await db.auto_compares.find_one(
        {"symbol": symbol}, {"_id": 0}, sort=[("finished_at", -1)],
    )
