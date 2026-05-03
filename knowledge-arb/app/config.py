"""Config for knowledge-arb. Fail fast on missing vars."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

REQUIRED = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "TAVILY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "WATCHLIST",
    "SCHEDULE_CRON",
    "MIN_CONFIDENCE",
)


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    anthropic_model: str
    tavily_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    watchlist: List[str]
    schedule_cron: str
    min_confidence: int


def load_config() -> Config:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    watchlist = [t.strip() for t in os.environ["WATCHLIST"].split(",") if t.strip()]
    if not watchlist:
        raise RuntimeError("WATCHLIST must contain at least one topic")
    try:
        min_conf = int(os.environ["MIN_CONFIDENCE"])
        if not 1 <= min_conf <= 10:
            raise ValueError
    except ValueError as e:
        raise RuntimeError("MIN_CONFIDENCE must be an int 1..10") from e

    return Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        anthropic_model=os.environ["ANTHROPIC_MODEL"],
        tavily_api_key=os.environ["TAVILY_API_KEY"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        watchlist=watchlist,
        schedule_cron=os.environ["SCHEDULE_CRON"].strip(),
        min_confidence=min_conf,
    )
