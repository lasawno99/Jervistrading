"""Agent loop: Claude (via Anthropic SDK) + tool execution.

We hand-roll the tool loop here for clarity and to avoid coupling to a specific
LangGraph version. The agent receives candle snapshots and (optionally) news,
proposes a tool call, and the orchestrator executes guarded tools.

The LLM only proposes. Guardrails decide if the order goes through.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog
from anthropic import Anthropic

from app.config import Config
from app.tools.news_tool import NewsTool
from app.tools.oanda_tool import OandaTool
from app.tools.telegram_tool import TelegramSender

log = structlog.get_logger()

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text()

MAX_TOOL_ITERATIONS = 10


def _tool_specs() -> List[Dict[str, Any]]:
    """Anthropic tool-use schemas exposed to the LLM."""
    return [
        {
            "name": "get_candles",
            "description": "Fetch the most recent OANDA candles for an instrument.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string", "description": "e.g. EUR_USD"},
                    "granularity": {
                        "type": "string",
                        "description": "M1, M5, M15, H1, H4, D",
                        "default": "M15",
                    },
                    "count": {
                        "type": "integer",
                        "description": "How many candles (max 200)",
                        "default": 50,
                    },
                },
                "required": ["instrument"],
            },
        },
        {
            "name": "get_price",
            "description": "Fetch current bid/ask for an instrument.",
            "input_schema": {
                "type": "object",
                "properties": {"instrument": {"type": "string"}},
                "required": ["instrument"],
            },
        },
        {
            "name": "list_positions",
            "description": "List open positions on the practice account.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "news_search",
            "description": (
                "Search recent news. REQUIRED before any XAU_USD trade."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "place_paper_order",
            "description": (
                "Open a paper position. stop_loss is REQUIRED. "
                "side must be 'buy' or 'sell'. units > 0."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "units": {"type": "integer"},
                    "stop_loss": {"type": "number"},
                    "take_profit": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "instrument",
                    "side",
                    "units",
                    "stop_loss",
                    "take_profit",
                    "rationale",
                ],
            },
        },
        {
            "name": "no_trade",
            "description": "Explicitly decide not to trade this tick.",
            "input_schema": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    ]


class Agent:
    """Single-shot agent invocation per scheduled tick or `/summary`."""

    def __init__(
        self,
        config: Config,
        oanda: OandaTool,
        news: NewsTool,
        telegram: TelegramSender,
    ):
        self._config = config
        self._oanda = oanda
        self._news = news
        self._telegram = telegram
        self._client = Anthropic(api_key=config.anthropic_api_key)

    async def run_tick(self, *, dry_run: bool = False) -> str:
        """Run one decision cycle across all configured instruments.

        Returns a one-line summary that has also been sent to Telegram.
        Telegram is sent on every tick — including no_trade and errors.
        """
        start = time.time()
        instruments_processed: List[str] = []
        news_headlines: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        final_action: Dict[str, Any] = {"action": "unknown", "reason": ""}

        log.info("tick_start", instruments=self._config.instruments, dry_run=dry_run)

        snapshot = await self._build_snapshot()
        instruments_processed = list(snapshot.get("instruments", {}).keys())

        user_msg = (
            "Current market snapshot:\n"
            f"{json.dumps(snapshot, indent=2)}\n\n"
            "Decide: open a position, close one, or no-trade. "
            "Respect every rule in the system prompt. "
            + ("This is a DRY RUN: do not place orders. " if dry_run else "")
            + "When done, end with a one-line summary."
        )

        summary = await self._loop(
            user_msg,
            dry_run=dry_run,
            news_headlines=news_headlines,
            tool_calls=tool_calls,
            final_action=final_action,
        )

        log.info(
            "tick_complete",
            duration_s=round(time.time() - start, 2),
            dry_run=dry_run,
            instruments_processed=instruments_processed,
            news_headlines=news_headlines,
            tool_calls=tool_calls,
            final_action=final_action,
            summary=summary,
        )
        try:
            await self._telegram.send(summary)
        except Exception:
            pass  # already logged inside sender; do not crash the tick
        return summary

    async def chat(self, message: str) -> str:
        """Free-form conversation with full tool access. Used by /jarvis.

        Same loop as `run_tick` but driven by an arbitrary user message.
        Returns the final summary; caller is responsible for sending it.
        """
        news_headlines: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        final_action: Dict[str, Any] = {"action": "chat", "reason": ""}

        log.info("chat_start", message=message[:200])
        summary = await self._loop(
            message,
            dry_run=False,
            news_headlines=news_headlines,
            tool_calls=tool_calls,
            final_action=final_action,
        )
        log.info(
            "chat_complete",
            message=message[:200],
            news_headlines=news_headlines,
            tool_calls=tool_calls,
            final_action=final_action,
            summary=summary,
        )
        return summary

    async def _build_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {"instruments": {}, "open_positions": []}
        for inst in self._config.instruments:
            try:
                candles = await asyncio.to_thread(
                    self._oanda.get_candles, inst, "M15", 50
                )
                price = await asyncio.to_thread(self._oanda.get_price, inst)
                snapshot["instruments"][inst] = {
                    "price": price,
                    "candles": candles,
                }
            except Exception as e:
                log.error("snapshot_failed", instrument=inst, error=str(e))
                snapshot["instruments"][inst] = {"error": str(e)}
        try:
            snapshot["open_positions"] = await asyncio.to_thread(
                self._oanda.list_positions
            )
        except Exception as e:
            log.error("list_positions_failed", error=str(e))
            snapshot["open_positions"] = []
        return snapshot

    async def _loop(
        self,
        user_msg: str,
        *,
        dry_run: bool,
        news_headlines: List[str],
        tool_calls: List[Dict[str, Any]],
        final_action: Dict[str, Any],
    ) -> str:
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_msg}]
        tools = _tool_specs()
        last_summary = "No summary produced."

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self._config.anthropic_model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            text_parts = [b.text for b in response.content if b.type == "text"]
            if text_parts:
                last_summary = text_parts[-1].strip().splitlines()[-1][:300]

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses or response.stop_reason == "end_turn":
                if final_action["action"] == "unknown":
                    final_action["action"] = "no_trade"
                    final_action["reason"] = last_summary
                return last_summary or "No summary produced."

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                args = tu.input or {}
                tool_calls.append({"name": tu.name, "args": args})
                result = await self._dispatch(tu.name, args, dry_run=dry_run)

                if tu.name == "news_search" and isinstance(result, dict):
                    for r in result.get("results", []) or []:
                        title = r.get("title")
                        if title:
                            news_headlines.append(title)
                if tu.name == "place_paper_order":
                    final_action["action"] = "place_paper_order"
                    final_action["reason"] = args.get("rationale", "")
                    final_action["details"] = {
                        k: args.get(k)
                        for k in ("instrument", "side", "units", "stop_loss", "take_profit")
                    }
                    final_action["result"] = result
                elif tu.name == "no_trade":
                    final_action["action"] = "no_trade"
                    final_action["reason"] = args.get("reason", "")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(result),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        if final_action["action"] == "unknown":
            final_action["action"] = "loop_exhausted"
            final_action["reason"] = last_summary
        return last_summary or "Tool loop exhausted without summary."

    async def _dispatch(
        self, name: str, args: Dict[str, Any], *, dry_run: bool
    ) -> Dict[str, Any]:
        log.info("tool_call", name=name, args=args, dry_run=dry_run)
        try:
            if name == "get_candles":
                return {
                    "candles": await asyncio.to_thread(
                        self._oanda.get_candles,
                        args["instrument"],
                        args.get("granularity", "M15"),
                        int(args.get("count", 50)),
                    )
                }
            if name == "get_price":
                return {
                    "price": await asyncio.to_thread(
                        self._oanda.get_price, args["instrument"]
                    )
                }
            if name == "list_positions":
                return {
                    "positions": await asyncio.to_thread(self._oanda.list_positions)
                }
            if name == "news_search":
                return {
                    "results": await asyncio.to_thread(
                        self._news.search,
                        args["query"],
                        int(args.get("max_results", 5)),
                    )
                }
            if name == "place_paper_order":
                if dry_run:
                    return {"status": "skipped", "reason": "dry_run"}
                return await asyncio.to_thread(
                    self._oanda.place_paper_order,
                    instrument=args["instrument"],
                    side=args["side"],
                    units=int(args["units"]),
                    stop_loss=float(args["stop_loss"]),
                    take_profit=float(args["take_profit"]),
                    rationale=args.get("rationale", ""),
                )
            if name == "no_trade":
                return {"status": "no_trade", "reason": args.get("reason", "")}
            return {"error": f"unknown tool: {name}"}
        except Exception as e:
            log.error("tool_failed", name=name, error=str(e))
            return {"error": str(e)}
