"""Read-only HTTP sidecar for diagnostics.

Exposes 3 endpoints, all gated by header ``X-Status-Token`` matching env
``STATUS_API_TOKEN``:

  GET /health           — boot state, last cycle ts, scheduler jobs
  GET /cycles?limit=20  — last N pipeline decisions (from cycle_log JSONL)
  GET /trades?limit=20  — last N broker fills

The token check is skipped if STATUS_API_TOKEN env is unset (open mode for
local dev). Production deploys MUST set the token.
"""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import structlog
import uvicorn
from fastapi import FastAPI, Header, HTTPException

from app.cycle_log import CycleLog

log = structlog.get_logger()


def _check_token(presented: Optional[str]) -> None:
    expected = os.environ.get("STATUS_API_TOKEN", "").strip()
    if not expected:
        return  # open mode
    if not presented or presented.strip() != expected:
        raise HTTPException(status_code=401, detail="invalid X-Status-Token")


def build_app(
    *,
    worker_name: str,
    cycle_log: CycleLog,
    get_status: Callable[[], Dict[str, Any]],
    get_trades: Callable[[int], list],
) -> FastAPI:
    app = FastAPI(title=f"{worker_name} status", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health(x_status_token: Optional[str] = Header(None)):
        _check_token(x_status_token)
        out = {
            "worker": worker_name,
            "now": datetime.now(timezone.utc).isoformat(),
            **get_status(),
        }
        # Add last cycle timestamp from the log if any
        tail = cycle_log.tail(1)
        out["last_cycle_ts"] = tail[0].get("ts") if tail else None
        return out

    @app.get("/cycles")
    def cycles(limit: int = 20, x_status_token: Optional[str] = Header(None)):
        _check_token(x_status_token)
        items = cycle_log.tail(int(limit))
        items.reverse()  # newest first
        return {"count": len(items), "cycles": items}

    @app.get("/trades")
    def trades(limit: int = 20, x_status_token: Optional[str] = Header(None)):
        _check_token(x_status_token)
        try:
            return {"trades": get_trades(int(limit))}
        except Exception as e:
            log.error("status_trades_failed", error=str(e))
            return {"trades": [], "error": str(e)}

    return app


def start_in_thread(app: FastAPI, host: str = "0.0.0.0", port: int = 8080) -> threading.Thread:
    """Run uvicorn in a daemon thread so the main async pipeline isn't blocked."""

    def _run():
        cfg = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
        server = uvicorn.Server(cfg)
        # Use a fresh event loop for uvicorn (separate from APScheduler's loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    t = threading.Thread(target=_run, name="status-server", daemon=True)
    t.start()
    log.info("status_server_started", host=host, port=port)
    return t
