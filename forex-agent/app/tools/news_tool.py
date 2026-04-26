"""Tavily-backed news search."""
from __future__ import annotations

from typing import List

import structlog
from tavily import TavilyClient

log = structlog.get_logger()


class NewsTool:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        """Return a list of {title, url, content} dicts for the query."""
        try:
            resp = self._client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
                topic="news",
            )
        except Exception as e:
            log.error("tavily_search_failed", query=query, error=str(e))
            raise
        results = resp.get("results", []) if isinstance(resp, dict) else []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:500],
            }
            for r in results
        ]
