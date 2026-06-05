"""Shadow Pod Telemetry — live multi-agent observability (Magents-style).

Every SHADOW_INTERVAL_S, fetches recent bars (yfinance) for each tracked
instrument and runs Pod A/B/C on them. Results land in MongoDB collection
`shadow_votes` so the dashboard can show what the ensemble is "thinking"
in real time.

This is OBSERVABILITY ONLY — no orders, no worker mutations. The point is to
collect live evidence of whether the 3-pod ensemble actually beats single-pod
on live data before any promotion to paper trading.

Tracked instruments + cadence are intentionally small to keep yfinance load low:
  • 7 instruments × every 5 minutes  →  ~84 votes/hr, ~2K/day
  • Last 200 votes per symbol retained (rolling)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

import backtest_engine as bt
import strategy_pods as sp

log = logging.getLogger("shadow_pods")

# Small representative basket — keeps yfinance calls tame and lets us cover
# all 3 asset classes (forex, crypto, stocks) for cross-class validation.
TRACKED_INSTRUMENTS = [
    "EUR_USD", "GBP_USD", "XAU_USD",
    "BTC/USD", "ETH/USD",
    "NVDA", "TSLA",
]

SHADOW_INTERVAL_S = int(os.environ.get("SHADOW_INTERVAL_S", "300"))      # 5 min
SHADOW_BARS_PERIOD = os.environ.get("SHADOW_BARS_PERIOD", "10d")
SHADOW_BARS_INTERVAL = os.environ.get("SHADOW_BARS_INTERVAL", "1h")
SHADOW_RETAIN_PER_SYMBOL = int(os.environ.get("SHADOW_RETAIN_PER_SYMBOL", "200"))


async def _fetch_bars_safe(symbol: str) -> Optional[Dict[str, np.ndarray]]:
    """Pull recent bars via the same code path the backtester uses (yfinance).

    Returns dict of closes/highs/lows numpy arrays, or None on any failure
    (network, no data, throttling). Failures are swallowed so the loop keeps
    ticking other symbols.
    """
    try:
        yf_sym = bt.map_symbol(symbol)
        df = await asyncio.to_thread(bt._fetch_bars, yf_sym, SHADOW_BARS_PERIOD, SHADOW_BARS_INTERVAL)
        df = df.dropna(subset=["close", "high", "low"]).reset_index(drop=True)
        if len(df) < 50:
            return None
        return {
            "closes": df["close"].astype(float).to_numpy(),
            "highs": df["high"].astype(float).to_numpy(),
            "lows": df["low"].astype(float).to_numpy(),
        }
    except Exception as e:
        log.debug("shadow fetch failed %s: %s", symbol, e)
        return None


async def _run_one_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    bars = await _fetch_bars_safe(symbol)
    if bars is None:
        return None
    out = await sp.vote_concurrently(
        bars["closes"], bars["highs"], bars["lows"],
        per_pod_timeout_s=10.0,
    )
    pods = out["pods"]
    ens = out["ensemble"]
    return {
        "symbol": symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ensemble": {
            "action": ens["action"],
            "confidence": ens["confidence"],
            "agreeing_pods": ens["agreeing_pods"],
        },
        "pods": {
            "A": {"action": pods["A"]["action"], "confidence": pods["A"]["confidence"]},
            "B": {"action": pods["B"]["action"], "confidence": pods["B"]["confidence"]},
            "C": {"action": pods["C"]["action"], "confidence": pods["C"]["confidence"]},
        },
        "last_close": float(bars["closes"][-1]),
    }


async def _persist(db, doc: Dict[str, Any]) -> None:
    await db.shadow_votes.insert_one(doc)
    # Keep only last N per symbol — find the (N+1)th-newest _id and drop older.
    cursor = db.shadow_votes.find(
        {"symbol": doc["symbol"]}, {"_id": 1}
    ).sort("_id", -1).skip(SHADOW_RETAIN_PER_SYMBOL).limit(1)
    async for cutoff in cursor:
        await db.shadow_votes.delete_many({
            "symbol": doc["symbol"], "_id": {"$lt": cutoff["_id"]},
        })


async def _tick(db) -> int:
    """Run one cycle across all tracked instruments. Returns count persisted."""
    saved = 0
    # Stagger by symbol — gentle on yfinance rate-limits.
    for symbol in TRACKED_INSTRUMENTS:
        try:
            doc = await _run_one_symbol(symbol)
            if doc is None:
                continue
            await _persist(db, doc)
            saved += 1
        except Exception as e:
            log.warning("shadow tick failed for %s: %s", symbol, e)
        await asyncio.sleep(0.8)  # tiny gap between symbol fetches
    return saved


async def shadow_loop(db) -> None:
    """Background task — runs `_tick(db)` every SHADOW_INTERVAL_S seconds.

    Cancellation-safe: SIGTERM/Ctrl+C lets the current cycle finish then exits.
    """
    log.info("shadow_pods_loop_started interval=%ss instruments=%d",
             SHADOW_INTERVAL_S, len(TRACKED_INSTRUMENTS))
    # First tick: small delay so startup isn't slammed.
    await asyncio.sleep(8)
    while True:
        try:
            saved = await _tick(db)
            log.info("shadow_tick saved=%d/%d", saved, len(TRACKED_INSTRUMENTS))
        except asyncio.CancelledError:
            log.info("shadow_pods_loop_cancelled")
            raise
        except Exception as e:
            log.warning("shadow tick errored: %s", e)
        try:
            await asyncio.sleep(SHADOW_INTERVAL_S)
        except asyncio.CancelledError:
            log.info("shadow_pods_loop_cancelled")
            raise


# ---------- read helpers (used by routes) -----------------------------------

async def latest_per_symbol(db) -> List[Dict[str, Any]]:
    """Return the most recent vote for each tracked instrument."""
    out: List[Dict[str, Any]] = []
    for symbol in TRACKED_INSTRUMENTS:
        d = await db.shadow_votes.find_one(
            {"symbol": symbol}, {"_id": 0}, sort=[("ts", -1)],
        )
        if d:
            out.append(d)
        else:
            out.append({"symbol": symbol, "ts": None, "ensemble": None, "pods": None})
    return out


async def recent_history(db, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    cursor = db.shadow_votes.find({"symbol": symbol}, {"_id": 0}).sort("ts", -1).limit(int(limit))
    return [d async for d in cursor]


async def agreement_tally(db, hours: int = 24) -> Dict[str, Any]:
    """How often (per symbol, last N hours) did the ensemble actually fire LONG/SHORT
    vs HOLD? Tells us if the 2-of-3 gate is too strict on live data.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"symbol": "$symbol", "action": "$ensemble.action"},
            "count": {"$sum": 1},
        }},
    ]
    by_symbol: Dict[str, Dict[str, int]] = {}
    async for row in db.shadow_votes.aggregate(pipeline):
        sym = row["_id"]["symbol"]
        action = row["_id"]["action"] or "HOLD"
        by_symbol.setdefault(sym, {"LONG": 0, "SHORT": 0, "HOLD": 0, "total": 0})
        by_symbol[sym][action] = row["count"]
        by_symbol[sym]["total"] += row["count"]
    # Compute agreement-rate (LONG+SHORT) / total per symbol
    for sym, d in by_symbol.items():
        actionable = d["LONG"] + d["SHORT"]
        d["agreement_rate_pct"] = round((actionable / d["total"]) * 100.0, 2) if d["total"] else 0.0
    return {
        "hours": hours,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "by_symbol": by_symbol,
    }
