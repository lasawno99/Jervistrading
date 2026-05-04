"""Lightweight news fetcher for the debate context."""
from __future__ import annotations

from typing import List

import structlog
from tavily import TavilyClient

log = structlog.get_logger()


class NewsContext:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def headlines_for(self, instrument: str, max_results: int = 5) -> List[str]:
        # Translate OANDA instrument codes to tradeable names.
        query_map = {
            "EUR_USD": "EUR/USD euro dollar forex",
            "GBP_USD": "GBP/USD pound dollar forex",
            "USD_JPY": "USD/JPY dollar yen forex",
            "AUD_USD": "AUD/USD aussie dollar forex",
            "XAU_USD": "gold XAU price",
            "XAG_USD": "silver XAG price",
        }
        query = query_map.get(instrument, instrument.replace("_", "/") + " forex")
        try:
            resp = self._client.search(
                query=query,
                topic="news",
                days=1,
                max_results=max_results,
                search_depth="basic",
            )
        except Exception as e:
            log.error("news_context_failed", instrument=instrument, error=str(e))
            return []
        return [
            r.get("title", "")
            for r in resp.get("results", []) or []
            if r.get("title")
        ][:max_results]
