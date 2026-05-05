"""Boot-time configuration: read, validate, and expose env vars.

Fail fast if anything required is missing or wrong.
Never log secret values; mask them in any debug output.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

REQUIRED = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
    "OANDA_API_TOKEN", "OANDA_ACCOUNT_ID", "OANDA_ENVIRONMENT",
    "TAVILY_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "INSTRUMENTS", "GRANULARITY", "LOOKBACK", "PRED_LEN", "SAMPLE_COUNT",
    "KRONOS_SIZE", "SCHEDULE_CRON",
    "TRADING_MODE", "MAX_POSITION_UNITS", "DAILY_LOSS_LIMIT_PCT",
    "BASE_POSITION_UNITS", "MIN_RR_RATIO",
)

# Optional vars (have defaults, never crash if missing)
PROFIT_LOCK_THRESHOLD_PCT_DEFAULT = "5.0"
PROFIT_LOCK_LEDGER_PATH_DEFAULT = "/app/data/ledger.json"
PROFIT_LOCK_CHECK_INTERVAL_SECONDS_DEFAULT = "300"  # 5 min


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    anthropic_model: str
    oanda_api_token: str
    oanda_account_id: str
    oanda_environment: str
    tavily_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    instruments: List[str]
    granularity: str
    lookback: int
    pred_len: int
    sample_count: int
    kronos_size: str
    schedule_cron: str
    trading_mode: str
    max_position_units: int
    daily_loss_limit_pct: float
    base_position_units: int
    min_rr_ratio: float
    profit_lock_threshold_pct: float
    profit_lock_ledger_path: str
    profit_lock_check_interval_seconds: int


def load_config() -> Config:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    if os.environ["TRADING_MODE"].strip().lower() != "paper":
        raise RuntimeError("TRADING_MODE must be 'paper'")
    if os.environ["OANDA_ENVIRONMENT"].strip().lower() != "practice":
        raise RuntimeError("OANDA_ENVIRONMENT must be 'practice'")

    size = os.environ["KRONOS_SIZE"].strip().lower()
    if size not in ("mini", "small", "base"):
        raise RuntimeError(f"KRONOS_SIZE must be mini|small|base (got {size!r})")

    # Defensively strip whitespace/newlines from every secret-like value.
    # Mobile clipboards sometimes inject newlines mid-string when pasting.
    def _clean(name: str) -> str:
        v = os.environ[name]
        return "".join(v.split())  # removes ALL whitespace including embedded \n

    return Config(
        anthropic_api_key=_clean("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ["ANTHROPIC_MODEL"].strip(),
        oanda_api_token=_clean("OANDA_API_TOKEN"),
        oanda_account_id=_clean("OANDA_ACCOUNT_ID"),
        oanda_environment="practice",
        tavily_api_key=_clean("TAVILY_API_KEY"),
        telegram_bot_token=_clean("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_clean("TELEGRAM_CHAT_ID"),
        instruments=[i.strip() for i in os.environ["INSTRUMENTS"].split(",") if i.strip()],
        granularity=os.environ["GRANULARITY"].strip(),
        lookback=int(os.environ["LOOKBACK"]),
        pred_len=int(os.environ["PRED_LEN"]),
        sample_count=int(os.environ["SAMPLE_COUNT"]),
        kronos_size=size,
        schedule_cron=os.environ["SCHEDULE_CRON"].strip(),
        trading_mode="paper",
        max_position_units=int(os.environ["MAX_POSITION_UNITS"]),
        daily_loss_limit_pct=float(os.environ["DAILY_LOSS_LIMIT_PCT"]),
        base_position_units=int(os.environ["BASE_POSITION_UNITS"]),
        min_rr_ratio=float(os.environ["MIN_RR_RATIO"]),
        profit_lock_threshold_pct=float(
            os.environ.get("PROFIT_LOCK_THRESHOLD_PCT", PROFIT_LOCK_THRESHOLD_PCT_DEFAULT)
        ),
        profit_lock_ledger_path=os.environ.get(
            "PROFIT_LOCK_LEDGER_PATH", PROFIT_LOCK_LEDGER_PATH_DEFAULT
        ).strip(),
        profit_lock_check_interval_seconds=int(
            os.environ.get(
                "PROFIT_LOCK_CHECK_INTERVAL_SECONDS",
                PROFIT_LOCK_CHECK_INTERVAL_SECONDS_DEFAULT,
            )
        ),
    )
