"""Telegram outbound messaging.

Slash-command handlers live in app.main; this module is just `send()`.
"""
from __future__ import annotations

import structlog
from telegram import Bot

log = structlog.get_logger()


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
        except Exception as e:
            log.error("telegram_send_failed", error=str(e))
            raise
