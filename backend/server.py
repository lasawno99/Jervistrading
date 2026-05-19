from fastapi import FastAPI, APIRouter, HTTPException, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import random
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

# Moonshot / Kimi
MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '').strip()
KIMI_MODEL = os.environ.get('KIMI_MODEL', 'moonshotai/Kimi-K2.5')

try:
    from openai import OpenAI
    if MOONSHOT_API_KEY:
        kimi_client = OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.ai/v1")
    else:
        kimi_client = None
except Exception:
    kimi_client = None

# Trading + Telegram modules
import trading_engine as te
import telegram_bot as tg
import forex_agent as fx
import oanda_client as oa
import alpaca_client as al
import jarvis_agent as jv
import fx_strategies as fxs
from scheduler import scheduler_loop

app = FastAPI(title="Jarvis Command Center API")
api_router = APIRouter(prefix="/api")


# ================= MODELS =================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    panel: Literal["trading", "twitter", "calendar", "news", "task", "general"] = "general"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    detail: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatResponse(BaseModel):
    reply: str
    intent: str
    spawned_task: Optional[AgentTask] = None
    session_id: str


class TickerRow(BaseModel):
    symbol: str
    price: float
    change: float
    posture: str


class TweetItem(BaseModel):
    id: str
    handle: str
    name: str
    content: str
    timestamp: str
    likes: int


class CalendarItem(BaseModel):
    id: str
    title: str
    time: str
    attendees: List[str]


class NewsItem(BaseModel):
    id: str
    headline: str
    source: str
    timestamp: str


class TradeRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    qty: float


# ================= INTENT ROUTER =================

INTENT_KEYWORDS = {
    "trading": ["trade", "stock", "buy", "sell", "market", "portfolio", "tsla", "btc", "crypto", "oil", "gold", "price", "nvda", "eth"],
    "twitter": ["twitter", "tweet", "x.com", " x ", "social", "post", "trend", "viral"],
    "calendar": ["meeting", "schedule", "calendar", "event", "appointment", "remind", "tomorrow", "monday", "friday"],
    "news": ["news", "headline", "article", "research", "report", "happening"],
}


def classify_intent(text: str) -> str:
    t = f" {text.lower()} "
    for intent, kws in INTENT_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return intent
    return "general"


SYSTEM_PROMPT = """You are JARVIS, an autonomous AI command center operator running a 24/7 paper-trading bot connected to Telegram. You speak with calm precision in 1-3 short sentences. You orchestrate sub-agents across panels: trading, twitter, calendar, news, and general tasks. Briefly confirm what you'll do. Never use markdown. Be confident and concise."""


async def call_kimi(message: str) -> str:
    """Call Kimi K2.5 if key available, else fallback to scripted reply."""
    if kimi_client:
        try:
            loop = asyncio.get_event_loop()

            def _call():
                return kimi_client.chat.completions.create(
                    model=KIMI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": message},
                    ],
                    temperature=1,
                    max_tokens=2048,
                )

            resp = await loop.run_in_executor(None, _call)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Kimi error: {e}")
            return scripted_reply(message)
    return scripted_reply(message)


async def call_kimi_strict(message: str) -> Optional[str]:
    """Like call_kimi but returns None if Kimi isn't actually configured (so callers can use their own fallback)."""
    if not kimi_client:
        return None
    try:
        loop = asyncio.get_event_loop()

        def _call():
            return kimi_client.chat.completions.create(
                model=KIMI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a concise quant trading agent. One sentence, no markdown."},
                    {"role": "user", "content": message},
                ],
                temperature=1,
                max_tokens=1024,
            )

        resp = await loop.run_in_executor(None, _call)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Kimi strict error: {e}")
        return None


def scripted_reply(message: str) -> str:
    intent = classify_intent(message)
    templates = {
        "trading": "Acknowledged. Tickers refreshed and bot posture updated. Trading panel synced.",
        "twitter": "Scanning the X feed for relevant signals. Streaming results to your social panel.",
        "calendar": "Checking your calendar. I'll surface conflicts in the schedule panel.",
        "news": "Aggregating top sources. News brief is being assembled.",
        "general": "Understood. Sub-agent spawned and routed to the dashboard.",
    }
    return templates.get(intent, templates["general"])


# ================= ROUTES =================

@api_router.get("/")
async def root():
    return {
        "service": "jarvis",
        "model": KIMI_MODEL,
        "kimi_active": kimi_client is not None,
        "telegram_configured": tg.is_configured(),
    }


@api_router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    intent = classify_intent(req.message)
    reply = await call_kimi(req.message)

    task_titles = {
        "trading": f"Analyze trading: {req.message[:60]}",
        "twitter": f"Monitor X feed: {req.message[:60]}",
        "calendar": f"Schedule: {req.message[:60]}",
        "news": f"Research: {req.message[:60]}",
        "general": f"Run task: {req.message[:60]}",
    }
    task = AgentTask(
        title=task_titles.get(intent, task_titles["general"]),
        panel=intent if intent in ("trading", "twitter", "calendar", "news") else "task",
        status="running",
        detail=reply,
    )
    await db.tasks.insert_one(task.model_dump())

    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": "user",
        "content": req.message,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": "assistant",
        "content": reply,
        "intent": intent,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    return ChatResponse(reply=reply, intent=intent, spawned_task=task, session_id=session_id)


@api_router.get("/tasks", response_model=List[AgentTask])
async def list_tasks(limit: int = 20):
    docs = await db.tasks.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs


@api_router.delete("/tasks")
async def clear_tasks():
    await db.tasks.delete_many({})
    return {"ok": True}


# ================= MOCK FEEDS =================

