"""Entrypoint: APScheduler + Telegram polling, single event loop.

Runs as a pure worker (no HTTP listener). Designed for Railway deployment.

Critical pattern: slow agent work (Claude tool loops, 5-10s) is dispatched
via `asyncio.create_task` inside Telegram handlers. The handler itself
returns fast, so a slow turn never blocks the polling loop.

Graceful shutdown: SIGTERM (Railway redeploy) and SIGINT both stop the
scheduler, the Telegram updater, and the application cleanly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.agent import Agent
from app.config import Config, load_config
from app.guardrails import GuardrailState
from app.tools.news_tool import NewsTool
from app.tools.oanda_tool import OandaTool
from app.tools.telegram_tool import TelegramSender


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()


@dataclass
class Runtime:
    """Bundle of live services passed to handlers and scheduled jobs."""
    config: Config
    agent: Agent
    oanda: OandaTool
    state: GuardrailState
    sender: TelegramSender


# ---------- handler authorization ----------------------------------------

def _is_authorized(update: Update, allowed_chat_id: str) -> bool:
    """Reject any message from a chat ID outside the allowlist."""
    chat = update.effective_chat
    if chat is None:
        return False
    try:
        return str(chat.id) == str(int(allowed_chat_id))
    except (ValueError, TypeError):
        return False


def _runtime(context: ContextTypes.DEFAULT_TYPE) -> Runtime:
    return context.application.bot_data["runtime"]


# ---------- slash command handlers ---------------------------------------

WELCOME = (
    "🤖 Forex agent online. Paper trading on OANDA practice.\n\n"
    "Commands:\n"
    "/start — this message\n"
    "/brief — on-demand market brief (no trading)\n"
    "/positions — open paper positions\n"
    "/balance — practice account summary\n"
    "/kill on|off — toggle the global kill switch\n"
    "/schedules — list active scheduled jobs\n"
    "/jarvis [text] — free-form chat with the agent"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        log.warning("unauthorized_chat", chat_id=getattr(update.effective_chat, "id", None))
        return
    await update.message.reply_text(WELCOME)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    try:
        summary = await asyncio.to_thread(rt.oanda.get_account_summary)
    except Exception as e:
        log.error("balance_failed", error=str(e))
        await update.message.reply_text(f"⚠️ OANDA error: {e}")
        return
    text = (
        f"💰 Practice account\n"
        f"Balance: {summary['balance']:.2f} {summary['currency']}\n"
        f"NAV: {summary['nav']:.2f}\n"
        f"Unrealized P&L: {summary['unrealized_pl']:.2f}"
    )
    await update.message.reply_text(text)


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    try:
        positions = await asyncio.to_thread(rt.oanda.list_positions)
    except Exception as e:
        log.error("positions_failed", error=str(e))
        await update.message.reply_text(f"⚠️ OANDA error: {e}")
        return
    if not positions:
        await update.message.reply_text("📭 No open positions.")
        return
    lines = ["📊 Open positions:"]
    for p in positions:
        lines.append(
            f"• {p['instrument']} {p['side']} {abs(p['units']):.0f} units, "
            f"unrealized {p['unrealized_pl']:+.2f}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    arg = (context.args[0].lower() if context.args else "").strip()
    if arg == "on":
        rt.state.kill_switch_active = True
        log.warning("kill_switch_on", actor=update.effective_user.id if update.effective_user else None)
        await update.message.reply_text("🛑 Kill switch ON. All trading halted.")
    elif arg == "off":
        rt.state.kill_switch_active = False
        log.warning("kill_switch_off", actor=update.effective_user.id if update.effective_user else None)
        await update.message.reply_text("✅ Kill switch OFF. Trading re-enabled.")
    else:
        status = "ON" if rt.state.kill_switch_active else "OFF"
        await update.message.reply_text(
            f"Kill switch is currently {status}. Usage: /kill on  or  /kill off"
        )


async def cmd_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("No scheduled jobs.")
        return
    lines = ["🗓️ Scheduled jobs:"]
    for j in jobs:
        next_run = j.next_run_time.isoformat() if j.next_run_time else "n/a"
        lines.append(f"• {j.id} — next: {next_run}")
    await update.message.reply_text("\n".join(lines))


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """On-demand market brief. Dispatched as a background task so the
    handler returns immediately and the polling loop is never blocked."""
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    await update.message.reply_text("⏳ Building brief…")
    asyncio.create_task(_brief_background(rt))


async def _brief_background(rt: Runtime) -> None:
    try:
        await rt.agent.run_tick(dry_run=True)  # run_tick already sends to Telegram
    except Exception as e:
        log.error("brief_failed", error=str(e))
        try:
            await rt.sender.send(f"⚠️ Brief failed: {e}")
        except Exception:
            pass


async def cmd_jarvis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free-form chat. Background task pattern: the Anthropic call (5-10s on
    tool-heavy turns) MUST NOT block the Telegram polling loop, otherwise
    queued updates can pile up or cause duplicate handler dispatch."""
    rt = _runtime(context)
    if not _is_authorized(update, rt.config.telegram_chat_id):
        return
    prompt = " ".join(context.args).strip() if context.args else ""
    if not prompt:
        await update.message.reply_text("Usage: /jarvis [your message]")
        return
    await update.message.reply_text("⏳ Thinking…")
    asyncio.create_task(
        _jarvis_background(
            rt, update.effective_chat.id, prompt, context.application
        )
    )


