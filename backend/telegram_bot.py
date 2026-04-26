"""Telegram bot — long polling loop using raw HTTP API via httpx.

Starts only if TELEGRAM_BOT_TOKEN env var is set.
Sends signal alerts with inline approve/skip buttons. Handles commands.
"""

import asyncio
import logging
import os
import json
import httpx
from datetime import datetime, timezone
from typing import Optional, List

from trading_engine import (
    compute_equity, execute_trade, list_trades, list_signals,
    execute_signal, skip_signal, current_price, UNIVERSE, tick_prices,
)

logger = logging.getLogger("telegram")

API_BASE = "https://api.telegram.org/bot{token}"

# Module-level state
_state = {
    "running": False,
    "auto_mode": False,
    "last_update_id": 0,
    "subscribed_chats": set(),
    "last_error": None,
    "started_at": None,
}


def is_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())


def get_state() -> dict:
    return {
        "running": _state["running"],
        "auto_mode": _state["auto_mode"],
        "configured": is_configured(),
        "subscribed_chats": list(_state["subscribed_chats"]),
        "last_error": _state["last_error"],
        "started_at": _state["started_at"],
    }


def set_auto(on: bool) -> bool:
    _state["auto_mode"] = bool(on)
    return _state["auto_mode"]


async def _api(client: httpx.AsyncClient, method: str, **params) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        r = await client.post(url, json=params, timeout=35)
        return r.json()
    except Exception as e:
        logger.error(f"telegram api {method} error: {e}")
        _state["last_error"] = str(e)
        return {"ok": False, "error": str(e)}


async def _send_message(client, chat_id: int, text: str, reply_markup: Optional[dict] = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _api(client, "sendMessage", **payload)


async def broadcast_signal(db, signal: dict):
    """Send signal to all subscribed chats with inline buttons."""
    if not is_configured() or not _state["subscribed_chats"]:
        return
    text = (
        f"<b>🛰  AI SIGNAL · {signal['action']} {signal['symbol']}</b>\n"
        f"<i>conviction {int(signal['conviction']*100)}% · 24h {signal['change_pct']:+.2f}%</i>\n\n"
        f"qty: <code>{signal['qty']}</code> @ <code>${signal['price']:,.2f}</code>\n"
        f"notional: <code>${signal['qty']*signal['price']:,.2f}</code>\n\n"
        f"💡 {signal['reason']}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{signal['id']}"},
            {"text": "❌ Skip",    "callback_data": f"skip:{signal['id']}"},
        ]]
    }
    async with httpx.AsyncClient() as client:
        for chat_id in list(_state["subscribed_chats"]):
            await _send_message(client, chat_id, text, keyboard)


async def _handle_command(client, db, chat_id: int, text: str, kimi_call):
    parts = text.strip().split()
    cmd = parts[0].lower().split("@")[0]

    if cmd == "/start":
        _state["subscribed_chats"].add(chat_id)
        await _send_message(client, chat_id, (
            "🤖 <b>JARVIS Trading Bot online</b>\n"
            "Powered by Kimi K2.5 · paper trading mode\n\n"
            "Commands:\n"
            "/status · balance + positions\n"
            "/auto on|off · toggle AI auto-trader\n"
            "/buy SYM QTY · manual buy\n"
            "/sell SYM QTY · manual sell\n"
            "/signal · request fresh AI signal now\n"
            "/trades · last 10 trades\n"
            "/help · this menu"
        ))
    elif cmd == "/help":
        await _send_message(client, chat_id, "Use /start to see all commands. Universe: " + ", ".join(UNIVERSE.keys()))
    elif cmd == "/status":
        eq = await compute_equity(db)
        lines = [
            "<b>📊 Account</b>",
            f"equity: <code>${eq['equity']:,.2f}</code>",
            f"cash:   <code>${eq['cash']:,.2f}</code>",
            f"P/L:    <code>${eq['total_pl']:,.2f} ({eq['total_pl_pct']:+.2f}%)</code>",
            f"auto-mode: <b>{'ON' if _state['auto_mode'] else 'OFF'}</b>",
        ]
        if eq["positions"]:
            lines.append("\n<b>Positions</b>")
            for p in eq["positions"]:
                lines.append(f"• {p['symbol']}  qty {p['qty']}  @${p['entry']:,.2f}  PL <code>${p['pl']:,.2f} ({p['pl_pct']:+.2f}%)</code>")
        else:
            lines.append("\n<i>no open positions</i>")
        await _send_message(client, chat_id, "\n".join(lines))
    elif cmd == "/auto":
        if len(parts) >= 2 and parts[1].lower() in ("on", "off"):
            set_auto(parts[1].lower() == "on")
        await _send_message(client, chat_id, f"auto-mode: <b>{'ON' if _state['auto_mode'] else 'OFF'}</b>")
    elif cmd in ("/buy", "/sell"):
        if len(parts) < 3:
            await _send_message(client, chat_id, f"usage: {cmd} SYMBOL QTY")
            return
        sym, qty_s = parts[1].upper(), parts[2]
        try:
            qty = float(qty_s)
        except Exception:
            await _send_message(client, chat_id, "qty must be a number")
            return
        side = "buy" if cmd == "/buy" else "sell"
        res = await execute_trade(db, sym, side, qty, source="telegram-manual")
        if res["ok"]:
            t = res["trade"]
            await _send_message(client, chat_id, f"✅ {side.upper()} {t['qty']} {t['symbol']} @ <code>${t['price']:,.2f}</code>  (notional ${t['value']:,.2f})")
        else:
            await _send_message(client, chat_id, f"❌ {res['error']}")
    elif cmd == "/signal":
        from trading_engine import generate_signal
        sig = await generate_signal(db, kimi_call)
        if not sig:
            await _send_message(client, chat_id, "<i>no actionable edge right now. market is quiet.</i>")
        else:
            _state["subscribed_chats"].add(chat_id)
            await broadcast_signal(db, sig)
    elif cmd == "/trades":
        trades = await list_trades(db, 10)
        if not trades:
            await _send_message(client, chat_id, "<i>no trades yet.</i>")
            return
        lines = ["<b>Last trades</b>"]
        for t in trades:
            lines.append(f"• {t['side'].upper()} {t['qty']} {t['symbol']} @${t['price']:,.2f}  <i>{t['source']}</i>")
        await _send_message(client, chat_id, "\n".join(lines))
    else:
        await _send_message(client, chat_id, "unknown command. /help")


