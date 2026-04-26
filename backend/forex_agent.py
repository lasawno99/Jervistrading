"""Claude (Anthropic) forex agent with OANDA tool calling.

Adapted from user-provided claude_agent.py with fixes:
- added missing `import os`
- defensive client init (handles missing ANTHROPIC_API_KEY)
- max-iterations cap on the tool loop
- async wrapper for FastAPI
- tool calls routed through our oanda_client wrapper
"""

import os
import json
import asyncio
import logging
from typing import Tuple, List, Optional

from oanda_client import (
    get_price,
    get_account,
    get_open_positions,
    place_market_order,
    place_limit_order,
    close_position,
    get_trade_history,
    is_configured as oanda_configured,
)

try:
    import anthropic
except Exception:
    anthropic = None  # type: ignore

logger = logging.getLogger("forex-agent")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_client = None
if anthropic and ANTHROPIC_KEY:
    try:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    except Exception as e:
        logger.error(f"Anthropic client init failed: {e}")
        _client = None


def is_configured() -> bool:
    return _client is not None


SYSTEM_PROMPT = """You are a professional forex trading assistant with direct access to an OANDA trading account.

Your personality:
- Concise and professional — no fluff
- Always mention current price before placing any trade
- Always confirm risk (stop loss, position size) before executing
- Use [BUY] for buys, [SELL] for sells, [ANALYSIS] for analysis, [PNL] for P&L

Your rules:
- NEVER place a trade without a stop loss unless the user explicitly says "no stop loss"
- Default position size is 1000 units unless the user specifies
- Always report back the fill price and trade ID after execution
- If the user says "auto mode on" you can execute without asking for confirmation
- If auto mode is OFF (default), describe the trade you're about to make and ask "Execute? (yes/no)"
- Max risk per trade: 2% of account balance unless user overrides

When analyzing pairs, consider:
- Current bid/ask spread
- Recent price action context
- User's stated strategy or preference

Supported pairs: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD, EUR/GBP, XAU/USD (gold)

Always format numbers cleanly:
- Prices: 4-5 decimal places for forex, 2 for gold
- P&L: always show currency symbol
- Units: use K notation (1K, 10K, 100K)"""

TOOLS = [
    {
        "name": "get_price",
        "description": "Get the current live bid/ask price for a forex pair",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": "Forex pair e.g. EUR_USD, GBP_USD, USD_JPY, XAU_USD"}
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "get_account",
        "description": "Get account balance, margin, and P&L summary",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_open_positions",
        "description": "Get all currently open positions",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "place_market_order",
        "description": "Place a market order immediately at current price. Positive units = buy/long, negative = sell/short.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": "e.g. EUR_USD"},
                "units": {"type": "integer", "description": "Positive=buy, negative=sell. e.g. 1000 or -1000"},
                "stop_loss": {"type": "number", "description": "Stop loss price level"},
                "take_profit": {"type": "number", "description": "Take profit price level"},
            },
            "required": ["instrument", "units"],
        },
    },
    {
        "name": "place_limit_order",
        "description": "Place a limit order at a specific price level (GTC - Good Till Cancelled)",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string"},
                "units": {"type": "integer", "description": "Positive=buy limit, negative=sell limit"},
                "price": {"type": "number", "description": "The limit price to execute at"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
            },
            "required": ["instrument", "units", "price"],
        },
    },
    {
        "name": "close_position",
        "description": "Close an open position fully or partially by side",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": "e.g. EUR_USD"},
                "side": {"type": "string", "enum": ["long", "short", "all"], "description": "Which side to close"},
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "get_trade_history",
        "description": "Get recent closed trades and their P&L",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of trades to fetch (default 20)"}
            },
        },
    },
]


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_price":
            result = get_price(**tool_input)
        elif tool_name == "get_account":
            result = get_account()
        elif tool_name == "get_open_positions":
            result = get_open_positions()
        elif tool_name == "place_market_order":
            result = place_market_order(**tool_input)
        elif tool_name == "place_limit_order":
            result = place_limit_order(**tool_input)
        elif tool_name == "close_position":
            result = close_position(**tool_input)
        elif tool_name == "get_trade_history":
            result = get_trade_history(**tool_input)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return json.dumps(result)
    except Exception as e:
        logger.exception("tool error")
        return json.dumps({"error": str(e)})


def _serialise_blocks(content) -> list:
    """Convert anthropic block list to JSON-safe dicts for storage."""
    out = []
    for b in content:
        if hasattr(b, "model_dump"):
            out.append(b.model_dump())
        else:
            out.append(b)
    return out


def _run_agent_sync(history: list, user_message: str, max_iters: int = 6) -> Tuple[str, list]:
    if not _client:
        return (
            "Forex agent disabled. Add ANTHROPIC_API_KEY to backend/.env and restart backend.",
            history,
        )
    history = list(history)
    history.append({"role": "user", "content": user_message})

    for _ in range(max_iters):
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )
        text_parts: list = []
        tool_uses: list = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Append assistant turn (raw blocks for next-turn fidelity)
        history.append({"role": "assistant", "content": _serialise_blocks(response.content)})

        if response.stop_reason == "end_turn" or not tool_uses:
            return ("\n".join(text_parts).strip() or "(done)", history)

        # Execute tools
        tool_results = []
        for tu in tool_uses:
            result = process_tool_call(tu.name, tu.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })
        history.append({"role": "user", "content": tool_results})

    return ("Reached max tool iterations without completing.", history)


async def run_agent(history: list, user_message: str, max_iters: int = 6) -> Tuple[str, list]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_agent_sync, history, user_message, max_iters)


def status() -> dict:
    return {
        "anthropic_configured": is_configured(),
        "oanda_configured": oanda_configured(),
        "model": CLAUDE_MODEL,
    }
