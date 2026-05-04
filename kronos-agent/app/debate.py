"""Multi-agent debate over a Kronos signal.

Architecture inspired by TauricResearch/TradingAgents (bull/bear/manager
pattern). Adapted for forex + Claude.

Flow:
  1. Bull researcher argues FOR the Kronos direction.
  2. Bear researcher argues AGAINST it.
  3. Risk manager synthesizes both, returns final verdict + adjusted confidence.

Each researcher gets the Kronos signal, recent candles, and news context.
The manager returns a strict JSON verdict so the worker can act on it.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import List, Optional

import structlog
from anthropic import Anthropic

from app.signal import Signal

log = structlog.get_logger()


@dataclass
class Verdict:
    decision: str           # "confirm", "veto", "downgrade"
    final_direction: str    # "buy", "sell", "skip"
    final_confidence: str   # "high", "medium", "low"
    bull_thesis: str
    bear_thesis: str
    manager_summary: str


_BULL_SYSTEM = """You are the BULL researcher in a forex trading debate.
The Kronos quant model has produced a directional signal. Your job is to
argue FOR the trade given the price action and news context.

Rules:
- Ground every claim in the actual numbers/headlines provided. No vague macro talk.
- If the signal is BUY, advocate for it. If SELL, argue why downside is real.
- Address counterarguments preemptively.
- Be terse: 4-6 sentences max. Punchy reasoning over verbose lists.
"""

_BEAR_SYSTEM = """You are the BEAR researcher in a forex trading debate.
The Kronos quant model has produced a directional signal AND a bull researcher
has argued for it. Your job is to argue AGAINST the trade — find the holes.

Rules:
- Ground every claim in the actual numbers/headlines provided. No vague doom.
- Look specifically for: stretched moves, weak momentum, conflicting headlines,
  unfavorable session timing, vol amplification too high, mean target too close.
- Engage with the bull's specific points; don't just list generic risks.
- Be terse: 4-6 sentences max.
"""

_MANAGER_SYSTEM = """You are the RISK MANAGER. Two researchers have debated
a Kronos forex signal. Decide the final action.

Rules:
- "confirm" if the bull case clearly wins on merit.
- "downgrade" if the case is real but weaker than Kronos suggested (e.g. flip
  confidence high → medium, or medium → low).
- "veto" if the bear case credibly invalidates the trade.
- Default toward "veto" / "downgrade" when in doubt — skipping is free.

Return ONLY valid JSON in this exact schema:
{
  "decision": "confirm" | "downgrade" | "veto",
  "final_direction": "buy" | "sell" | "skip",
  "final_confidence": "high" | "medium" | "low",
  "manager_summary": "one sentence on why"
}
"""


def _signal_block(s: Signal, news_titles: List[str]) -> str:
    return json.dumps(
        {
            "instrument": s.instrument,
            "kronos_direction": s.direction,
            "kronos_confidence": s.confidence,
            "current_price": round(s.current_price, 5),
            "mean_target": round(s.mean_target, 5),
            "expected_move_pct": round(
                (s.mean_target - s.current_price) / s.current_price * 100, 3
            ),
            "upside_probability": round(s.upside_prob, 3),
            "vol_amplification": round(s.vol_amp, 3),
            "recent_news_headlines": news_titles[:5],
        },
        indent=2,
    )


class DebateRunner:
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def _ask(self, system: str, user: str, max_tokens: int = 600) -> str:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            log.error("debate_llm_failed", error=str(e))
            return ""
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    async def run(self, signal: Signal, news_titles: List[str]) -> Optional[Verdict]:
        if signal.direction == "skip":
            return None

        block = _signal_block(signal, news_titles)

        bull = await asyncio.to_thread(
            self._ask, _BULL_SYSTEM, f"Signal context:\n{block}\n\nMake the bull case."
        )
        if not bull:
            return None

        bear_user = (
            f"Signal context:\n{block}\n\n"
            f"Bull researcher said:\n{bull}\n\n"
            "Now make the bear case."
        )
        bear = await asyncio.to_thread(self._ask, _BEAR_SYSTEM, bear_user)
        if not bear:
            return None

        manager_user = (
            f"Signal context:\n{block}\n\n"
            f"BULL:\n{bull}\n\n"
            f"BEAR:\n{bear}\n\n"
            "Return JSON verdict per schema."
        )
        manager_raw = await asyncio.to_thread(
            self._ask, _MANAGER_SYSTEM, manager_user, max_tokens=400
        )
        if manager_raw.startswith("```"):
            manager_raw = manager_raw.strip("`")
            if manager_raw.lower().startswith("json"):
                manager_raw = manager_raw[4:].lstrip()
        try:
            decision_data = json.loads(manager_raw)
        except json.JSONDecodeError:
            log.error("debate_bad_json", raw=manager_raw[:300])
            return None

        return Verdict(
            decision=str(decision_data.get("decision", "veto")),
            final_direction=str(decision_data.get("final_direction", "skip")),
            final_confidence=str(decision_data.get("final_confidence", "low")),
            bull_thesis=bull,
            bear_thesis=bear,
            manager_summary=str(decision_data.get("manager_summary", "")),
        )
