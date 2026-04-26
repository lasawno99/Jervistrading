"""JARVIS — unified personal AI assistant.

Single tool-using Claude agent that orchestrates:
- Paper trading (crypto/equities)
- OANDA forex
- Schedules + reminders
- Calendar
- Todos
- News + X feeds
- Web search (DuckDuckGo Instant Answer)
- Long-term memory

Talks the same on dashboard chat AND Telegram.
"""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional

import httpx

try:
    import anthropic
except Exception:
    anthropic = None  # type: ignore

import oanda_client as oa
import trading_engine as te

logger = logging.getLogger("jarvis")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_client = None
if anthropic and ANTHROPIC_KEY:
    try:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    except Exception as e:
        logger.error(f"Anthropic init failed: {e}")


def is_configured() -> bool:
    return _client is not None


SYSTEM_PROMPT = """You are JARVIS — a personal AI command center for {user_name}.

You orchestrate everything across trading, scheduling, calendar, research, todos, and memory. You always have full context of the user's account, schedule, and preferences.

Personality:
- Confident, brief, futuristic — Iron Man's Jarvis tone
- Use 1-3 short sentences unless data needs more
- Never use markdown (no asterisks, no hashes, no backticks for emphasis)
- Use bracket tags for clarity: [TRADE], [SCHEDULE], [BRIEF], [DONE]

Behavior rules:
- Before any trade, mention current price and risk
- Default paper-trade qty = $1,000 notional. Default forex qty = 1000 units. Always include a stop unless user says "no stop"
- For schedules and reminders, confirm the exact time + cron expression you'll save
- For research/news, cite source names from the data you fetched
- When user asks "what's my day" — pull calendar + open positions + today's schedules + market overview, return a concise brief
- Remember preferences via save_memory; recall them at the start of complex tasks
- If a tool returns an error, surface it plainly and propose a fix, don't silently retry
- If the kill switch is engaged, refuse trade tools and tell the user clearly

Today is {today}. Timezone: UTC."""


