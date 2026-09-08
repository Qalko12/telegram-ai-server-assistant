"""Доставка алертов мониторинга в Telegram."""

import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


class AlertSender:
    """Отправляет сообщения в чат оператора. Bot подключается при старте приложения."""

    def __init__(self, bot: Bot | None = None) -> None:
        self._bot = bot

    def attach_bot(self, bot: Bot) -> None:
        self._bot = bot

    async def send(self, chat_id: int, text: str) -> bool:
        if self._bot is None:
            logger.warning("AlertSender без bot-инстанса: алерт в chat %s не отправлен", chat_id)
            return False
        try:
            await self._bot.send_message(chat_id, text)
        except Exception:
            logger.exception("Не удалось отправить алерт в chat %s", chat_id)
            return False
        return True
