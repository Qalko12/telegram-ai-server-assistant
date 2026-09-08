"""Middleware общего rate limit на входящие сообщения (ТЗ §41).

Защищает от флуда и бесконечного запуска задач: не более USER_MESSAGES.max_calls
сообщений в окно на одного пользователя. Лимиты на отдельные тяжёлые действия
(agent runs, команды, sandbox) применяются внутри соответствующих модулей.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from security.ratelimit import USER_MESSAGES, RateLimitExceeded, limiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        try:
            await limiter.acquire("user_messages", user.id, USER_MESSAGES)
        except RateLimitExceeded as exc:
            logger.warning("Rate limit: user %s превысил лимит сообщений", user.id)
            text = f"⏳ Слишком много сообщений. Подожди ~{exc.retry_after_seconds} сек."
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None

        return await handler(event, data)
