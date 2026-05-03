"""Tavily-backed narrative freshness probe.

For each topic we pull two windows:
  - recent: last 24h  (news topic)
  - broad:  last 7d   (web search for breadth / velocity baseline)

Counts, titles, and domains are returned so the LLM can reason about
"how early is this?" without hallucinating.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import structlog
from tavily import TavilyClient

log = structlog.get_logger()


@dataclass
class TopicEvidence:
    topic: str
    recent_count: int
    broad_count: int
    recent_titles: List[str]
    recent_domains: List[str]
    sample_snippets: List[str]


class NarrativeScout:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def _search(self, query: str, topic: str, days: int, max_results: int) -> dict:
        try:
            return self._client.search(
                query=query,
                topic=topic,
                days=days,
                max_results=max_results,
                search_depth="basic",
            )
        except Exception as e:
            log.error("tavily_search_failed", query=query, error=str(e))
            return {"results": []}

    def gather(self, topic: str) -> TopicEvidence:
        recent = self._search(topic, "news", days=1, max_results=10)
        broad = self._search(topic, "general", days=7, max_results=10)

        r_results = recent.get("results", []) or []
        b_results = broad.get("results", []) or []

        titles = [r.get("title", "")[:160] for r in r_results if r.get("title")]
        domains: List[str] = []
        for r in r_results:
            url = r.get("url", "")
            if "://" in url:
                d = url.split("://", 1)[1].split("/", 1)[0]
                domains.append(d)
        snippets = [(r.get("content") or "")[:300] for r in r_results[:5]]

        return TopicEvidence(
            topic=topic,
            recent_count=len(r_results),
            broad_count=len(b_results),
            recent_titles=titles,
            recent_domains=list(dict.fromkeys(domains)),
            sample_snippets=snippets,
        )
