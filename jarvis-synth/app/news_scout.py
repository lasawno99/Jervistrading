"""LAYER 1 — News + Macro context.

Pulls a per-instrument news snapshot AND a generic economic-calendar query
via Tavily. The economic calendar is a synthetic best-effort scrape via news
search (no premium API needed); accuracy is "good enough for context",
not a substitute for a real calendar feed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

import structlog
from tavily import TavilyClient

log = structlog.get_logger()

_INSTRUMENT_QUERIES = {
    "EUR_USD": "EUR/USD euro dollar forex Fed ECB",
    "GBP_USD": "GBP/USD pound dollar BoE forex",
    "USD_JPY": "USD/JPY dollar yen BoJ forex",
    "AUD_USD": "AUD/USD aussie dollar RBA forex",
    "XAU_USD": "gold XAU price Fed dollar inflation",
    "XAG_USD": "silver XAG price industrial demand",
}


@dataclass
class MacroContext:
    instrument_headlines: dict      # instrument -> list[str]
    economic_calendar: List[str]    # this-week event headlines
    fetched_at: str


class NewsScout:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def _search_titles(self, query: str, days: int, max_results: int = 5) -> List[str]:
        try:
            resp = self._client.search(
                query=query,
                topic="news",
                days=days,
                max_results=max_results,
                search_depth="basic",
            )
        except Exception as e:
            log.error("tavily_failed", query=query, error=str(e))
            return []
        return [
            r.get("title", "")[:160]
            for r in resp.get("results", []) or []
            if r.get("title")
        ][:max_results]

    def gather(self, instruments: List[str]) -> MacroContext:
        per_inst = {}
        for inst in instruments:
            q = _INSTRUMENT_QUERIES.get(inst, inst.replace("_", "/") + " forex")
            per_inst[inst] = self._search_titles(q, days=1, max_results=5)

        calendar = self._search_titles(
            "this week economic calendar Fed ECB BoE NFP CPI inflation rates",
            days=2,
            max_results=8,
        )
        ctx = MacroContext(
            instrument_headlines=per_inst,
            economic_calendar=calendar,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        log.info(
            "macro_context_built",
            instruments=list(per_inst.keys()),
            calendar_count=len(calendar),
        )
        return ctx
