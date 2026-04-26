"""Paper trading engine with AI-driven signals.

State persisted in MongoDB:
- paper_account: { _id: 'main', cash, equity, updated_at }
- paper_positions: { id, symbol, qty, entry, opened_at }
- paper_trades: { id, symbol, side, qty, price, ts }
- signals: { id, symbol, action, conviction, reason, status, ts, executed_at }
"""

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("trading")

UNIVERSE = {
    "BTC":  {"price": 71240.55, "vol": 0.018, "kind": "crypto"},
    "ETH":  {"price": 3812.15,  "vol": 0.022, "kind": "crypto"},
    "OIL":  {"price": 78.42,    "vol": 0.015, "kind": "commodity"},
    "GOLD": {"price": 2419.10,  "vol": 0.008, "kind": "commodity"},
    "TSLA": {"price": 248.33,   "vol": 0.025, "kind": "equity"},
    "NVDA": {"price": 138.82,   "vol": 0.022, "kind": "equity"},
}

# In-process price cache (random-walked each tick)
_prices: Dict[str, float] = {s: cfg["price"] for s, cfg in UNIVERSE.items()}
_last_change: Dict[str, float] = {s: 0.0 for s in UNIVERSE}


def tick_prices() -> Dict[str, dict]:
    out = {}
    for s, cfg in UNIVERSE.items():
        # random walk with mean reversion to base
        base = cfg["price"]
        cur = _prices[s]
        drift = random.gauss(0, cfg["vol"]) * base * 0.4
        # mean reversion pull
        cur = cur + drift + (base - cur) * 0.02
        change_pct = (cur - base) / base * 100
        _prices[s] = round(cur, 2)
        _last_change[s] = round(change_pct, 2)
        out[s] = {"price": _prices[s], "change_pct": _last_change[s], "kind": cfg["kind"]}
    return out