async def _jarvis_background(
    rt: Runtime, chat_id: int, prompt: str, application: Application
) -> None:
    try:
        result = await rt.agent.chat(prompt)
    except Exception as e:
        log.error("jarvis_failed", error=str(e))
        result = f"⚠️ Error: {e}"
    try:
        await application.bot.send_message(chat_id=chat_id, text=result[:4000])
    except Exception as e:
        log.error("jarvis_reply_failed", error=str(e))


def _register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("brief", cmd_brief))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("positions", cmd_positions))
    application.add_handler(CommandHandler("kill", cmd_kill))
    application.add_handler(CommandHandler("schedules", cmd_schedules))
    application.add_handler(CommandHandler("jarvis", cmd_jarvis))


# ---------- scheduled jobs -----------------------------------------------

async def _job_morning_brief(rt: Runtime) -> None:
    log.info("job_morning_brief_start")
    try:
        await rt.agent.run_tick(dry_run=True)
    except Exception as e:
        log.error("morning_brief_failed", error=str(e))
        try:
            await rt.sender.send(f"⚠️ Morning brief failed: {e}")
        except Exception:
            pass


async def _job_alert_scan(rt: Runtime) -> None:
    log.info("job_alert_scan_start")
    try:
        await rt.agent.run_tick(dry_run=False)
    except Exception as e:
        log.error("alert_scan_failed", error=str(e))
        try:
            await rt.sender.send(f"⚠️ Alert scan failed: {e}")
        except Exception:
            pass


async def _job_health_check(rt: Runtime) -> None:
    log.info(
        "health_check",
        kill_switch=rt.state.kill_switch_active,
        halted_today=rt.state.is_halted_today(),
        recent_orders_60s=rt.state.recent_order_count(60.0),
    )


def _register_jobs(scheduler: AsyncIOScheduler, rt: Runtime) -> None:
    # Daily 8am UTC morning brief (dry-run; no orders placed)
    scheduler.add_job(
        _job_morning_brief,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        kwargs={"rt": rt},
        id="morning_brief",
        max_instances=1,
        coalesce=True,
    )

    # Autonomous live alert scan — GATED by AUTONOMOUS_TRADING_ENABLED env var.
    # When false (default), forex-agent is conversation-only and will only
    # place orders in response to /jarvis commands from the operator.
    # jarvis-synth handles autonomous trading via its own 5-layer pipeline.
    if os.environ.get("AUTONOMOUS_TRADING_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        log.warning("autonomous_trading_enabled")
        try:
            alert_trigger = CronTrigger.from_crontab(rt.config.schedule_cron, timezone="UTC")
        except Exception as e:
            log.error(
                "schedule_cron_invalid_using_default",
                invalid_value=rt.config.schedule_cron,
                error=str(e),
                default="*/15 9-21 * * 1-5",
            )
            alert_trigger = CronTrigger.from_crontab("*/15 9-21 * * 1-5", timezone="UTC")
        scheduler.add_job(
            _job_alert_scan,
            trigger=alert_trigger,
            kwargs={"rt": rt},
            id="alert_scan",
            max_instances=1,
            coalesce=True,
        )
    else:
        log.info("autonomous_trading_disabled_command_bot_mode")

    # Heartbeat / guardrail health check every 60s
    scheduler.add_job(
        _job_health_check,
        trigger=IntervalTrigger(seconds=60),
        kwargs={"rt": rt},
        id="health_check",
        max_instances=1,
        coalesce=True,
    )


# ---------- main ----------------------------------------------------------

async def main_async() -> None:
    config = load_config()
    log.info("config_loaded", **config.safe_repr())

    state = GuardrailState()
    sender = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
    oanda = OandaTool(
        api_token=config.oanda_api_token,
        account_id=config.oanda_account_id,
        environment=config.oanda_environment,
        guardrail_state=state,
        telegram_send=sender.send,
    )
    news = NewsTool(config.tavily_api_key)
    agent = Agent(config=config, oanda=oanda, news=news, telegram=sender)

    runtime = Runtime(
        config=config, agent=agent, oanda=oanda, state=state, sender=sender
    )

    application = (
        Application.builder().token(config.telegram_bot_token).build()
    )
    application.bot_data["runtime"] = runtime
    _register_handlers(application)

    scheduler = AsyncIOScheduler(timezone="UTC")
    application.bot_data["scheduler"] = scheduler
    _register_jobs(scheduler, runtime)

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    scheduler.start()
    log.info("services_started", jobs=[j.id for j in scheduler.get_jobs()])

    try:
        await sender.send("✅ Forex agent online.")
    except Exception:
        pass

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    await stop_event.wait()
    log.info("shutdown_initiated")

    try:
        scheduler.shutdown(wait=False)
    except Exception as e:
        log.error("scheduler_shutdown_failed", error=str(e))
    try:
        await application.updater.stop()
    except Exception as e:
        log.error("updater_stop_failed", error=str(e))
    try:
        await application.stop()
        await application.shutdown()
    except Exception as e:
        log.error("application_stop_failed", error=str(e))
    log.info("shutdown_complete")


def main() -> None:
    _configure_logging()
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
