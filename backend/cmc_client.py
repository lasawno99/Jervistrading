"""CoinMarketCap Pro API client with shared in-memory cache.

Single source of truth for /api/market/* endpoints. Designed for the
free Basic tier (~333 calls/day) — each upstream call is gated behind
a 75-second TTL cache so a refreshing dashboard never exceeds the limit.

Key lives in /app/backend/.env as CMC_API_KEY. Never exposed to the client.
"""
from __future__ import annotations

import os
import time
import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

import httpx

log = logging.getLogger("cmc")

CMC_API_KEY = os.environ.get("CMC_API_KEY")
CMC_BASE_URL = os.environ.get("CMC_API_BASE_URL", "https://pro-api.coinmarketcap.com")
CMC_CACHE_TTL_SECONDS = int(os.environ.get("CMC_CACHE_TTL_SECONDS", "75"))

# In-memory cache: { cache_key: (timestamp, data) }
_cache: Dict[str, Tuple[float, Any]] = {}
_lock = asyncio.Lock()
_client: Optional[httpx.AsyncClient] = None

# Lightweight usage counter for observability via /api/market/status.
_daily_calls = 0
_daily_date: Optional[str] = None


def _ensure_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=CMC_BASE_URL,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"Accept": "application/json"},
        )
    return _client


def _bump_counter() -> None:
    global _daily_calls, _daily_date
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _daily_date != today:
        _daily_date = today
        _daily_calls = 0
    _daily_calls += 1


def _cache_key(endpoint: str, params: Dict[str, Any]) -> str:
    return endpoint + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))


def get_status() -> Dict[str, Any]:
    return {
        "configured": bool(CMC_API_KEY),
        "cache_entries": len(_cache),
        "calls_today": _daily_calls,
        "cache_ttl_seconds": CMC_CACHE_TTL_SECONDS,
    }


async def fetch(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Cached GET against the CMC Pro API. Returns the raw JSON payload.

    Raises RuntimeError if the key is missing or upstream returns non-200.
    """
    if not CMC_API_KEY:
        raise RuntimeError("CMC_API_KEY is not configured on the server.")

    params = params or {}
    key = _cache_key(endpoint, params)

    async with _lock:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < CMC_CACHE_TTL_SECONDS:
            return hit[1]

        client = _ensure_client()
        try:
            r = await client.get(
                endpoint,
                params=params,
                headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error contacting CMC: {e}") from e

        if r.status_code != 200:
            # Cache short error so we don't hammer the API on bad keys.
            log.warning("CMC %s returned %s: %s", endpoint, r.status_code, r.text[:200])
            raise RuntimeError(f"CMC {endpoint} -> HTTP {r.status_code}")

        data = r.json()
        _cache[key] = (time.time(), data)
        _bump_counter()
        return data


async def close() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
