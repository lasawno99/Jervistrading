from fastapi import FastAPI, APIRouter, HTTPException
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
import jarvis_agent as jv
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