def current_price(symbol: str) -> float:
    return _prices.get(symbol, 0.0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- Account / positions ----------------

async def ensure_account(db) -> dict:
    acc = await db.paper_account.find_one({"_id": "main"})
    if acc:
        return acc
    acc = {"_id": "main", "cash": 100_000.0, "starting_cash": 100_000.0, "updated_at": now_iso()}
    await db.paper_account.insert_one(acc)
    return acc


async def get_positions(db) -> List[dict]:
    return await db.paper_positions.find({}, {"_id": 0}).to_list(100)


# ---------------- Risk controls ----------------

DEFAULT_RISK = {
    "_id": "risk",
    "max_position_notional": 25000.0,
    "max_daily_loss": 5000.0,
    "kill_switch": False,
}


async def get_risk(db) -> dict:
    r = await db.settings.find_one({"_id": "risk"})
    if r:
        r.pop("_id", None)
        return {**{k: v for k, v in DEFAULT_RISK.items() if k != "_id"}, **r}
    await db.settings.insert_one(dict(DEFAULT_RISK))
    return {k: v for k, v in DEFAULT_RISK.items() if k != "_id"}


async def update_risk(db, payload: dict) -> dict:
    allowed = {"max_position_notional", "max_daily_loss", "kill_switch"}
    update = {k: v for k, v in payload.items() if k in allowed}
    if not update:
        return await get_risk(db)
    await db.settings.update_one({"_id": "risk"}, {"$set": update}, upsert=True)
    return await get_risk(db)


async def _today_realized_loss(db) -> float:
    """Best-effort: sum of (sell proceeds - matching cost basis) for trades today.
    Simpler proxy: today's equity drawdown vs starting cash today.
    We use: starting_cash - current_equity if negative trades dominate.
    """
    eq = await compute_equity(db)
    return max(0.0, -eq["total_pl"])  # treat any negative P/L as loss for kill-switch check


async def check_risk(db, symbol: str, side: str, qty: float, price: float) -> Optional[str]:
    """Return None if OK, else error string."""
    risk = await get_risk(db)
    if risk["kill_switch"]:
        return "kill switch is engaged. all new trading halted."
    if side == "buy":
        # max position notional after this trade
        pos = await db.paper_positions.find_one({"symbol": symbol})
        post_qty = (pos["qty"] if pos else 0) + qty
        post_notional = post_qty * price
        if post_notional > risk["max_position_notional"]:
            return f"would exceed max position notional ${risk['max_position_notional']:,.0f} ({symbol} would be ${post_notional:,.2f})"
    # daily loss kill
    loss = await _today_realized_loss(db)
    if loss > risk["max_daily_loss"]:
        return f"daily loss cap hit (${loss:,.2f} > ${risk['max_daily_loss']:,.0f}). new orders blocked."
    return None


# ---------------- Equity curve ----------------

async def snapshot_equity(db) -> dict:
    eq = await compute_equity(db)
    point = {
        "ts": now_iso(),
        "equity": eq["equity"],
        "cash": eq["cash"],
        "pl": eq["total_pl"],
    }
    await db.equity_curve.insert_one(dict(point))
    return point


async def get_equity_curve(db, limit: int = 200) -> List[dict]:
    docs = await db.equity_curve.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
    return list(reversed(docs))


async def compute_equity(db) -> dict:
    acc = await ensure_account(db)
    positions = await get_positions(db)
    pos_value = 0.0
    enriched = []
    for p in positions:
        cp = current_price(p["symbol"])
        mv = cp * p["qty"]
        pl = (cp - p["entry"]) * p["qty"]
        pl_pct = ((cp / p["entry"]) - 1) * 100 if p["entry"] else 0
        pos_value += mv
        enriched.append({**p, "current_price": cp, "market_value": round(mv, 2), "pl": round(pl, 2), "pl_pct": round(pl_pct, 2)})
    equity = acc["cash"] + pos_value
    total_pl = equity - acc["starting_cash"]
    total_pl_pct = (total_pl / acc["starting_cash"]) * 100
    return {
        "cash": round(acc["cash"], 2),
        "starting_cash": acc["starting_cash"],
        "equity": round(equity, 2),
        "total_pl": round(total_pl, 2),
        "total_pl_pct": round(total_pl_pct, 2),
        "positions": enriched,
    }


async def execute_trade(db, symbol: str, side: str, qty: float, price: Optional[float] = None, source: str = "manual") -> dict:
    """Execute a paper trade. side in {buy, sell}."""
    symbol = symbol.upper()
    if symbol not in UNIVERSE:
        return {"ok": False, "error": f"Unknown symbol {symbol}. Universe: {list(UNIVERSE.keys())}"}
    if qty <= 0:
        return {"ok": False, "error": "qty must be > 0"}

    px = price or current_price(symbol)
    # Risk check
    err = await check_risk(db, symbol, side, qty, px)
    if err:
        return {"ok": False, "error": err}
    acc = await ensure_account(db)
    cost = px * qty

    if side == "buy":
        if acc["cash"] < cost:
            return {"ok": False, "error": f"Insufficient cash. Have ${acc['cash']:.2f}, need ${cost:.2f}"}
        # Update or open position
        existing = await db.paper_positions.find_one({"symbol": symbol})
        if existing:
            new_qty = existing["qty"] + qty
            new_entry = ((existing["entry"] * existing["qty"]) + cost) / new_qty
            await db.paper_positions.update_one(
                {"symbol": symbol},
                {"$set": {"qty": new_qty, "entry": round(new_entry, 4), "updated_at": now_iso()}},
            )
        else:
            await db.paper_positions.insert_one({
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "qty": qty,
                "entry": px,
                "opened_at": now_iso(),
                "updated_at": now_iso(),
            })
        await db.paper_account.update_one({"_id": "main"}, {"$set": {"cash": acc["cash"] - cost, "updated_at": now_iso()}})
    elif side == "sell":
        existing = await db.paper_positions.find_one({"symbol": symbol})
        if not existing or existing["qty"] < qty:
            have = existing["qty"] if existing else 0
            return {"ok": False, "error": f"Insufficient position. Have {have} {symbol}"}
        new_qty = existing["qty"] - qty
        if new_qty <= 1e-9:
            await db.paper_positions.delete_one({"symbol": symbol})
        else:
            await db.paper_positions.update_one({"symbol": symbol}, {"$set": {"qty": new_qty, "updated_at": now_iso()}})
        proceeds = px * qty
        await db.paper_account.update_one({"_id": "main"}, {"$set": {"cash": acc["cash"] + proceeds, "updated_at": now_iso()}})
    else:
        return {"ok": False, "error": f"Unknown side {side}"}

    trade = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": px,
        "value": round(px * qty, 2),
        "source": source,
        "ts": now_iso(),
    }
    await db.paper_trades.insert_one(dict(trade))
    return {"ok": True, "trade": trade}


