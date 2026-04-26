"""OANDA REST v3 client wrapper.

Falls back to mock responses when OANDA_API_TOKEN / OANDA_ACCOUNT_ID are not set,
so the Claude forex agent can still run end-to-end in demo mode.

Trade-placing functions hard-refuse if env not configured (no accidental fills).
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger("oanda")

ENV_BASE = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def _cfg() -> dict:
    return {
        "token": os.environ.get("OANDA_API_TOKEN", "").strip(),
        "account_id": os.environ.get("OANDA_ACCOUNT_ID", "").strip(),
        "env": (os.environ.get("OANDA_ENV", "practice") or "practice").strip().lower(),
    }


def is_configured() -> bool:
    c = _cfg()
    return bool(c["token"] and c["account_id"])


def _normalize_instrument(instrument: str) -> str:
    """Accept EUR/USD, EURUSD, EUR-USD, EUR_USD → EUR_USD."""
    s = instrument.upper().replace("/", "_").replace("-", "_")
    if "_" not in s and len(s) in (6, 7):
        # e.g. EURUSD or XAUUSD
        s = s[:-3] + "_" + s[-3:]
    return s


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_cfg()['token']}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "RFC3339",
    }


def _base_url() -> str:
    env = _cfg()["env"]
    if env not in ENV_BASE:
        env = "practice"
    return ENV_BASE[env]


def _account_path() -> str:
    return f"/v3/accounts/{_cfg()['account_id']}"


def _request(method: str, path: str, **kwargs) -> dict:
    url = _base_url() + path
    try:
        r = httpx.request(method, url, headers=_headers(), timeout=20, **kwargs)
        if r.status_code >= 400:
            return {"error": f"OANDA HTTP {r.status_code}", "detail": r.text[:400]}
        return r.json()
    except Exception as e:
        logger.exception("OANDA request failed")
        return {"error": str(e)}


# ---------------- Mocks (used when not configured) ----------------

_MOCK_PRICES = {
    "EUR_USD": (1.0842, 1.0844),
    "GBP_USD": (1.2719, 1.2721),
    "USD_JPY": (151.62, 151.64),
    "USD_CHF": (0.9012, 0.9014),
    "AUD_USD": (0.6592, 0.6594),
    "USD_CAD": (1.3601, 1.3603),
    "NZD_USD": (0.6041, 0.6043),
    "EUR_GBP": (0.8523, 0.8525),
    "XAU_USD": (2418.40, 2418.90),
}


def _mock_unconfigured() -> dict:
    return {
        "error": "OANDA not configured",
        "hint": "Set OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV in backend/.env and restart backend.",
    }


# ---------------- Tool functions used by Claude agent ----------------

def get_price(instrument: str) -> dict:
    inst = _normalize_instrument(instrument)
    if not is_configured():
        bid, ask = _MOCK_PRICES.get(inst, (1.0, 1.0))
        return {
            "instrument": inst, "bid": bid, "ask": ask, "spread": round(ask - bid, 5),
            "source": "mock",
        }
    data = _request("GET", f"{_account_path()}/pricing", params={"instruments": inst})
    if "error" in data:
        return data
    prices = data.get("prices", [])
    if not prices:
        return {"error": "no price returned", "instrument": inst}
    p = prices[0]
    bid = float(p["bids"][0]["price"])
    ask = float(p["asks"][0]["price"])
    return {
        "instrument": inst, "bid": bid, "ask": ask, "spread": round(ask - bid, 5),
        "time": p.get("time"), "source": "oanda",
    }


def get_account() -> dict:
    if not is_configured():
        return {
            "balance": 100000.0, "currency": "USD", "unrealized_pl": 0.0, "margin_used": 0.0,
            "margin_available": 100000.0, "open_position_count": 0, "open_trade_count": 0,
            "source": "mock",
        }
    data = _request("GET", f"{_account_path()}/summary")
    if "error" in data:
        return data
    a = data.get("account", {})
    return {
        "id": a.get("id"),
        "currency": a.get("currency"),
        "balance": float(a.get("balance", 0)),
        "unrealized_pl": float(a.get("unrealizedPL", 0)),
        "realized_pl": float(a.get("pl", 0)),
        "margin_used": float(a.get("marginUsed", 0)),
        "margin_available": float(a.get("marginAvailable", 0)),
        "open_position_count": int(a.get("openPositionCount", 0)),
        "open_trade_count": int(a.get("openTradeCount", 0)),
        "nav": float(a.get("NAV", 0)),
        "source": "oanda",
    }


def get_open_positions() -> dict:
    if not is_configured():
        return {"positions": [], "source": "mock"}
    data = _request("GET", f"{_account_path()}/openPositions")
    if "error" in data:
        return data
    out = []
    for p in data.get("positions", []):
        long_units = float(p.get("long", {}).get("units", 0))
        short_units = float(p.get("short", {}).get("units", 0))
        unrealized = float(p.get("unrealizedPL", 0))
        out.append({
            "instrument": p.get("instrument"),
            "long_units": long_units,
            "short_units": short_units,
            "net_units": long_units + short_units,  # short_units already negative in OANDA payload
            "unrealized_pl": unrealized,
            "pl": float(p.get("pl", 0)),
        })
    return {"positions": out, "source": "oanda"}


def _check_kill_switch_sync() -> Optional[str]:
    """Synchronous best-effort risk check. Returns error string if blocked."""
    # We can't access the async DB here without a loop. The agent itself
    # is invoked from an async context that already gate-checked, so this is a
    # second-line defense via env var override.
    if os.environ.get("FOREX_TRADING_DISABLED", "").lower() in ("1", "true", "yes"):
        return "FOREX_TRADING_DISABLED env flag is set; refusing to place orders."
    return None


def place_market_order(instrument: str, units: int, stop_loss: Optional[float] = None,
                       take_profit: Optional[float] = None) -> dict:
    if not is_configured():
        return _mock_unconfigured()
    blocked = _check_kill_switch_sync()
    if blocked:
        return {"error": blocked}
    # Live-trading gate: block real-money orders unless explicit opt-in
    env = _cfg()["env"]
    live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "").lower() in ("1", "true", "yes")
    if env == "live" and not live_enabled:
        return {"error": "OANDA_ENV is 'live' but LIVE_TRADING_ENABLED is not set. Refusing real-money order."}
    inst = _normalize_instrument(instrument)
    order = {
        "type": "MARKET",
        "instrument": inst,
        "units": str(int(units)),
        "timeInForce": "FOK",
        "positionFill": "DEFAULT",
    }
    if stop_loss is not None:
        order["stopLossOnFill"] = {"price": f"{stop_loss}", "timeInForce": "GTC"}
    if take_profit is not None:
        order["takeProfitOnFill"] = {"price": f"{take_profit}", "timeInForce": "GTC"}
    data = _request("POST", f"{_account_path()}/orders", json={"order": order})
    if "error" in data:
        return data
    fill = data.get("orderFillTransaction") or {}
    return {
        "ok": True,
        "instrument": inst,
        "units": units,
        "fill_price": float(fill.get("price", 0)) if fill else None,
        "trade_id": fill.get("id"),
        "time": fill.get("time"),
        "raw": {k: data.get(k) for k in ("orderCreateTransaction", "orderFillTransaction")},
    }


def place_limit_order(instrument: str, units: int, price: float,
                      stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> dict:
    if not is_configured():
        return _mock_unconfigured()
    blocked = _check_kill_switch_sync()
    if blocked:
        return {"error": blocked}
    env = _cfg()["env"]
    live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "").lower() in ("1", "true", "yes")
    if env == "live" and not live_enabled:
        return {"error": "OANDA_ENV is 'live' but LIVE_TRADING_ENABLED is not set."}
    inst = _normalize_instrument(instrument)
    order = {
        "type": "LIMIT",
        "instrument": inst,
        "units": str(int(units)),
        "price": f"{price}",
        "timeInForce": "GTC",
    }
    if stop_loss is not None:
        order["stopLossOnFill"] = {"price": f"{stop_loss}", "timeInForce": "GTC"}
    if take_profit is not None:
        order["takeProfitOnFill"] = {"price": f"{take_profit}", "timeInForce": "GTC"}
    data = _request("POST", f"{_account_path()}/orders", json={"order": order})
    if "error" in data:
        return data
    create = data.get("orderCreateTransaction") or {}
    return {
        "ok": True,
        "instrument": inst,
        "units": units,
        "limit_price": price,
        "order_id": create.get("id"),
        "time": create.get("time"),
    }


def close_position(instrument: str, side: str = "all") -> dict:
    if not is_configured():
        return _mock_unconfigured()
    inst = _normalize_instrument(instrument)
    body: dict = {}
    if side in ("long", "all"):
        body["longUnits"] = "ALL"
    if side in ("short", "all"):
        body["shortUnits"] = "ALL"
    data = _request("PUT", f"{_account_path()}/positions/{inst}/close", json=body)
    if "error" in data:
        return data
    return {"ok": True, "instrument": inst, "side": side, "raw": data}


def get_trade_history(count: int = 20) -> dict:
    if not is_configured():
        return {"trades": [], "source": "mock"}
    data = _request("GET", f"{_account_path()}/trades", params={"state": "CLOSED", "count": count})
    if "error" in data:
        return data
    out = []
    for t in data.get("trades", []):
        out.append({
            "id": t.get("id"),
            "instrument": t.get("instrument"),
            "open_time": t.get("openTime"),
            "close_time": t.get("closeTime"),
            "initial_units": float(t.get("initialUnits", 0)),
            "price": float(t.get("price", 0)),
            "average_close_price": float(t.get("averageClosePrice", 0)) if t.get("averageClosePrice") else None,
            "realized_pl": float(t.get("realizedPL", 0)),
        })
    return {"trades": out, "source": "oanda"}
