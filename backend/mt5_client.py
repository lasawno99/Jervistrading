"""MT5 client wrapper.

Connects to a MetaTrader 5 RPyC server running on a Windows machine
(see https://github.com/HydrogenB/OpenClaw-MT5-python-bridge for the server).

If MT5_RPYC_HOST is not set, every function returns a structured
"not configured" error so JARVIS can degrade gracefully.

Recommended setup: run the MT5 server on Windows + a Cloudflare Tunnel
to expose it. Then set MT5_RPYC_HOST in backend/.env to the tunnel URL.
"""

import logging
import os
import time
from typing import Optional

try:
    import rpyc
except Exception:
    rpyc = None  # type: ignore

logger = logging.getLogger("mt5")

_conn = None
_conn_ts = 0.0


def _cfg() -> dict:
    return {
        "host": os.environ.get("MT5_RPYC_HOST", "").strip(),
        "port": int(os.environ.get("MT5_RPYC_PORT", "18812").strip() or 18812),
    }


def is_configured() -> bool:
    return bool(rpyc) and bool(_cfg()["host"])


def _connect():
    global _conn, _conn_ts
    if not is_configured():
        return None
    cfg = _cfg()
    # Reuse connection for 5 minutes
    if _conn is not None and (time.time() - _conn_ts) < 300:
        try:
            _conn.ping()
            return _conn
        except Exception:
            _conn = None
    try:
        _conn = rpyc.connect(
            cfg["host"], cfg["port"],
            config={"allow_pickle": True, "sync_request_timeout": 30},
        )
        _conn_ts = time.time()
        return _conn
    except Exception as e:
        logger.warning(f"MT5 connect failed: {e}")
        _conn = None
        return None


def _not_configured() -> dict:
    return {
        "error": "MT5 not configured",
        "hint": "Set MT5_RPYC_HOST (and optionally MT5_RPYC_PORT, default 18812) in backend/.env. Server: github.com/HydrogenB/OpenClaw-MT5-python-bridge",
    }


def _call(method: str, **kwargs) -> dict:
    """Call any method on the remote MT5 service."""
    if not is_configured():
        return _not_configured()
    conn = _connect()
    if not conn:
        return {"error": f"MT5 unreachable at {_cfg()['host']}:{_cfg()['port']}"}
    try:
        svc = conn.root
        fn = getattr(svc, method, None)
        if fn is None:
            return {"error": f"MT5 server has no method {method}"}
        result = fn(**kwargs)
        # rpyc returns netref objects; convert to plain dict if possible
        try:
            return rpyc.classic.obtain(result)
        except Exception:
            return result if isinstance(result, dict) else {"result": str(result)}
    except Exception as e:
        logger.exception("MT5 call failed")
        return {"error": str(e)}


# ---------------- Public functions used by JARVIS tools ----------------

def status() -> dict:
    cfg = _cfg()
    if not is_configured():
        return {"configured": False, "rpyc_installed": rpyc is not None}
    info = _call("ping")
    return {"configured": True, "host": cfg["host"], "port": cfg["port"], "ping": info}


def get_account() -> dict:
    return _call("get_account_info")


def get_positions() -> dict:
    return _call("get_open_positions")


def get_symbol_info(symbol: str) -> dict:
    return _call("get_symbol_info", symbol=symbol)


def get_tick(symbol: str) -> dict:
    return _call("get_tick", symbol=symbol)


def get_ohlc(symbol: str, timeframe: str = "M5", count: int = 200) -> dict:
    """timeframe in {M1,M5,M15,M30,H1,H4,D1,W1,MN1}"""
    return _call("get_ohlc", symbol=symbol, timeframe=timeframe, count=count)


def market_order(symbol: str, side: str, volume: float,
                 stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                 magic: int = 0, comment: str = "JARVIS") -> dict:
    if os.environ.get("FOREX_TRADING_DISABLED", "").lower() in ("1", "true", "yes"):
        return {"error": "FOREX_TRADING_DISABLED env flag set; refusing to send orders."}
    return _call(
        "market_order",
        symbol=symbol, side=side.lower(), volume=float(volume),
        stop_loss=stop_loss, take_profit=take_profit,
        magic=int(magic), comment=comment,
    )


def limit_order(symbol: str, side: str, volume: float, price: float,
                stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                magic: int = 0, comment: str = "JARVIS") -> dict:
    if os.environ.get("FOREX_TRADING_DISABLED", "").lower() in ("1", "true", "yes"):
        return {"error": "FOREX_TRADING_DISABLED env flag set."}
    return _call(
        "limit_order",
        symbol=symbol, side=side.lower(), volume=float(volume), price=float(price),
        stop_loss=stop_loss, take_profit=take_profit,
        magic=int(magic), comment=comment,
    )


def close_position(ticket: int) -> dict:
    return _call("close_position", ticket=int(ticket))
