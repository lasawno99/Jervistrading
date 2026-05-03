"""Entrypoint: schedule the narrative scan + push alerts to Telegram.

Signal-only. No polling, no trading.
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
from app.scorer import NarrativeScorer, Score
from app.scout import NarrativeScout
from app.state import AlertState


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

# Stages that count as arbitrage opportunities — where the signal has real value.
ACTIONABLE_STAGES = {"pre-emerging", "emerging", "breakout"}


def format_alert(s: Score) -> str:
    stage_icon = {
        "pre-emerging": "🌱",
        "emerging": "📈",
        "breakout": "🚀",
        "mainstream": "📰",
        "fading": "📉",
    }.get(s.stage, "❓")
    tickers = ", ".join(s.tickers) if s.tickers else "—"
    return (
        f"{stage_icon} Knowledge arb — {s.topic}\n"
        f"Stage: {s.stage} · confidence {s.confidence}/10\n"
        f"Thesis: {s.thesis}\n"
        f"Tickers: {tickers}\n"
        f"Risks: {s.risks}"
    )


async def run_scan(cfg, scout: NarrativeScout, scorer: NarrativeScorer,
                   state: AlertState, bot: Bot) -> None:
    log.info("scan_start", topics=len(cfg.watchlist))
    for topic in cfg.watchlist:
        try:
            evidence = await asyncio.to_thread(scout.gather, topic)
        except Exception as e:
            log.error("scout_failed", topic=topic, error=str(e))
            continue

        score = await scorer.score(evidence)
        if score is None:
            continue

        log.info(
            "scored",
            topic=score.topic,
            stage=score.stage,
            confidence=score.confidence,
            tickers=score.tickers,
        )

        if score.stage not in ACTIONABLE_STAGES:
            continue
        if score.confidence < cfg.min_confidence:
            continue
        if not state.should_send(score.topic, score.stage):
            log.info("alert_suppressed_cooldown", topic=score.topic, stage=score.stage)
            continue

        try:
            await bot.send_message(chat_id=cfg.telegram_chat_id, text=format_alert(score))
            state.mark_sent(score.topic, score.stage)
        except Exception as e:
            log.error("telegram_send_failed", topic=score.topic, error=str(e))


async def main_async() -> None:
    cfg = load_config()
    log.info("config_loaded", topics=len(cfg.watchlist), min_confidence=cfg.min_confidence)

    scout = NarrativeScout(cfg.tavily_api_key)
    scorer = NarrativeScorer(cfg.anthropic_api_key, cfg.anthropic_model)
    state = AlertState()
    bot = Bot(token=cfg.telegram_bot_token)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_scan,
        trigger=CronTrigger.from_crontab(cfg.schedule_cron, timezone="UTC"),
        kwargs={"cfg": cfg, "scout": scout, "scorer": scorer, "state": state, "bot": bot},
        id="narrative_scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("services_started", jobs=[j.id for j in scheduler.get_jobs()])

    try:
        await bot.send_message(chat_id=cfg.telegram_chat_id, text="🛰 Knowledge-arb scout online.")
    except Exception as e:
        log.warning("startup_ping_failed", error=str(e))

    # Kick one scan immediately so the first signals arrive right after deploy.
    asyncio.create_task(run_scan(cfg, scout, scorer, state, bot))

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
