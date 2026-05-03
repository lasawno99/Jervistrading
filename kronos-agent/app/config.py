"""Config loader for kronos-agent. Fail fast on missing vars."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

REQUIRED = (
    "OANDA_API_TOKEN",
    "OANDA_ACCOUNT_ID",
    "OANDA_ENVIRONMENT",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "INSTRUMENTS",
    "GRANULARITY",
    "LOOKBACK",
    "PRED_LEN",
    "SAMPLE_COUNT",
    "SCHEDULE_CRON",
    "UPSIDE_PROB_HIGH",
    "UPSIDE_PROB_LOW",
    "MAX_VOL_AMP",
    "KRONOS_SIZE",
)


@dataclass(frozen=True)
class Config:
    oanda_api_token: str
    oanda_account_id: str
    oanda_environment: str
    telegram_bot_token: str
    telegram_chat_id: str
    instruments: List[str]
    granularity: str
    lookback: int
    pred_len: int
    sample_count: int
    schedule_cron: str
    upside_prob_high: float
    upside_prob_low: float
    max_vol_amp: float
    kronos_size: str


def load_config() -> Config:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    env = os.environ["OANDA_ENVIRONMENT"].strip().lower()
    if env != "practice":
        raise RuntimeError(f"OANDA_ENVIRONMENT must be 'practice' (got {env!r})")

    size = os.environ["KRONOS_SIZE"].strip().lower()
    if size not in ("mini", "small", "base"):
        raise RuntimeError(f"KRONOS_SIZE must be mini|small|base (got {size!r})")

    return Config(
        oanda_api_token=os.environ["OANDA_API_TOKEN"],
        oanda_account_id=os.environ["OANDA_ACCOUNT_ID"],
        oanda_environment=env,
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        instruments=[i.strip() for i in os.environ["INSTRUMENTS"].split(",") if i.strip()],
        granularity=os.environ["GRANULARITY"].strip(),
        lookback=int(os.environ["LOOKBACK"]),
        pred_len=int(os.environ["PRED_LEN"]),
        sample_count=int(os.environ["SAMPLE_COUNT"]),
        schedule_cron=os.environ["SCHEDULE_CRON"].strip(),
        upside_prob_high=float(os.environ["UPSIDE_PROB_HIGH"]),
        upside_prob_low=float(os.environ["UPSIDE_PROB_LOW"]),
        max_vol_amp=float(os.environ["MAX_VOL_AMP"]),
        kronos_size=size,
    )
