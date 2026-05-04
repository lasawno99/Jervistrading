"""Entrypoint: APScheduler + Telegram send-only. No polling, no trading.

This worker produces signals and sends them to the same Telegram bot used by
forex-agent. Because it does NOT poll, it does not conflict with forex-agent.

If DEBATE_ENABLED=true, every non-skip Kronos signal is run through a
TauricResearch-inspired bull/bear/manager debate before being published.
"""
from __future__ import annotations

import asyncio
import logging
import signal as pysignal
import sys

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from app.config import load_config
from app.debate import DebateRunner, Verdict
from app.kronos_client import KronosForecaster
from app.news_context import NewsContext
from app.oanda_fetch import OandaFetcher
from app.signal import build_signal, format_signal, Signal


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()


def format_verdict_message(s: Signal, v: Verdict) -> str:
    arrow = {"buy": "🟢 BUY", "sell": "🔴 SELL", "skip": "⚪ SKIP"}[v.final_direction]
    decision_icon = {"confirm": "✅", "downgrade": "🟡", "veto": "❌"}.get(v.decision, "❓")
    change_pct = (s.mean_target - s.current_price) / s.current_price * 100
    return (
        f"🔮 Kronos + Debate — {s.instrument}\n"
        f"{arrow} · final confidence: {v.final_confidence}  {decision_icon} {v.decision}\n"
        f"Kronos: {s.direction}/{s.confidence} · upside {s.upside_prob:.0%} · vol {s.vol_amp:.2f}x\n"
        f"Price: {s.current_price:.5f} → target: {s.mean_target:.5f} ({change_pct:+.2f}%)\n"
        f"Manager: {v.manager_summary}"
    )


async def run_forecast_cycle(
    cfg,
    fetcher: OandaFetcher,
    forecaster: KronosForecaster,
    bot: Bot,
    debater: DebateRunner = None,
    news: NewsContext = None,
) -> None:
    for instrument in cfg.instruments:
        try:
            hist = fetcher.fetch_candles(instrument, cfg.granularity, cfg.lookback + 10)
            hist = hist.iloc[-cfg.lookback:].reset_index(drop=True)
        except Exception as e:
            log.error("fetch_failed", instrument=instrument, error=str(e))
            continue
        try:
            pred = await asyncio.to_thread(
                forecaster.predict,
                hist,
                cfg.lookback,
                cfg.pred_len,
                cfg.sample_count,
            )
        except Exception as e:
            log.error("predict_failed", instrument=instrument, error=str(e))
            continue

        sig = build_signal(
            instrument,
            hist,
            pred,
            cfg.upside_prob_high,
            cfg.upside_prob_low,
            cfg.max_vol_amp,
        )
        log.info(
            "signal",
            instrument=instrument,
            direction=sig.direction,
            confidence=sig.confidence,
            upside_prob=round(sig.upside_prob, 3),
            vol_amp=round(sig.vol_amp, 3),
            mean_target=round(sig.mean_target, 5),
        )
        if sig.direction == "skip":
            continue

        # Optional multi-agent debate
        if cfg.debate_enabled and debater is not None and news is not None:
            headlines = await asyncio.to_thread(news.headlines_for, instrument)
            verdict = await debater.run(sig, headlines)
            if verdict is None:
                log.warning("debate_failed_publishing_kronos_only", instrument=instrument)
            else:
                log.info(
                    "debate_verdict",
                    instrument=instrument,
                    decision=verdict.decision,
                    final_direction=verdict.final_direction,
                    final_confidence=verdict.final_confidence,
                )
                if verdict.final_direction == "skip" or verdict.decision == "veto":
                    log.info("debate_vetoed", instrument=instrument, summary=verdict.manager_summary)
                    continue
                try:
                    await bot.send_message(
                        chat_id=cfg.telegram_chat_id,
                        text=format_verdict_message(sig, verdict),
                    )
                except Exception as e:
                    log.error("telegram_send_failed", instrument=instrument, error=str(e))
                continue

        # No debate path
        try:
            await bot.send_message(chat_id=cfg.telegram_chat_id, text=format_signal(sig))
        except Exception as e:
            log.error("telegram_send_failed", instrument=instrument, error=str(e))


async def main_async() -> None:
    cfg = load_config()
    log.info(
        "config_loaded",
        instruments=cfg.instruments,
        kronos_size=cfg.kronos_size,
        debate_enabled=cfg.debate_enabled,
    )

    fetcher = OandaFetcher(cfg.oanda_api_token, cfg.oanda_environment)
    forecaster = KronosForecaster(size=cfg.kronos_size)
    bot = Bot(token=cfg.telegram_bot_token)

    debater = None
    news = None
    if cfg.debate_enabled:
        debater = DebateRunner(cfg.anthropic_api_key, cfg.anthropic_model)
        news = NewsContext(cfg.tavily_api_key)
        log.info("debate_runner_ready", model=cfg.anthropic_model)

    # Eager model load at boot so the first scheduled run doesn't pay the cold start.
    try:
        await asyncio.to_thread(forecaster._ensure_loaded)
    except Exception as e:
        log.error("kronos_load_failed", error=str(e))
        raise

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_forecast_cycle,
        trigger=CronTrigger.from_crontab(cfg.schedule_cron, timezone="UTC"),
        kwargs={
            "cfg": cfg,
            "fetcher": fetcher,
            "forecaster": forecaster,
            "bot": bot,
            "debater": debater,
            "news": news,
        },
        id="forecast_cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("services_started", jobs=[j.id for j in scheduler.get_jobs()])
    online_msg = "🔮 Kronos forecaster online."
    if cfg.debate_enabled:
        online_msg += " Bull/Bear debate enabled."
    try:
        await bot.send_message(chat_id=cfg.telegram_chat_id, text=online_msg)
    except Exception as e:
        log.warning("startup_ping_failed", error=str(e))

    # Run one cycle immediately so you see signals right after deploy.
    asyncio.create_task(
        run_forecast_cycle(cfg, fetcher, forecaster, bot, debater, news)
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (pysignal.SIGTERM, pysignal.SIGINT):
        try:
            loop.add_signal_handler(s, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    await stop_event.wait()
    log.info("shutdown_initiated")
    scheduler.shutdown(wait=False)
    log.info("shutdown_complete")


def main() -> None:
    _configure_logging()
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