# ---------------- Signals ----------------

async def list_signals(db, limit: int = 20) -> List[dict]:
    return await db.signals.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)


async def list_trades(db, limit: int = 20) -> List[dict]:
    return await db.paper_trades.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)


async def generate_signal(db, kimi_call) -> Optional[dict]:
    """Generate one trading signal. Uses Kimi if provided, else heuristic."""
    tick_prices()
    # Pick the symbol with biggest absolute % change as candidate
    candidates = sorted(_last_change.items(), key=lambda kv: abs(kv[1]), reverse=True)
    if not candidates:
        return None
    sym, ch = candidates[0]
    price = current_price(sym)

    # Heuristic: strong negative move -> BUY (mean revert), strong positive -> SELL
    if ch < -0.5:
        action = "BUY"
        reason_h = f"{sym} down {ch:.2f}% — oversold mean-revert candidate."
    elif ch > 0.6:
        action = "SELL"
        reason_h = f"{sym} up {ch:.2f}% — take partial profits, momentum exhaustion."
    else:
        action = "HOLD"
        reason_h = f"{sym} drift {ch:.2f}% — no edge."

    conviction = min(0.95, abs(ch) / 3)
    reason = reason_h
    if kimi_call:
        try:
            prompt = (
                f"You are a quant trading agent. Symbol: {sym}, price: ${price:.2f}, "
                f"24h change: {ch:.2f}%. Heuristic suggests {action}. "
                f"Respond in ONE sentence (max 25 words) with rationale, no markdown."
            )
            ai_reason = await kimi_call(prompt)
            if ai_reason:
                reason = ai_reason.strip()
        except Exception as e:
            logger.warning(f"Kimi signal call failed: {e}")

    if action == "HOLD":
        return None  # don't push hold signals

    # Position sizing: 5% of account on conviction
    acc = await ensure_account(db)
    notional = max(500, acc["cash"] * 0.05 * conviction)
    qty = round(notional / price, 6 if price < 100 else 4)

    sig = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "action": action,
        "qty": qty,
        "price": price,
        "change_pct": ch,
        "conviction": round(conviction, 2),
        "reason": reason,
        "status": "pending",
        "ts": now_iso(),
    }
    await db.signals.insert_one(dict(sig))
    return sig


async def execute_signal(db, signal_id: str) -> dict:
    sig = await db.signals.find_one({"id": signal_id}, {"_id": 0})
    if not sig:
        return {"ok": False, "error": "signal not found"}
    if sig["status"] != "pending":
        return {"ok": False, "error": f"signal already {sig['status']}"}
    side = "buy" if sig["action"] == "BUY" else "sell"
    res = await execute_trade(db, sig["symbol"], side, sig["qty"], sig["price"], source="ai")
    new_status = "executed" if res["ok"] else "failed"
    await db.signals.update_one(
        {"id": signal_id},
        {"$set": {"status": new_status, "executed_at": now_iso(), "exec_result": res.get("error", "ok")}},
    )
    return res


async def skip_signal(db, signal_id: str) -> dict:
    r = await db.signals.update_one(
        {"id": signal_id, "status": "pending"},
        {"$set": {"status": "skipped", "executed_at": now_iso()}},
    )
    return {"ok": r.modified_count > 0}