async def _handle_callback(client, db, cb: dict):
    data = cb.get("data", "")
    chat_id = cb["message"]["chat"]["id"]
    cb_id = cb["id"]
    if ":" not in data:
        return
    action, sig_id = data.split(":", 1)
    if action == "approve":
        res = await execute_signal(db, sig_id)
        text = "✅ executed" if res.get("ok") else f"❌ {res.get('error')}"
    elif action == "skip":
        await skip_signal(db, sig_id)
        text = "↪️ skipped"
    else:
        text = "?"
    await _api(client, "answerCallbackQuery", callback_query_id=cb_id, text=text)
    await _send_message(client, chat_id, f"<i>signal {sig_id[:8]}…</i> {text}")


async def polling_loop(db, kimi_call):
    """Main long-polling loop. Resilient — restarts on errors."""
    if not is_configured():
        logger.info("Telegram not configured (no TELEGRAM_BOT_TOKEN). Bot disabled.")
        return
    _state["running"] = True
    _state["started_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Telegram polling loop started")

    async with httpx.AsyncClient() as client:
        while _state["running"]:
            try:
                resp = await _api(
                    client, "getUpdates",
                    offset=_state["last_update_id"] + 1,
                    timeout=25,
                    allowed_updates=["message", "callback_query"],
                )
                if not resp.get("ok"):
                    err = resp.get("description") or resp.get("error", "unknown")
                    _state["last_error"] = err
                    logger.error(f"getUpdates not ok: {err}")
                    await asyncio.sleep(5)
                    continue
                for upd in resp.get("result", []):
                    _state["last_update_id"] = upd["update_id"]
                    if "message" in upd:
                        msg = upd["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        if text.startswith("/"):
                            await _handle_command(client, db, chat_id, text, kimi_call)
                        else:
                            _state["subscribed_chats"].add(chat_id)
                            await _send_message(client, chat_id, "<i>tip: use /help</i>")
                    elif "callback_query" in upd:
                        await _handle_callback(client, db, upd["callback_query"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                _state["last_error"] = str(e)
                logger.exception(f"polling loop error: {e}")
                await asyncio.sleep(5)
    _state["running"] = False
    logger.info("Telegram polling loop stopped")


async def auto_trader_loop(db, kimi_call, interval_sec: int = 90):
    """Periodically generate signals when auto-mode is ON."""
    from trading_engine import generate_signal
    logger.info("Auto-trader loop started")
    while True:
        try:
            await asyncio.sleep(interval_sec)
            tick_prices()
            if not _state["auto_mode"]:
                continue
            if not _state["subscribed_chats"]:
                continue
            sig = await generate_signal(db, kimi_call)
            if sig:
                await broadcast_signal(db, sig)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"auto trader error: {e}")
