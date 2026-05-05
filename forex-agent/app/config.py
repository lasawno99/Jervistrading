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
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "OANDA_API_TOKEN",
    "OANDA_ACCOUNT_ID",
    "OANDA_ENVIRONMENT",
    "TAVILY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TRADING_MODE",
    "INSTRUMENTS",
    "SCHEDULE_CRON",
    "MAX_POSITION_UNITS",
    "DAILY_LOSS_LIMIT_PCT",
)

SECRET_KEYS = {
    "ANTHROPIC_API_KEY",
    "OANDA_API_TOKEN",
    "TAVILY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
}


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-2:]}"


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
    trading_mode: str
    instruments: List[str]
    schedule_cron: str
    max_position_units: int
    daily_loss_limit_pct: float

    def safe_repr(self) -> dict:
        return {
            "anthropic_model": self.anthropic_model,
            "oanda_environment": self.oanda_environment,
            "oanda_account_id": self.oanda_account_id,
            "trading_mode": self.trading_mode,
            "instruments": self.instruments,
            "schedule_cron": self.schedule_cron,
            "max_position_units": self.max_position_units,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "anthropic_api_key": _mask(self.anthropic_api_key),
            "oanda_api_token": _mask(self.oanda_api_token),
            "tavily_api_key": _mask(self.tavily_api_key),
            "telegram_bot_token": _mask(self.telegram_bot_token),
            "telegram_chat_id": self.telegram_chat_id,
        }


def load_config() -> Config:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    trading_mode = os.environ["TRADING_MODE"].strip().lower()
    if trading_mode != "paper":
        raise RuntimeError(
            f"TRADING_MODE must be 'paper'. Got '{trading_mode}'. Live trading is not supported."
        )

    oanda_env = os.environ["OANDA_ENVIRONMENT"].strip().lower()
    if oanda_env != "practice":
        raise RuntimeError(
            f"OANDA_ENVIRONMENT must be 'practice'. Got '{oanda_env}'. Live trading is not supported."
        )

    instruments = [
        i.strip() for i in os.environ["INSTRUMENTS"].split(",") if i.strip()
    ]
    if not instruments:
        raise RuntimeError("INSTRUMENTS must contain at least one instrument")

    try:
        max_units = int(os.environ["MAX_POSITION_UNITS"])
        if max_units <= 0:
            raise ValueError
    except ValueError as e:
        raise RuntimeError("MAX_POSITION_UNITS must be a positive integer") from e

    try:
        daily_loss = float(os.environ["DAILY_LOSS_LIMIT_PCT"])
        if daily_loss <= 0:
            raise ValueError
    except ValueError as e:
        raise RuntimeError("DAILY_LOSS_LIMIT_PCT must be a positive number") from e

    # Defensively strip ALL whitespace (including embedded newlines) from
    # secrets — mobile clipboards sometimes inject \n mid-string when pasting.
    def _clean(name: str) -> str:
        return "".join(os.environ[name].split())

    return Config(
        anthropic_api_key=_clean("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ["ANTHROPIC_MODEL"].strip(),
        oanda_api_token=_clean("OANDA_API_TOKEN"),
        oanda_account_id=_clean("OANDA_ACCOUNT_ID"),
        oanda_environment=oanda_env,
        tavily_api_key=_clean("TAVILY_API_KEY"),
        telegram_bot_token=_clean("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_clean("TELEGRAM_CHAT_ID"),
        trading_mode=trading_mode,
        instruments=instruments,
        schedule_cron=os.environ["SCHEDULE_CRON"].strip(),
        max_position_units=max_units,
        daily_loss_limit_pct=daily_loss,
    )