@api_router.get("/feed/trading", response_model=List[TickerRow])
async def trading_feed():
    snap = te.tick_prices()
    posture_map = {
        "BTC": "MOMENTUM · LONG",
        "ETH": "ACCUMULATE",
        "OIL": "LONG · COMMODITY",
        "GOLD": "ADAPTIVE ROTATION",
        "TSLA": "MEAN REVERT",
        "NVDA": "BREAKOUT WATCH",
    }
    return [
        TickerRow(symbol=sym, price=round(d["price"], 2), change=round(d["change_pct"], 2), posture=posture_map.get(sym, "—"))
        for sym, d in snap.items()
    ]


@api_router.get("/feed/twitter", response_model=List[TweetItem])
async def twitter_feed():
    raw = [
        ("@elonmusk", "Elon Musk", "Mars launch window opens Q3. Boosters reusable beyond 50 cycles now."),
        ("@naval", "Naval", "The internet rewards those who build in public. Compounding attention is a moat."),
        ("@balajis", "Balaji", "Sovereign individual thesis playing out faster than predicted. Watch capital flows."),
        ("@sama", "Sam Altman", "Compute is the new oil. Allocate accordingly."),
        ("@cz_binance", "CZ", "Risk management is everything. Position sizing > prediction."),
        ("@karpathy", "Andrej Karpathy", "Tokenizers are the worst part of LLMs. We can do better."),
    ]
    now = datetime.now(timezone.utc)
    return [
        TweetItem(
            id=str(uuid.uuid4()),
            handle=h,
            name=n,
            content=c,
            timestamp=(now - timedelta(minutes=random.randint(2, 240))).isoformat(),
            likes=random.randint(120, 18_400),
        ) for h, n, c in raw
    ]


@api_router.get("/feed/calendar", response_model=List[CalendarItem])
async def calendar_feed():
    items = [
        ("Strategy Sync · Trading Desk", ["Marco", "Lena"], 1),
        ("AI Roadmap Review", ["Aiden", "Priya", "Chen"], 4),
        ("Investor Update Call", ["Olivia", "Sasha"], 8),
        ("Hormuz Logistics Brief", ["Rafael", "Yuki"], 26),
    ]
    now = datetime.now(timezone.utc)
    return [
        CalendarItem(
            id=str(uuid.uuid4()),
            title=t,
            time=(now + timedelta(hours=h)).isoformat(),
            attendees=a,
        ) for t, a, h in items
    ]


@api_router.get("/feed/news", response_model=List[NewsItem])
async def news_feed():
    items = [
        ("Oil futures rally as Hormuz tensions escalate", "Reuters"),
        ("Fed signals dovish pivot; risk assets bid", "Bloomberg"),
        ("NVIDIA unveils next-gen inference accelerator", "The Verge"),
        ("Gold reclaims $2,400 as DXY softens", "FT"),
        ("Moonshot AI releases Kimi K2.5 with 256K context", "TechCrunch"),
    ]
    now = datetime.now(timezone.utc)
    return [
        NewsItem(
            id=str(uuid.uuid4()),
            headline=h,
            source=s,
            timestamp=(now - timedelta(minutes=random.randint(5, 300))).isoformat(),
        ) for h, s in items
    ]


# ================= BOT / TRADING =================

@api_router.get("/bot/status")
async def bot_status():
    eq = await te.compute_equity(db)
    return {
        "telegram": tg.get_state(),
        "account": eq,
        "kimi_active": kimi_client is not None,
        "model": KIMI_MODEL,
    }


@api_router.get("/bot/positions")
async def bot_positions():
    return await te.compute_equity(db)


@api_router.get("/bot/trades")
async def bot_trades(limit: int = 20):
    return await te.list_trades(db, limit)


@api_router.get("/bot/signals")
async def bot_signals(limit: int = 20):
    return await te.list_signals(db, limit)


@api_router.post("/bot/auto")
async def bot_auto(payload: dict):
    on = bool(payload.get("on", False))
    return {"auto": tg.set_auto(on)}


@api_router.post("/bot/signal")
async def bot_generate_signal():
    sig = await te.generate_signal(db, call_kimi_strict)
    if sig:
        await tg.broadcast_signal(db, sig)
    return sig or {"ok": False, "reason": "no edge"}


