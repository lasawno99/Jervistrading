"""Per-symbol config override fetcher.

If `DASHBOARD_INSTRUMENT_CONFIGS_URL` is set in the env (e.g.
`https://your-dashboard.preview.emergentagent.com/api/instrument-configs`),
the worker polls it once per cycle. Any symbol with a stored config has its
tuning params overridden — the rest fall back to the worker's env defaults.

Failures (network blip, unreachable URL, missing entries) all fail OPEN and
return None — the worker keeps using its env-var defaults.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("instrument_config")

_cache: Dict[str, Any] = {"as_of": 0.0, "data": {}}
_TTL_SECONDS = 60.0


async def fetch_all() -> Dict[str, Dict[str, Any]]:
    """Return {symbol: params_dict} or empty dict on any error."""
    url = (os.environ.get("DASHBOARD_INSTRUMENT_CONFIGS_URL") or "").strip()
    if not url:
        return {}

    now = time.time()
    if (now - _cache["as_of"]) < _TTL_SECONDS:
        return _cache["data"]

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        log.warning("instrument_config fetch failed: %s", e)
        return _cache["data"]  # use last good cache

    data: Dict[str, Dict[str, Any]] = {}
    for entry in payload.get("configs", []):
        symbol = entry.get("symbol")
        params = entry.get("params") or {}
        if symbol and params:
            data[symbol] = params

    _cache["as_of"] = now
    _cache["data"] = data
    return data


async def for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the override params for one symbol, or None."""
    all_cfg = await fetch_all()
    return all_cfg.get(symbol)
