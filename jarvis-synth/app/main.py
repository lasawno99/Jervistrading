"""Entrypoint: orchestrates the full pipeline on a schedule.

Layer 1 (News+Macro)  →  Layer 2 (Tauric 7-agent)  →  Layer 3 (Kronos)  →
Layer 4 (JARVIS synth)  →  Layer 5 (Risk Guard + OANDA execution)
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
from app.guardrails import GuardrailState
from app.kronos_client import KronosForecaster
from app.news_scout import NewsScout
from app.oanda_exec import OandaExecutor
from app.oanda_fetch import OandaFetcher
from app.signal import build_signal
from app.synth import synthesize
from app.tauric import TauricDebate


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


def format_decision(instrument: str, decision, kronos_sig) -> str:
    icon = {"LONG": "🟢", "SHORT": "🔴", "HOLD": "⚪"}[decision.action]
    units = decision.units if decision.action != "HOLD" else 0
    return (
        f"🧠 JARVIS Synth — {instrument}\n"
        f"{icon} {decision.action}  units: {units}\n"
        f"Tauric: {decision.tauric_verdict} ({decision.tauric_confidence}/10)  "
        f"· Kronos: {decision.kronos_direction} ({decision.kronos_confidence})\n"
        f"Price → target: {kronos_sig.current_price:.5f} → {kronos_sig.mean_target:.5f}\n"
        f"{decision.reasoning[:600]}"
    )


async def run_pipeline(
    cfg, fetcher, forecaster, scout, debate, executor, bot
) -> None:
    log.info("pipeline_tick_start", instruments=cfg.instruments)
    macro = await asyncio.to_thread(scout.gather, cfg.instruments)

    for instrument in cfg.instruments:
        try:
            hist = await asyncio.to_thread(
                fetcher.fetch_candles, instrument, cfg.granularity, cfg.lookback + 10
            )
            hist = hist.iloc[-cfg.lookback:].reset_index(drop=True)
        except Exception as e:
            log.error("layer3_fetch_failed", instrument=instrument, error=str(e))
            continue

        try:
            pred = await asyncio.to_thread(
                forecaster.predict, hist, cfg.lookback, cfg.pred_len, cfg.sample_count
            )
        except Exception as e:
            log.error("layer3_predict_failed", instrument=instrument, error=str(e))
            continue

        kronos_sig = build_signal(
            instrument, hist, pred,
            upside_high=0.65, upside_low=0.35, max_vol_amp=2.0,
        )
        log.info("layer3_kronos_signal", instrument=instrument,
                 direction=kronos_sig.direction, confidence=kronos_sig.confidence,
                 upside_prob=round(kronos_sig.upside_prob, 3))

        # Layer 2: Tauric debate (7 agents)
        verdict = await debate.run(
            instrument=instrument,
            macro_headlines=macro.instrument_headlines.get(instrument, []),
            calendar=macro.economic_calendar,
            candles=hist,
            kronos_signal=kronos_sig,
        )
        if verdict is None:
            log.warning("layer2_debate_failed", instrument=instrument)
            continue
        log.info("layer2_tauric_verdict", instrument=instrument,
                 verdict=verdict.verdict, confidence=verdict.confidence,
                 fundamentals=verdict.fundamentals[:400],
                 sentiment=verdict.sentiment[:400],
                 technical=verdict.technical[:400],
                 bull=verdict.bull[:400],
                 bear=verdict.bear[:400],
                 trader=verdict.trader[:400],
                 risk_manager=verdict.risk_manager[:400])

        # Layer 4: synthesis
        decision = synthesize(instrument, verdict, kronos_sig, cfg.base_position_units)
        log.info("layer4_decision", instrument=instrument,
                 action=decision.action, units=decision.units)

        # Telegram report (every cycle, regardless of action)
        try:
            await bot.send_message(
                chat_id=cfg.telegram_chat_id,
                text=format_decision(instrument, decision, kronos_sig),
            )
        except Exception as e:
            log.error("telegram_send_failed", instrument=instrument, error=str(e))

        # Layer 5: execution (only if not HOLD)
        if decision.action == "HOLD":
            continue
        side = "buy" if decision.action == "LONG" else "sell"
        # Conviction-based R:R: confidence 9-10 → 2.5:1, 7-8 → 2:1, 5-6 → 1.5:1
        rr = 2.5 if verdict.confidence >= 9 else (2.0 if verdict.confidence >= 7 else 1.5)
        result = await asyncio.to_thread(
            executor.execute,
            instrument=instrument,
            side=side,
            units=decision.units,
            rationale=decision.reasoning[:200],
            rr_ratio=rr,
            sl_pips=10.0,
        )
        log.info("layer5_execution", instrument=instrument, result=result)
        try:
            await bot.send_message(
                chat_id=cfg.telegram_chat_id,
                text=f"🎯 Order — {instrument} {side.upper()} {decision.units}u: {result.get('status')}"
                     + (f" @ {result.get('fill_price')}" if result.get('fill_price') else "")
                     + (f"\nRejected: {result.get('reason')}" if result.get('status') in ('rejected', 'error') else ""),
            )
        except Exception:
            pass


async def main_async() -> None:
    cfg = load_config()
    log.info("config_loaded", instruments=cfg.instruments,
             base_units=cfg.base_position_units, kronos_size=cfg.kronos_size)

    state = GuardrailState()
    bot = Bot(token=cfg.telegram_bot_token)

    async def _send(text: str) -> None:
        await bot.send_message(chat_id=cfg.telegram_chat_id, text=text)

    fetcher = OandaFetcher(cfg.oanda_api_token, cfg.oanda_environment)
    forecaster = KronosForecaster(size=cfg.kronos_size)
    scout = NewsScout(cfg.tavily_api_key)
    debate = TauricDebate(cfg.anthropic_api_key, cfg.anthropic_model)
    executor = OandaExecutor(
        api_token=cfg.oanda_api_token,
        account_id=cfg.oanda_account_id,
        environment=cfg.oanda_environment,
        guardrail_state=state,
        min_rr_ratio=cfg.min_rr_ratio,
        telegram_send=_send,
    )

    log.info("loading_kronos")
    try:
        await asyncio.to_thread(forecaster._ensure_loaded)
    except Exception as e:
        log.error("kronos_load_failed", error=str(e))
        raise

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger.from_crontab(cfg.schedule_cron, timezone="UTC"),
        kwargs={
            "cfg": cfg, "fetcher": fetcher, "forecaster": forecaster,
            "scout": scout, "debate": debate, "executor": executor, "bot": bot,
        },
        id="full_pipeline",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("services_started", jobs=[j.id for j in scheduler.get_jobs()])

    try:
        await _send("🧠 JARVIS Synth online — full 5-layer pipeline armed.")
    except Exception as e:
        log.warning("startup_ping_failed", error=str(e))

    # Kick one cycle immediately
    asyncio.create_task(
        run_pipeline(cfg, fetcher, forecaster, scout, debate, executor, bot)
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
