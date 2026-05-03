"""Entrypoint: APScheduler + Telegram send-only. No polling, no trading.

This worker produces signals and sends them to the same Telegram bot used by
forex-agent. Because it does NOT poll, it does not conflict with forex-agent.
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
from app.kronos_client import KronosForecaster
from app.oanda_fetch import OandaFetcher
from app.signal import build_signal, format_signal


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


async def run_forecast_cycle(cfg, fetcher: OandaFetcher, forecaster: KronosForecaster, bot: Bot) -> None:
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
        try:
            await bot.send_message(chat_id=cfg.telegram_chat_id, text=format_signal(sig))
        except Exception as e:
            log.error("telegram_send_failed", instrument=instrument, error=str(e))


async def main_async() -> None:
    cfg = load_config()
    log.info("config_loaded", instruments=cfg.instruments, kronos_size=cfg.kronos_size)

    fetcher = OandaFetcher(cfg.oanda_api_token, cfg.oanda_environment)
    forecaster = KronosForecaster(size=cfg.kronos_size)
    bot = Bot(token=cfg.telegram_bot_token)

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
        kwargs={"cfg": cfg, "fetcher": fetcher, "forecaster": forecaster, "bot": bot},
        id="forecast_cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("services_started", jobs=[j.id for j in scheduler.get_jobs()])
    try:
        await bot.send_message(chat_id=cfg.telegram_chat_id, text="🔮 Kronos forecaster online.")
    except Exception as e:
        log.warning("startup_ping_failed", error=str(e))

    # Run one cycle immediately so you see signals right after deploy.
    asyncio.create_task(run_forecast_cycle(cfg, fetcher, forecaster, bot))

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