@api_router.post("/bot/trade")
async def bot_trade(req: TradeRequest):
    res = await te.execute_trade(db, req.symbol, req.side, req.qty, source="dashboard")
    if not res["ok"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@api_router.post("/bot/signal/{sig_id}/approve")
async def bot_approve(sig_id: str):
    return await te.execute_signal(db, sig_id)


@api_router.post("/bot/signal/{sig_id}/skip")
async def bot_skip(sig_id: str):
    return await te.skip_signal(db, sig_id)


@api_router.post("/bot/reset")
async def bot_reset():
    await db.paper_account.delete_many({})
    await db.paper_positions.delete_many({})
    await db.paper_trades.delete_many({})
    await db.signals.delete_many({})
    await db.equity_curve.delete_many({})
    await te.ensure_account(db)
    return {"ok": True}


@api_router.get("/bot/risk")
async def bot_get_risk():
    return await te.get_risk(db)


@api_router.post("/bot/risk")
async def bot_update_risk(payload: dict):
    return await te.update_risk(db, payload)


@api_router.get("/bot/equity-curve")
async def bot_equity_curve(limit: int = 200):
    return await te.get_equity_curve(db, limit)


# ================= FOREX (Claude + OANDA) =================

class ForexChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@api_router.get("/forex/status")
async def forex_status():
    return {**fx.status(), "env": os.environ.get("OANDA_ENV", "practice")}


@api_router.get("/forex/account")
async def forex_account():
    return oa.get_account()


@api_router.get("/forex/positions")
async def forex_positions():
    return oa.get_open_positions()


@api_router.get("/forex/history")
async def forex_history(count: int = 20):
    return oa.get_trade_history(count)


@api_router.get("/forex/price")
async def forex_price(instrument: str):
    return oa.get_price(instrument)


async def _broker_summary_for(*, broker: str, acct: dict, locked_filter: dict | None = None) -> dict:
    """Common shape: turn a raw broker account dict into the dashboard payload.

    - ``broker`` is a stable key ("oanda", "alpaca") used for storage attribution.
    - ``locked_filter`` is the Mongo filter against ``profit_locks`` for this broker.
      Pass {} (or None) to sum **all** events; pass {"source": "..."} to scope.
    """
    if "error" in acct:
        return acct

    nav = float(acct.get("nav") or acct.get("equity") or acct.get("balance") or 0.0)
    balance = float(acct.get("balance") or 0.0)
    unrealized = float(acct.get("unrealized_pl") or 0.0)
    currency = acct.get("currency") or "USD"
    open_positions = int(acct.get("open_position_count") or 0)
    open_trades = int(acct.get("open_trade_count") or 0)
    margin_used = float(acct.get("margin_used") or 0.0)
    margin_available = float(acct.get("margin_available") or acct.get("buying_power") or 0.0)
    source = acct.get("source") or broker

    # Locked profits — scoped to this broker via source tag where possible.
    locked_total = 0.0
    locked_events = 0
    try:
        cursor = db.profit_locks.find(locked_filter or {}, {"_id": 0, "amount": 1})
        async for ev in cursor:
            locked_total += float(ev.get("amount") or 0.0)
            locked_events += 1
    except Exception:
        pass

    total_wealth = nav + locked_total

    # Day-over-day NAV: per-broker key in ``nav_snapshots``.
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dod_change = None
    dod_pct = None
    try:
        prev = await db.nav_snapshots.find_one(
            {"broker": broker, "date": {"$lt": today_utc}},
            sort=[("date", -1)],
            projection={"_id": 0, "nav": 1, "date": 1},
        )
        if prev and prev.get("nav") is not None:
            prev_nav = float(prev["nav"])
            dod_change = nav - prev_nav
            dod_pct = (dod_change / prev_nav * 100.0) if prev_nav else None

        await db.nav_snapshots.update_one(
            {"broker": broker, "date": today_utc},
            {
                "$set": {
                    "broker": broker,
                    "date": today_utc,
                    "nav": nav,
                    "balance": balance,
                    "locked_total": locked_total,
                    "total_wealth": total_wealth,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "$setOnInsert": {"opened_nav": nav},
            },
            upsert=True,
        )
    except Exception as e:
        logging.warning(f"nav_snapshot persistence failed: {e}")

    return {
        "broker": broker,
        "nav": nav,
        "balance": balance,
        "unrealized_pl": unrealized,
        "margin_used": margin_used,
        "margin_available": margin_available,
        "open_positions": open_positions,
        "open_trades": open_trades,
        "currency": currency,
        "locked_profits": locked_total,
        "locked_events": locked_events,
        "total_wealth": total_wealth,
        "dod_change": dod_change,
        "dod_pct": dod_pct,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }


@api_router.get("/broker/summary")
async def broker_summary():
    """Backwards-compat: OANDA forex summary (the original endpoint)."""
    acct = oa.get_account()
    # Sum everything *except* alpaca-tagged events for backwards compatibility.
    locked_filter = {"$or": [{"source": {"$exists": False}}, {"source": {"$ne": "jarvis-synth-alpaca"}}]}
    return await _broker_summary_for(broker="oanda", acct=acct, locked_filter=locked_filter)


@api_router.get("/broker/oanda/summary")
async def broker_oanda_summary():
    """OANDA forex broker — paper practice account."""
    acct = oa.get_account()
    locked_filter = {"$or": [{"source": {"$exists": False}}, {"source": {"$ne": "jarvis-synth-alpaca"}}]}
    return await _broker_summary_for(broker="oanda", acct=acct, locked_filter=locked_filter)


@api_router.get("/broker/alpaca/summary")
async def broker_alpaca_summary():
    """Alpaca multi-asset broker — paper account, stocks + crypto."""
    acct = al.get_account()
    pos = al.get_open_positions()
    if isinstance(pos, dict) and "positions" in pos:
        acct = {
            **acct,
            "open_position_count": pos.get("count") or 0,
            "open_trade_count": pos.get("count") or 0,
            "unrealized_pl": pos.get("unrealized_total") or 0.0,
        }
    locked_filter = {"source": "jarvis-synth-alpaca"}
    payload = await _broker_summary_for(broker="alpaca", acct=acct, locked_filter=locked_filter)
    # Extra Alpaca-only field: per-position breakdown for the dashboard.
    if isinstance(pos, dict):
        payload["positions_detail"] = pos.get("positions", [])
    return payload


# ----------------------- Sim broker (in-memory paper desk) -----------------------

SIM_PROFIT_LOCK_THRESHOLD_PCT = 5.0


async def _sim_check_profit_lock(equity: float) -> dict | None:
    """Auto-lock simulator profits at +5% NAV growth.

    Maintains a baseline in MongoDB collection ``sim_lock_baseline`` (singleton doc).
    When equity ≥ baseline × 1.05, locks the gain into the same ``profit_locks``
    collection (with ``source="sim"``), resets baseline to current equity.
    """
    doc = await db.sim_lock_baseline.find_one({"_id": "main"}, {"_id": 0})
    if doc is None:
        # First-touch initialization — set baseline to current equity, don't lock yet.
        await db.sim_lock_baseline.insert_one({"_id": "main", "baseline": float(equity)})
        return None

    baseline = float(doc.get("baseline") or 0.0)
    if baseline <= 0:
        # Defensive: never divide by 0
        await db.sim_lock_baseline.update_one(
            {"_id": "main"}, {"$set": {"baseline": float(equity)}}, upsert=True
        )
        return None

    target = baseline * (1 + SIM_PROFIT_LOCK_THRESHOLD_PCT / 100.0)
    if equity < target:
        return None

    # Threshold crossed — lock the gain, reset baseline.
    locked_amount = float(equity) - baseline
    ts = datetime.now(timezone.utc).isoformat()
    event = {
        "timestamp": ts,
        "amount": locked_amount,
        "nav_at_lock": float(equity),
        "baseline_before": baseline,
        "baseline_after": float(equity),
        "source": "sim",
        "received_at": ts,
    }
    await db.profit_locks.update_one(
        {"timestamp": ts, "source": "sim"},
        {"$setOnInsert": event},
        upsert=True,
    )
    await db.sim_lock_baseline.update_one(
        {"_id": "main"}, {"$set": {"baseline": float(equity)}}, upsert=True
    )
    logging.info(f"sim_profit_lock_fired amount={locked_amount:.2f} new_baseline={equity:.2f}")
    return event


@api_router.get("/broker/sim/summary")
async def broker_sim_summary():
    """Internal JARVIS sim desk (paper-paper). Auto-locks at +5% NAV growth.

    This is the same in-memory engine that powers the "BOT · ACCOUNT" left-rail
    panel — chat commands like 'buy 0.05 BTC' fill against it. Treated as a
    full broker here so the dashboard's locked-profits mechanism is end-to-end
    demonstrated even without real Railway workers firing.
    """
    eq = await te.compute_equity(db)
    equity = float(eq.get("equity") or 0.0)
    cash = float(eq.get("cash") or 0.0)
    starting_cash = float(eq.get("starting_cash") or 100_000.0)
    positions = eq.get("positions") or []
    unrealized = float(eq.get("total_pl") or 0.0)

    # Fire the lock check on every poll (cheap MongoDB read + maybe one write).
    await _sim_check_profit_lock(equity)

    # Shape it like the other broker payloads via the common helper.
    acct = {
        "currency": "USD",
        "balance": cash,
        "equity": equity,
        "nav": equity,
        "unrealized_pl": unrealized,
        "open_position_count": len(positions),
        "open_trade_count": len(positions),
        "margin_used": 0.0,
        "margin_available": cash,
        "source": "sim",
    }
    locked_filter = {"source": "sim"}
    payload = await _broker_summary_for(broker="sim", acct=acct, locked_filter=locked_filter)
    payload["starting_cash"] = starting_cash
    payload["positions_detail"] = positions
    return payload


@api_router.get("/broker/all")
async def broker_all():
    """Combined view: OANDA + Alpaca + Sim side-by-side, plus a unified Total Wealth."""
    oanda = await broker_oanda_summary()
    alpaca = await broker_alpaca_summary()
    sim = await broker_sim_summary()

    def _sum(*vals):
        return sum(float(v or 0) for v in vals if isinstance(v, (int, float)))

    combined_nav = _sum(oanda.get("nav"), alpaca.get("nav"), sim.get("nav"))
    combined_locked = _sum(
        oanda.get("locked_profits"), alpaca.get("locked_profits"), sim.get("locked_profits")
    )
    combined_wealth = combined_nav + combined_locked
    combined_unrealized = _sum(
        oanda.get("unrealized_pl"), alpaca.get("unrealized_pl"), sim.get("unrealized_pl")
    )
    combined_positions = int(
        (oanda.get("open_positions") or 0)
        + (alpaca.get("open_positions") or 0)
        + (sim.get("open_positions") or 0)
    )
    return {
        "oanda": oanda,
        "alpaca": alpaca,
        "sim": sim,
        "combined": {
            "nav": combined_nav,
            "locked_profits": combined_locked,
            "total_wealth": combined_wealth,
            "unrealized_pl": combined_unrealized,
            "open_positions": combined_positions,
            "currency": "USD",
        },
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ----------------------- Dashboard v2 aggregates -----------------------

@api_router.get("/dashboard/hero")
async def dashboard_hero():
    """Hero KPI row: total equity, day P/L, total cash, exposure %, win rate.

    Aggregates across OANDA + Alpaca + Sim. Computes win-rate from sim's
    closed-position history if available, else returns null.
    """
    all_data = await broker_all()
    oanda = all_data["oanda"]
    alpaca = all_data["alpaca"]
    sim = all_data["sim"]
    combined = all_data["combined"]

    total_equity = combined["nav"] + combined["locked_profits"]
    total_cash = float((oanda.get("balance") or 0) + (alpaca.get("balance") or 0) + (sim.get("balance") or 0))
    day_pl = float(oanda.get("dod_change") or 0) + float(alpaca.get("dod_change") or 0)
    # Sim has no DoD yet — approximate via realized today
    sim_starting = float(sim.get("starting_cash") or 100_000.0)
    sim_today_pl = float(sim.get("nav") or 0) - sim_starting - float(sim.get("locked_profits") or 0)
    day_pl_total = day_pl + sim_today_pl
    day_pl_pct = (day_pl_total / total_equity * 100.0) if total_equity > 0 else 0.0

    invested = total_equity - total_cash
    exposure_pct = max(0.0, min(100.0, (invested / total_equity * 100.0) if total_equity > 0 else 0.0))

    # Win rate from sim's closed trades + OANDA history, or null if no data
    try:
        closed = await db.closed_trades.find({}, {"_id": 0, "pl": 1}).to_list(500)
        wins = sum(1 for t in closed if float(t.get("pl") or 0) > 0)
        total = len(closed)
        # Also fold in OANDA closed trades when available
        try:
            oa_hist = oa.get_trade_history(count=200)
            for t in oa_hist.get("trades") or []:
                pl = float(t.get("realized_pl") or 0)
                if pl > 0:
                    wins += 1
                total += 1
        except Exception:
            pass
        win_rate = (wins / total * 100.0) if total > 0 else None
    except Exception:
        win_rate = None

    return {
        "total_equity": total_equity,
        "total_equity_pct": (combined["unrealized_pl"] / total_equity * 100.0) if total_equity > 0 else 0.0,
        "day_pl": day_pl_total,
        "day_pl_pct": day_pl_pct,
        "total_cash": total_cash,
        "exposure_pct": exposure_pct,
        "win_rate": win_rate,
        "open_positions": combined["open_positions"],
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/dashboard/sparkline")
async def dashboard_sparkline(metric: str = "equity"):
    """30-point sparkline series for hero KPI cards.

    Pulls per-broker `nav_snapshots` (sum across brokers per day) for equity;
    for other metrics, falls back to a deterministic generated curve so the UI
    doesn't look empty while history is being banked.
    """
    snaps = await db.nav_snapshots.find(
        {}, {"_id": 0, "date": 1, "nav": 1, "broker": 1, "locked_total": 1}
    ).sort("date", 1).to_list(2000)

    if metric == "equity" and snaps:
        # Group by date, sum across brokers
        by_date: dict[str, float] = {}
        for s in snaps:
            d = s.get("date")
            if not d:
                continue
            by_date[d] = by_date.get(d, 0.0) + float(s.get("nav") or 0.0) + float(s.get("locked_total") or 0.0)
        series = [{"x": d, "y": v} for d, v in sorted(by_date.items())][-30:]
        if series:
            return {"metric": metric, "points": series, "source": "snapshots"}

    # Fallback: tight synthetic series anchored at current NAV so the line isn't flat-zero
    base = (await broker_all())["combined"]["total_wealth"] or 100_000.0
    import math
    points = []
    for i in range(30):
        wobble = math.sin(i / 4.0) * 0.005 + (i / 30.0) * 0.01
        points.append({"x": f"d-{29 - i}", "y": round(base * (1 + wobble), 2)})
    return {"metric": metric, "points": points, "source": "synthetic"}


@api_router.get("/dashboard/peers")
async def dashboard_peers():
    """Trading Peers Cluster data: 8 nodes (assets + AI agents) around the central JARVIS node.

    Each node returns: id, label, kind, value, change_pct, status, color_hint.
    """
    # 5 assets — pull live prices for visible momentum
    assets = [
        ("BTC", "BTC/USD", "crypto"),
        ("ETH", "ETH/USD", "crypto"),
        ("NVDA", "NVDA", "stock"),
        ("TSLA", "TSLA", "stock"),
        ("OIL", "WTI", "commodity"),
    ]
    # 3 AI agents — surface live status from existing state
    agents = [
        ("KIMI", "Kimi", "Chat fallback", "online"),
        ("CLDE", "Claude", "5-layer reasoning", "online"),
        ("KRNS", "Kronos", "Price prediction", "online"),
    ]

    nodes = []

    # Assets: synthesize change_pct from sim positions or last broker price feed.
    # Keep it cheap — we already have OANDA + Alpaca data via broker/all
    eq = await te.compute_equity(db)
    sim_positions = {p["symbol"]: p for p in (eq.get("positions") or [])}

    for sym, label, kind in assets:
        pos = sim_positions.get(sym)
        if pos:
            change_pct = float(pos.get("pl_pct") or 0.0)
            value = float(pos.get("current_price") or pos.get("entry") or 0.0)
        else:
            # Synthesize a small momentum signal so the cluster glows even pre-trade
            import random
            random.seed(hash(sym) % 9973)
            change_pct = round(random.uniform(-2.5, 2.5), 2)
            value = 0.0
        nodes.append({
            "id": sym,
            "label": sym,
            "name": label,
            "kind": "asset",
            "asset_kind": kind,
            "value": value,
            "change_pct": change_pct,
            "status": "bullish" if change_pct > 0.3 else ("bearish" if change_pct < -0.3 else "neutral"),
        })

    for short, name, role, status in agents:
        nodes.append({
            "id": short,
            "label": short,
            "name": name,
            "kind": "agent",
            "role": role,
            "value": 0.0,
            "change_pct": 0.0,
            "status": status,
        })

    return {"center": {"id": "JARVIS", "label": "JARVIS", "kind": "self"}, "nodes": nodes}


@api_router.get("/dashboard/recent-trades")
async def dashboard_recent_trades(limit: int = 8):
    """Recent fills across all brokers + sim, newest first.

    Merges three sources:
      1. ``closed_trades`` collection (sim sells write here on every position close)
      2. OANDA closed trades via ``oanda_client.get_trade_history()`` (REST)
      3. Alpaca FILL activities via ``alpaca_client.get_recent_fills()`` (REST)

    Each row is normalized to: {ts, symbol, side, qty, pl?, pl_pct?, broker}.
    OANDA + sim rows have realized P/L; Alpaca FILL rows are per-leg (no pairing).
    """
    rows: list[dict] = []

    # 1) Sim — already in MongoDB
    try:
        sim = await db.closed_trades.find({}, {"_id": 0}).sort("ts", -1).to_list(int(limit) * 2)
        for t in sim:
            rows.append({
                "ts": t.get("ts"),
                "symbol": t.get("symbol"),
                "side": (t.get("side") or "").lower(),
                "qty": float(t.get("qty") or 0),
                "entry": float(t.get("entry") or 0),
                "exit": float(t.get("exit") or 0),
                "pl": float(t.get("pl") or 0),
                "pl_pct": float(t.get("pl_pct") or 0),
                "broker": t.get("broker") or "sim",
            })
    except Exception:
        pass

    # 2) OANDA — closed trades with realized P/L
    try:
        hist = oa.get_trade_history(count=int(limit) * 2)
        for t in hist.get("trades") or []:
            entry = float(t.get("price") or 0)
            exit_px = float(t.get("average_close_price") or 0)
            units = float(t.get("initial_units") or 0)
            pl = float(t.get("realized_pl") or 0)
            pl_pct = (((exit_px - entry) / entry) * 100.0 * (1 if units > 0 else -1)) if entry else 0.0
            rows.append({
                "ts": t.get("close_time") or t.get("open_time"),
                "symbol": t.get("instrument"),
                "side": "buy" if units > 0 else "sell",
                "qty": abs(units),
                "entry": entry,
                "exit": exit_px,
                "pl": pl,
                "pl_pct": round(pl_pct, 4),
                "broker": "oanda",
            })
    except Exception as e:
        logging.warning(f"oanda trade history fetch failed: {e}")

    # 3) Alpaca — FILL activities (per-leg; no built-in pairing)
    try:
        fills = al.get_recent_fills(limit=int(limit) * 2)
        for f in fills.get("fills") or []:
            rows.append({
                "ts": f.get("ts"),
                "symbol": f.get("symbol"),
                "side": f.get("side"),
                "qty": float(f.get("qty") or 0),
                "entry": None,
                "exit": float(f.get("price") or 0),
                "pl": None,  # unpaired
                "pl_pct": None,
                "broker": "alpaca",
            })
    except Exception as e:
        logging.warning(f"alpaca fills fetch failed: {e}")

    # Sort newest first; tolerate string-isoformat or None ts
    def _key(r):
        return r.get("ts") or ""
    rows.sort(key=_key, reverse=True)

    if not rows:
        # Cold-start fallback: synthesize from current open positions
        eq = await te.compute_equity(db)
        positions = eq.get("positions") or []
        for p in positions[: int(limit)]:
            pl = float(p.get("pl") or 0)
            rows.append({
                "ts": p.get("opened_at") or datetime.now(timezone.utc).isoformat(),
                "symbol": p.get("symbol"),
                "side": "buy" if float(p.get("qty") or 0) > 0 else "sell",
                "qty": float(p.get("qty") or 0),
                "entry": float(p.get("entry") or 0),
                "exit": None,
                "pl": pl,
                "pl_pct": float(p.get("pl_pct") or 0),
                "broker": "sim",
            })

    return {"trades": rows[: int(limit)], "sources": ["sim", "oanda", "alpaca"]}


@api_router.get("/dashboard/open-positions")
async def dashboard_open_positions(limit: int = 20):
    """All open positions across OANDA + Alpaca + Sim, normalized shape."""
    out = []

    # Sim
    try:
        eq = await te.compute_equity(db)
        for p in (eq.get("positions") or []):
            out.append({
                "symbol": p.get("symbol"),
                "broker": "sim",
                "qty": float(p.get("qty") or 0),
                "entry": float(p.get("entry") or 0),
                "current": float(p.get("current_price") or 0),
                "pl": float(p.get("pl") or 0),
                "pl_pct": float(p.get("pl_pct") or 0),
            })
    except Exception:
        pass

    # Alpaca
    try:
        alp = al.get_open_positions()
        for p in (alp.get("positions") or []):
            out.append({
                "symbol": p.get("symbol"),
                "broker": "alpaca",
                "qty": p.get("qty"),
                "entry": p.get("avg_entry_price"),
                "current": p.get("current_price"),
                "pl": p.get("unrealized_pl"),
                "pl_pct": p.get("unrealized_plpc"),
            })
    except Exception:
        pass

    # OANDA — open positions via existing client
    try:
        op = oa.get_open_positions()
        for p in (op.get("positions") or []):
            out.append({
                "symbol": p.get("instrument"),
                "broker": "oanda",
                "qty": float(p.get("units") or 0),
                "entry": float(p.get("avg_price") or 0),
                "current": float(p.get("current_price") or 0),
                "pl": float(p.get("unrealized_pl") or 0),
                "pl_pct": float(p.get("unrealized_pl_pct") or 0),
            })
    except Exception:
        pass

    return {"positions": out[: int(limit)]}


class ProfitLockEvent(BaseModel):
    timestamp: str  # ISO UTC; used as idempotency key
    amount: float  # locked $ amount (positive)
    nav_at_lock: Optional[float] = None
    baseline_before: Optional[float] = None
    baseline_after: Optional[float] = None
    source: Optional[str] = "jarvis-synth"


@api_router.post("/broker/profit-locks")
async def broker_post_profit_lock(event: ProfitLockEvent, request: Request):
    """Webhook for jarvis-synth (and other workers) to POST profit-lock events.

    Auth: X-Lock-Token header must match env BROKER_LOCK_TOKEN. If the env var
    is unset, the endpoint is closed (returns 503) — fail-secure, no public writes.
    Idempotency: ``timestamp`` is the unique key; duplicate posts are no-ops.
    """
    expected = os.environ.get("BROKER_LOCK_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="profit-lock webhook disabled (BROKER_LOCK_TOKEN not set)")
    presented = request.headers.get("x-lock-token", "").strip()
    if not presented or presented != expected:
        raise HTTPException(status_code=401, detail="invalid lock token")
    if event.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")

    doc = {
        "timestamp": event.timestamp,
        "amount": float(event.amount),
        "nav_at_lock": event.nav_at_lock,
        "baseline_before": event.baseline_before,
        "baseline_after": event.baseline_after,
        "source": event.source or "jarvis-synth",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.profit_locks.update_one(
        {"timestamp": event.timestamp},
        {"$setOnInsert": doc},
        upsert=True,
    )
    return {
        "stored": bool(res.upserted_id),
        "duplicate": not bool(res.upserted_id),
        "timestamp": event.timestamp,
        "amount": float(event.amount),
    }


@api_router.get("/broker/profit-locks")
async def broker_list_profit_locks(limit: int = 25):
    """Recent profit-lock events for the dashboard (most recent first)."""
    cursor = db.profit_locks.find({}, {"_id": 0}).sort("timestamp", -1).limit(int(limit))
    return {"events": [ev async for ev in cursor]}


# ----------------------- Bot Brain: live cycle stream -----------------------

class CycleEntry(BaseModel):
    timestamp: str  # ISO UTC; idempotency key
    worker: str  # "jarvis-synth" | "jarvis-synth-alpaca"
    instrument: str
    action: str  # LONG | SHORT | HOLD
    units: float = 0
    tauric_verdict: Optional[str] = None
    tauric_confidence: Optional[float] = None
    kronos_direction: Optional[str] = None
    kronos_confidence: Optional[str] = None
    kronos_upside_prob: Optional[float] = None
    reasoning: Optional[str] = None
    filters: list = []


@api_router.post("/bot-brain/cycles")
async def bot_brain_post_cycle(entry: CycleEntry, request: Request):
    """Webhook for Railway workers to push every pipeline decision.

    Same auth model as profit-locks: ``X-Lock-Token`` header must match
    ``BROKER_LOCK_TOKEN`` env. Idempotency: ``(worker, instrument, timestamp)``.
    """
    expected = os.environ.get("BROKER_LOCK_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="bot-brain webhook disabled")
    presented = request.headers.get("x-lock-token", "").strip()
    if not presented or presented != expected:
        raise HTTPException(status_code=401, detail="invalid lock token")

    doc = {
        **entry.dict(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.bot_cycles.update_one(
        {"worker": entry.worker, "instrument": entry.instrument, "timestamp": entry.timestamp},
        {"$setOnInsert": doc},
        upsert=True,
    )
    # Soft-cap collection at ~2000 entries; trim oldest above that.
    try:
        count = await db.bot_cycles.count_documents({})
        if count > 2000:
            cutoff = await db.bot_cycles.find({}, {"_id": 1, "timestamp": 1}).sort("timestamp", -1).skip(2000).limit(1).to_list(1)
            if cutoff:
                await db.bot_cycles.delete_many({"timestamp": {"$lt": cutoff[0]["timestamp"]}})
    except Exception:
        pass
    return {"stored": bool(res.upserted_id), "duplicate": not bool(res.upserted_id)}


@api_router.get("/bot-brain/cycles")
async def bot_brain_list_cycles(limit: int = 15, worker: Optional[str] = None):
    """Latest cycle decisions across both workers, newest first."""
    q: dict = {}
    if worker:
        q["worker"] = worker
    cursor = db.bot_cycles.find(q, {"_id": 0}).sort("timestamp", -1).limit(int(limit))
    cycles = [c async for c in cursor]

    # Compute quick stats for the panel header
    counts = {"LONG": 0, "SHORT": 0, "HOLD": 0}
    for c in cycles:
        a = (c.get("action") or "").upper()
        if a in counts:
            counts[a] += 1
    return {"cycles": cycles, "counts": counts, "as_of": datetime.now(timezone.utc).isoformat()}


@api_router.post("/forex/chat")
async def forex_chat(req: ForexChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    # Load history
    doc = await db.forex_sessions.find_one({"session_id": session_id}, {"_id": 0})
    history = doc.get("history", []) if doc else []
    # Risk gate: read kill switch — applies to forex too
    risk = await te.get_risk(db)
    block = bool(risk.get("kill_switch"))
    reply, new_history = await fx.run_agent(history, req.message, block_trades=block)
    await db.forex_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"session_id": session_id, "history": new_history, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"session_id": session_id, "reply": reply, "kill_switch": block}


@api_router.delete("/forex/chat/{session_id}")
async def forex_chat_clear(session_id: str):
    await db.forex_sessions.delete_one({"session_id": session_id})
    return {"ok": True}


# ================= JARVIS UNIFIED ASSISTANT =================

class JarvisChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_name: Optional[str] = "Operator"


@api_router.get("/jarvis/status")
async def jarvis_status():
    return jv.status()


@api_router.post("/jarvis/chat")
async def jarvis_chat(req: JarvisChatRequest):
    session_id = req.session_id or "dashboard-default"
    doc = await db.jarvis_sessions.find_one({"session_id": session_id}, {"_id": 0})
    history = doc.get("history", []) if doc else []
    reply, new_history = await jv.chat(db, history, req.message, user_name=req.user_name or "Operator")
    await db.jarvis_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"session_id": session_id, "history": new_history, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"session_id": session_id, "reply": reply}


@api_router.delete("/jarvis/chat/{session_id}")
async def jarvis_chat_clear(session_id: str):
    await db.jarvis_sessions.delete_one({"session_id": session_id})
    return {"ok": True}


@api_router.get("/jarvis/schedules")
async def jarvis_schedules():
    docs = await db.schedules.find({"status": "active"}, {"_id": 0}).sort("next_run", 1).to_list(200)
    return {"schedules": docs}


@api_router.delete("/jarvis/schedules/{sid}")
async def jarvis_schedule_cancel(sid: str):
    r = await db.schedules.update_one({"id": sid}, {"$set": {"status": "cancelled"}})
    return {"ok": r.modified_count > 0}


@api_router.get("/jarvis/todos")
async def jarvis_todos(include_done: bool = False):
    q = {} if include_done else {"done": False}
    docs = await db.todos.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"todos": docs}


@api_router.post("/jarvis/todos/{tid}/complete")
async def jarvis_todo_complete(tid: str):
    r = await db.todos.update_one({"id": tid}, {"$set": {"done": True, "completed_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": r.modified_count > 0}


@api_router.get("/jarvis/notifications")
async def jarvis_notifications(limit: int = 25):
    docs = await db.notifications.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
    return {"notifications": docs}


@api_router.post("/jarvis/notifications/read")
async def jarvis_notifications_read():
    await db.notifications.update_many({"read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.get("/jarvis/memory")
async def jarvis_memory():
    docs = await db.jarvis_memory.find({}, {"_id": 0}).to_list(200)
    return {"memory": {d["key"]: d["value"] for d in docs}}


@api_router.delete("/jarvis/memory/{key}")
async def jarvis_memory_delete(key: str):
    await db.jarvis_memory.delete_one({"key": key})
    return {"ok": True}


@api_router.get("/cli/jarvis")
async def cli_jarvis_install():
    """Serve the CLI script as plain text so users can `curl ... -o jarvis`."""
    from fastapi.responses import PlainTextResponse
    cli_path = Path(__file__).parent / "cli" / "jarvis.py"
    try:
        content = cli_path.read_text()
    except Exception as e:
        return PlainTextResponse(f"# error reading CLI: {e}", status_code=500)
    return PlainTextResponse(content, media_type="text/x-python")


# ================= FX STRATEGIES =================

class BacktestRequest(BaseModel):
    strategy: Literal["SMA", "Bollinger", "Contrarian", "Momentum", "ML_Classification"]
    instrument: str
    start: str
    end: str
    granularity: str = "H1"
    params: Optional[dict] = None
    trading_cost: float = 0
    source: str = "auto"


class StrategyStartRequest(BaseModel):
    kind: Literal["SMA", "Bollinger", "Contrarian", "Momentum"]
    instrument: str
    params: dict
    units: int = 1000
    poll_sec: int = 30


@api_router.post("/strategies/backtest")
async def strategies_backtest(req: BacktestRequest):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: jv._tool_backtest(
            strategy=req.strategy, instrument=req.instrument, start=req.start, end=req.end,
            granularity=req.granularity, params=req.params or {}, trading_cost=req.trading_cost, source=req.source,
        ),
    )


@api_router.post("/strategies/start")
async def strategies_start(req: StrategyStartRequest):
    risk = await te.get_risk(db)
    if risk.get("kill_switch"):
        raise HTTPException(status_code=403, detail="kill switch engaged")
    return await fxs.start_strategy(db, kind=req.kind, instrument=req.instrument,
                                     params=req.params, units=req.units, poll_sec=req.poll_sec)


@api_router.post("/strategies/{sid}/stop")
async def strategies_stop(sid: str):
    return await fxs.stop_strategy(db, sid)


@api_router.get("/strategies")
async def strategies_list():
    return {"strategies": await fxs.list_strategies(db)}


@api_router.get("/strategies/events")
async def strategies_events(strategy_id: Optional[str] = None, limit: int = 50):
    return {"events": await fxs.list_strategy_events(db, strategy_id, limit)}


# ================= MT5 BRIDGE =================

import mt5_client as mt5


@api_router.get("/mt5/status")
async def mt5_status():
    return mt5.status()


@api_router.get("/mt5/account")
async def mt5_account():
    return mt5.get_account()


@api_router.get("/mt5/positions")
async def mt5_positions():
    return mt5.get_positions()


@api_router.get("/mt5/tick")
async def mt5_tick(symbol: str):
    return mt5.get_tick(symbol)


@api_router.get("/mt5/ohlc")
async def mt5_ohlc(symbol: str, timeframe: str = "M5", count: int = 200):
    return mt5.get_ohlc(symbol, timeframe, count)


# ================= MT4 (stub) =================

import mt4_client as mt4
import price_triggers as pt


@api_router.get("/mt4/status")
async def mt4_status():
    return mt4.status()


# ================= PRICE TRIGGERS =================

class PriceAlertRequest(BaseModel):
    instrument: str
    condition: Literal["above", "below", "crosses_above", "crosses_below"]
    level: float
    action: Literal["notify", "market_order", "jarvis_prompt"] = "notify"
    order_units: Optional[int] = None
    order_stop_loss: Optional[float] = None
    jarvis_prompt: Optional[str] = None
    once: bool = True


@api_router.post("/triggers/alert")
async def trigger_create(req: PriceAlertRequest):
    return await pt.create_alert(db, **req.model_dump())


@api_router.get("/triggers/alerts")
async def trigger_list(status: Optional[str] = None):
    return {"alerts": await pt.list_alerts(db, status)}


@api_router.delete("/triggers/alerts/{aid}")
async def trigger_cancel(aid: str):
    return await pt.cancel_alert(db, aid)


# ================= APP WIRING =================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


_bg_tasks: list = []


@app.on_event("startup")
async def on_startup():
    await te.ensure_account(db)
    await te.get_risk(db)  # ensure risk doc exists
    await tg.load_subscribers(db)
    # Start telegram bot polling if configured
    if tg.is_configured():
        _bg_tasks.append(asyncio.create_task(tg.polling_loop(db, call_kimi_strict)))
        logger.info("Telegram polling task scheduled.")
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set; polling disabled.")
    # Auto-trader loop always runs (will no-op when auto_mode off / no chats)
    _bg_tasks.append(asyncio.create_task(tg.auto_trader_loop(db, call_kimi_strict, interval_sec=90)))
    # Equity snapshot loop — every 30s
    _bg_tasks.append(asyncio.create_task(_equity_snapshot_loop()))
    # JARVIS scheduler loop — every 30s
    _bg_tasks.append(asyncio.create_task(scheduler_loop(db, jv.chat, broadcast_fn=tg.broadcast_text, interval_sec=30)))
    # Price-event trigger loop — every 8s
    _bg_tasks.append(asyncio.create_task(pt.trigger_loop(db, jv.chat, broadcast_fn=tg.broadcast_text, interval_sec=8)))
    # Auto-resume any live FX strategies that were running before restart
    try:
        n = await fxs.resume_active_strategies(db)
        if n:
            logger.info(f"Resumed {n} live FX strategies")
    except Exception as e:
        logger.warning(f"strategy resume error: {e}")


async def _equity_snapshot_loop():
    while True:
        try:
            await asyncio.sleep(30)
            await te.snapshot_equity(db)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"equity snapshot error: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    for t in _bg_tasks:
        t.cancel()
    mongo_client.close()
