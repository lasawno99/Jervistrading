"""Lightweight Alpaca paper-account reader for the dashboard.

Read-only — fetches account summary + open positions. The trading worker
(`/app/jarvis-synth-alpaca/`) places orders; this module only reports state.

Falls back to a clearly-labeled mock payload when keys aren't configured so
local dev keeps working.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


def _key() -> str:
    return os.environ.get("ALPACA_API_KEY", "").strip()


def _secret() -> str:
    return os.environ.get("ALPACA_SECRET_KEY", "").strip()


def is_configured() -> bool:
    return bool(_key() and _secret())


def _headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": _key(),
        "APCA-API-SECRET-KEY": _secret(),
    }


def _request(method: str, path: str, **kwargs) -> Dict[str, Any]:
    url = f"{PAPER_BASE_URL}{path}"
    try:
        r = requests.request(method, url, headers=_headers(), timeout=10, **kwargs)
        if r.status_code >= 400:
            return {"error": f"alpaca {method} {path}: {r.status_code} {r.text[:200]}"}
        return r.json()
    except Exception as e:
        return {"error": f"alpaca {method} {path}: {e}"}


def get_account() -> Dict[str, Any]:
    if not is_configured():
        return {
            "balance": 100000.0,
            "currency": "USD",
            "unrealized_pl": 0.0,
            "equity": 100000.0,
            "buying_power": 100000.0,
            "open_position_count": 0,
            "source": "mock",
        }
    data = _request("GET", "/v2/account")
    if "error" in data:
        return data
    return {
        "id": data.get("account_number"),
        "currency": data.get("currency") or "USD",
        "balance": float(data.get("cash") or 0),
        "equity": float(data.get("equity") or 0),
        "nav": float(data.get("equity") or 0),  # Alpaca calls it equity; map to nav for parity
        "buying_power": float(data.get("buying_power") or 0),
        "long_market_value": float(data.get("long_market_value") or 0),
        "short_market_value": float(data.get("short_market_value") or 0),
        "status": data.get("status"),
        "crypto_status": data.get("crypto_status"),
        "source": "alpaca",
    }


def get_open_positions() -> Dict[str, Any]:
    if not is_configured():
        return {"positions": [], "source": "mock"}
    data = _request("GET", "/v2/positions")
    if isinstance(data, dict) and "error" in data:
        return data
    out: List[Dict[str, Any]] = []
    unrealized_total = 0.0
    for p in data:
        qty = float(p.get("qty") or 0)
        unrealized = float(p.get("unrealized_pl") or 0)
        unrealized_total += unrealized
        out.append({
            "symbol": p.get("symbol"),
            "asset_class": p.get("asset_class"),  # "us_equity" or "crypto"
            "qty": qty,
            "side": "long" if qty > 0 else ("short" if qty < 0 else "flat"),
            "market_value": float(p.get("market_value") or 0),
            "avg_entry_price": float(p.get("avg_entry_price") or 0),
            "current_price": float(p.get("current_price") or 0),
            "unrealized_pl": unrealized,
            "unrealized_plpc": float(p.get("unrealized_plpc") or 0) * 100.0,  # to %
        })
    return {
        "positions": out,
        "count": len(out),
        "unrealized_total": unrealized_total,
        "source": "alpaca",
    }


def get_recent_fills(limit: int = 50) -> Dict[str, Any]:
    """Recent FILL activities from Alpaca's account activity feed.

    Returns one row per fill (buy or sell). Alpaca FILL events don't pair
    open+close themselves, so we report each leg with its side+qty+price.
    P/L pairing happens client-side (or by joining symbol round-trips).
    """
    if not is_configured():
        return {"fills": [], "source": "mock"}
    data = _request(
        "GET", "/v2/account/activities",
        params={"activity_types": "FILL", "page_size": int(limit)},
    )
    if isinstance(data, dict) and "error" in data:
        return data
    out: List[Dict[str, Any]] = []
    for a in data or []:
        try:
            qty = float(a.get("qty") or 0)
            price = float(a.get("price") or 0)
            side = (a.get("side") or "").lower()
            out.append({
                "id": a.get("id"),
                "ts": a.get("transaction_time") or a.get("date"),
                "symbol": a.get("symbol"),
                "side": side,
                "qty": qty,
                "price": price,
                "notional": round(qty * price, 2),
                "order_id": a.get("order_id"),
                "type": a.get("type"),  # 'fill' | 'partial_fill'
                "broker": "alpaca",
            })
        except Exception:
            continue
    return {"fills": out, "source": "alpaca"}
