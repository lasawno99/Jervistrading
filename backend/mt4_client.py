"""MT4 stub — placeholder for future MetaTrader 4 integration.

MT4 has no official Python library. The standard bridge is a custom MQL4
Expert Advisor (EA) running on Windows + a ZeroMQ or socket connection.

When user is ready: install Darwinex `dwx-zeromq-connector` EA in MT4,
expose its REQ/PULL ports via Cloudflare Tunnel, set MT4_ZMQ_HOST in .env.
"""
import os


def is_configured() -> bool:
    return bool(os.environ.get("MT4_ZMQ_HOST", "").strip())


def status() -> dict:
    return {
        "configured": is_configured(),
        "note": "MT4 needs an MQL4 Expert Advisor on a Windows MT4 terminal exposing a ZeroMQ bridge. Recommended: github.com/darwinex/dwxconnect (DWX-ZeroMQ-Connector). Then set MT4_ZMQ_HOST in backend/.env.",
    }


def _not_configured() -> dict:
    return {
        "error": "MT4 not configured",
        "hint": "Install DWX-ZeroMQ-Connector EA on Windows MT4, expose port via Cloudflare Tunnel, set MT4_ZMQ_HOST in backend/.env.",
    }


def get_account() -> dict:
    return _not_configured()


def get_positions() -> dict:
    return _not_configured()


def market_order(*args, **kwargs) -> dict:
    return _not_configured()


def close_position(*args, **kwargs) -> dict:
    return _not_configured()
