"""Claude scorer: turns raw evidence into a narrative-stage judgment."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import List, Optional

import structlog
from anthropic import Anthropic

from app.scout import TopicEvidence

log = structlog.get_logger()

SCORE_SYSTEM = """You are a markets analyst looking for "knowledge arbitrage":
real-world behavior or sentiment shifts that are visible to attentive observers
but not yet priced in by mainstream markets.

For each topic, given recent news evidence, you must judge:

1. stage: one of
   - "pre-emerging"  (niche chatter, no mainstream coverage)
   - "emerging"      (a few credible outlets are picking it up, breadth is small)
   - "breakout"      (coverage is accelerating; mainstream noticing)
   - "mainstream"    (widely covered; edge mostly gone)
   - "fading"        (was hot, now cooling)
2. confidence: integer 1–10 on how sure you are
3. thesis: one sentence on what is actually shifting
4. tickers: up to 5 publicly-tradable symbols (US equities preferred; crypto
   ok if relevant) that would plausibly benefit if the thesis plays out.
   Use real tickers. If you're not confident in tickers, return [].
5. risks: one sentence on what would invalidate the thesis

Bias toward "pre-emerging" and "emerging" stages — those are the arbitrage.
Don't hallucinate tickers. If a topic is already mainstream, say so and move on.

Return ONLY valid JSON in this exact schema:
{
  "stage": "...",
  "confidence": 7,
  "thesis": "...",
  "tickers": ["AAA","BBB"],
  "risks": "..."
}
"""


@dataclass
class Score:
    topic: str
    stage: str
    confidence: int
    thesis: str
    tickers: List[str]
    risks: str


class NarrativeScorer:
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def _user_prompt(self, ev: TopicEvidence) -> str:
        return json.dumps(
            {
                "topic": ev.topic,
                "recent_24h_article_count": ev.recent_count,
                "broad_7d_article_count": ev.broad_count,
                "recent_titles": ev.recent_titles[:10],
                "recent_domains": ev.recent_domains[:10],
                "sample_snippets": ev.sample_snippets[:5],
            },
            indent=2,
        )

    async def score(self, ev: TopicEvidence) -> Optional[Score]:
        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=700,
                system=SCORE_SYSTEM,
                messages=[{"role": "user", "content": self._user_prompt(ev)}],
            )
        except Exception as e:
            log.error("claude_score_failed", topic=ev.topic, error=str(e))
            return None

        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        text = text.strip()
        # Sometimes models wrap JSON in fences; strip them.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.error("claude_bad_json", topic=ev.topic, raw=text[:300])
            return None

        try:
            return Score(
                topic=ev.topic,
                stage=str(data["stage"]),
                confidence=int(data["confidence"]),
                thesis=str(data["thesis"]),
                tickers=[str(t).upper() for t in data.get("tickers", [])][:5],
                risks=str(data.get("risks", "")),
            )
        except (KeyError, TypeError, ValueError) as e:
            log.error("claude_schema_miss", topic=ev.topic, error=str(e))
            return None