TOOLS = [
    # ---- Trading (paper bot) ----
    {
        "name": "paper_account",
        "description": "Get paper trading account: cash, equity, total P/L, and all positions with unrealized P/L.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "paper_trade",
        "description": "Place a paper-trade buy or sell. Universe: BTC, ETH, OIL, GOLD, TSLA, NVDA. Subject to risk gate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "enum": ["BTC", "ETH", "OIL", "GOLD", "TSLA", "NVDA"]},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "qty": {"type": "number", "description": "Quantity in units (e.g. 0.1 BTC, 10 TSLA)"},
            },
            "required": ["symbol", "side", "qty"],
        },
    },
    {
        "name": "paper_signals",
        "description": "List recent AI trading signals (pending/executed/skipped).",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    {
        "name": "paper_generate_signal",
        "description": "Ask the bot to scan markets and generate a fresh BUY/SELL signal right now.",
        "input_schema": {"type": "object", "properties": {}},
    },

    # ---- Forex (OANDA) ----
    {
        "name": "forex_price",
        "description": "Get live bid/ask for a forex pair (EUR_USD, GBP_USD, USD_JPY, XAU_USD, etc).",
        "input_schema": {"type": "object", "properties": {"instrument": {"type": "string"}}, "required": ["instrument"]},
    },
    {
        "name": "forex_account",
        "description": "Get OANDA account balance, margin, P&L.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "forex_positions",
        "description": "Get all open OANDA forex positions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "forex_market_order",
        "description": "Place a OANDA market order. Positive units=buy, negative=sell. Subject to risk gate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string"},
                "units": {"type": "integer"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
            },
            "required": ["instrument", "units"],
        },
    },
    {
        "name": "forex_close",
        "description": "Close a OANDA forex position (long/short/all).",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string"},
                "side": {"type": "string", "enum": ["long", "short", "all"]},
            },
            "required": ["instrument"],
        },
    },

    # ---- Risk ----
    {
        "name": "risk_status",
        "description": "Get current risk-gate settings: max position notional, max daily loss, kill_switch flag.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_kill_switch",
        "description": "Engage or disengage the kill switch (halts all trading across paper bot AND forex).",
        "input_schema": {"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"]},
    },

    # ---- Schedules / reminders ----
    {
        "name": "schedule_create",
        "description": "Create a recurring or one-shot schedule. JARVIS will auto-execute the prompt when due. Use cron for recurring (e.g. '30 9 * * 1-5'), or `at` for one-shot ISO time (e.g. '2026-05-01T15:00:00Z').",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "prompt": {"type": "string", "description": "What JARVIS should do/run when the schedule fires (e.g. 'send a market brief')."},
                "cron": {"type": "string", "description": "5-field cron expression. Optional."},
                "at": {"type": "string", "description": "ISO-8601 one-shot fire time (UTC). Optional."},
            },
            "required": ["title", "prompt"],
        },
    },
    {
        "name": "schedule_list",
        "description": "List all active schedules + reminders.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "schedule_cancel",
        "description": "Cancel a schedule by id.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },

    # ---- Calendar ----
    {
        "name": "calendar_list",
        "description": "Get upcoming calendar events (next 14 days).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calendar_add",
        "description": "Add a calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "time": {"type": "string", "description": "ISO-8601 UTC datetime"},
                "attendees": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "time"],
        },
    },

    # ---- Todos ----
    {
        "name": "todo_add",
        "description": "Add a to-do item.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
    {
        "name": "todo_list",
        "description": "List open todos.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "todo_complete",
        "description": "Mark a todo done by id.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },

    # ---- Feeds & research ----
    {
        "name": "news_get",
        "description": "Get latest market news headlines.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "x_feed",
        "description": "Get latest curated X/Twitter posts from market-influence accounts.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web for an answer or current info (uses DuckDuckGo Instant Answer).",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },

    # ---- Memory ----
    {
        "name": "memory_save",
        "description": "Persist a long-term preference or fact about the user (e.g. risk_tolerance='moderate', preferred_pairs=['EUR/USD']).",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Recall stored preferences and facts (returns key/value map).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ---------------- Tool implementations (async) ----------------

async def _tool_paper_account(db) -> dict:
    return await te.compute_equity(db)


async def _tool_paper_trade(db, symbol: str, side: str, qty: float) -> dict:
    return await te.execute_trade(db, symbol, side, qty, source="jarvis")


async def _tool_paper_signals(db, limit: int = 10) -> dict:
    return {"signals": await te.list_signals(db, limit)}


async def _tool_paper_generate_signal(db) -> dict:
    sig = await te.generate_signal(db, kimi_call=None)
    return sig or {"ok": False, "reason": "no edge right now"}


async def _tool_risk_status(db) -> dict:
    return await te.get_risk(db)


async def _tool_set_kill_switch(db, on: bool) -> dict:
    return await te.update_risk(db, {"kill_switch": bool(on)})


async def _tool_schedule_create(db, title: str, prompt: str, cron: Optional[str] = None, at: Optional[str] = None) -> dict:
    from scheduler import compute_next_run, validate_cron
    if not cron and not at:
        return {"error": "must provide either `cron` or `at`"}
    if cron and not validate_cron(cron):
        return {"error": f"invalid cron expression: {cron}"}
    sched = {
        "id": str(uuid.uuid4()),
        "title": title,
        "prompt": prompt,
        "cron": cron,
        "at": at,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "next_run": compute_next_run(cron, at),
    }
    await db.schedules.insert_one(dict(sched))
    return {"ok": True, "schedule": {k: v for k, v in sched.items() if k != "_id"}}


async def _tool_schedule_list(db) -> dict:
    docs = await db.schedules.find({"status": "active"}, {"_id": 0}).sort("next_run", 1).to_list(100)
    return {"schedules": docs}


async def _tool_schedule_cancel(db, id: str) -> dict:
    r = await db.schedules.update_one({"id": id}, {"$set": {"status": "cancelled"}})
    return {"ok": r.modified_count > 0}


async def _tool_calendar_list(db) -> dict:
    now = datetime.now(timezone.utc)
    docs = await db.calendar_events.find({}, {"_id": 0}).sort("time", 1).to_list(100)
    upcoming = [d for d in docs if d.get("time", "") >= now.isoformat()]
    return {"events": upcoming}


async def _tool_calendar_add(db, title: str, time: str, attendees: Optional[list] = None) -> dict:
    ev = {
        "id": str(uuid.uuid4()),
        "title": title,
        "time": time,
        "attendees": attendees or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_events.insert_one(dict(ev))
    return {"ok": True, "event": ev}


async def _tool_todo_add(db, text: str) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "text": text,
        "done": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.todos.insert_one(dict(item))
    return {"ok": True, "todo": item}


async def _tool_todo_list(db) -> dict:
    docs = await db.todos.find({"done": False}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"todos": docs}


async def _tool_todo_complete(db, id: str) -> dict:
    r = await db.todos.update_one({"id": id}, {"$set": {"done": True, "completed_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": r.modified_count > 0}


async def _tool_news(db) -> dict:
    # Reuse the same mock list used by /api/feed/news
    items = [
        ("Oil futures rally as Hormuz tensions escalate", "Reuters"),
        ("Fed signals dovish pivot; risk assets bid", "Bloomberg"),
        ("NVIDIA unveils next-gen inference accelerator", "The Verge"),
        ("Gold reclaims $2,400 as DXY softens", "FT"),
        ("Moonshot AI releases Kimi K2.5 with 256K context", "TechCrunch"),
    ]
    return {"news": [{"headline": h, "source": s} for h, s in items]}


async def _tool_x_feed(db) -> dict:
    raw = [
        ("@elonmusk", "Mars launch window opens Q3."),
        ("@naval", "Internet rewards those who build in public."),
        ("@balajis", "Sovereign individual thesis playing out."),
        ("@sama", "Compute is the new oil."),
        ("@cz_binance", "Risk management is everything."),
    ]
    return {"posts": [{"handle": h, "content": c} for h, c in raw]}


async def _tool_web_search(query: str) -> dict:
    """DuckDuckGo Instant Answer — free, no key. Returns abstract / related topics."""
    try:
        async with httpx.AsyncClient(timeout=8) as cli:
            r = await cli.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            )
            data = r.json()
        out = {
            "query": query,
            "abstract": data.get("AbstractText") or data.get("Abstract") or "",
            "source": data.get("AbstractSource") or "",
            "url": data.get("AbstractURL") or "",
            "related": [
                {"text": rt.get("Text"), "url": rt.get("FirstURL")}
                for rt in (data.get("RelatedTopics") or [])[:5]
                if isinstance(rt, dict) and rt.get("Text")
            ],
        }
        if not out["abstract"] and not out["related"]:
            out["note"] = "No instant answer; query may need a deeper search provider."
        return out
    except Exception as e:
        return {"error": str(e)}


async def _tool_memory_save(db, key: str, value: str) -> dict:
    await db.jarvis_memory.update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "key": key, "value": value}


async def _tool_memory_recall(db) -> dict:
    docs = await db.jarvis_memory.find({}, {"_id": 0}).to_list(200)
    return {"memory": {d["key"]: d["value"] for d in docs}}


# ---------------- Tool dispatcher ----------------

async def _dispatch_tool(db, tool_name: str, tool_input: dict, block_trades: bool) -> str:
    if block_trades and tool_name in (
        "paper_trade", "paper_generate_signal",
        "forex_market_order", "forex_close",
    ):
        return json.dumps({"error": "kill switch is engaged. all trading halted."})
    try:
        if tool_name == "paper_account":
            res = await _tool_paper_account(db)
        elif tool_name == "paper_trade":
            res = await _tool_paper_trade(db, **tool_input)
        elif tool_name == "paper_signals":
            res = await _tool_paper_signals(db, **tool_input)
        elif tool_name == "paper_generate_signal":
            res = await _tool_paper_generate_signal(db)
        elif tool_name == "forex_price":
            res = oa.get_price(**tool_input)
        elif tool_name == "forex_account":
            res = oa.get_account()
        elif tool_name == "forex_positions":
            res = oa.get_open_positions()
        elif tool_name == "forex_market_order":
            res = oa.place_market_order(**tool_input)
        elif tool_name == "forex_close":
            res = oa.close_position(**tool_input)
        elif tool_name == "risk_status":
            res = await _tool_risk_status(db)
        elif tool_name == "set_kill_switch":
            res = await _tool_set_kill_switch(db, **tool_input)
        elif tool_name == "schedule_create":
            res = await _tool_schedule_create(db, **tool_input)
        elif tool_name == "schedule_list":
            res = await _tool_schedule_list(db)
        elif tool_name == "schedule_cancel":
            res = await _tool_schedule_cancel(db, **tool_input)
        elif tool_name == "calendar_list":
            res = await _tool_calendar_list(db)
        elif tool_name == "calendar_add":
            res = await _tool_calendar_add(db, **tool_input)
        elif tool_name == "todo_add":
            res = await _tool_todo_add(db, **tool_input)
        elif tool_name == "todo_list":
            res = await _tool_todo_list(db)
        elif tool_name == "todo_complete":
            res = await _tool_todo_complete(db, **tool_input)
        elif tool_name == "news_get":
            res = await _tool_news(db)
        elif tool_name == "x_feed":
            res = await _tool_x_feed(db)
        elif tool_name == "web_search":
            res = await _tool_web_search(**tool_input)
        elif tool_name == "memory_save":
            res = await _tool_memory_save(db, **tool_input)
        elif tool_name == "memory_recall":
            res = await _tool_memory_recall(db)
        else:
            res = {"error": f"unknown tool {tool_name}"}
        return json.dumps(res, default=str)
    except Exception as e:
        logger.exception("tool error")
        return json.dumps({"error": str(e)})


def _serialise_blocks(content) -> list:
    out = []
    for b in content:
        if hasattr(b, "model_dump"):
            out.append(b.model_dump())
        else:
            out.append(b)
    return out


# ---------------- Public entry ----------------

async def chat(db, history: list, user_message: str, user_name: str = "Operator", max_iters: int = 8) -> Tuple[str, list]:
    """Run JARVIS with full tool calling. Returns (text_reply, updated_history)."""
    if not _client:
        return (
            "JARVIS offline. Add ANTHROPIC_API_KEY to backend/.env and restart backend to bring me online.",
            history,
        )
    history = list(history)
    history.append({"role": "user", "content": user_message})

    risk = await te.get_risk(db)
    block_trades = bool(risk.get("kill_switch"))

    sys_prompt = SYSTEM_PROMPT.format(
        user_name=user_name,
        today=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    if block_trades:
        sys_prompt += "\n\n[RISK GATE: kill switch is ON. Refuse trade tools (paper_trade, forex_market_order, forex_close, paper_generate_signal) and tell the user clearly.]"

    loop = asyncio.get_event_loop()

    for _ in range(max_iters):
        def _call(messages_):
            return _client.messages.create(
                model=CLAUDE_MODEL, max_tokens=1500,
                system=sys_prompt, tools=TOOLS, messages=messages_,
            )

        try:
            resp = await loop.run_in_executor(None, _call, history)
        except Exception as e:
            logger.exception("Claude call failed")
            return (f"Claude error: {e}", history)

        text_parts: list = []
        tool_uses: list = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        history.append({"role": "assistant", "content": _serialise_blocks(resp.content)})

        if resp.stop_reason == "end_turn" or not tool_uses:
            return ("\n".join(text_parts).strip() or "(done)", history)

        tool_results = []
        for tu in tool_uses:
            result = await _dispatch_tool(db, tu.name, tu.input or {}, block_trades=block_trades)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })
        history.append({"role": "user", "content": tool_results})

    return ("Reached tool iteration cap without completing.", history)


def status() -> dict:
    return {
        "configured": is_configured(),
        "model": CLAUDE_MODEL,
        "tool_count": len(TOOLS),
    }
