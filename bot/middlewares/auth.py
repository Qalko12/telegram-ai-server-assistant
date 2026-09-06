import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from app.config import settings
from database.engine import async_session_factory
from database.repository import UserRepository

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None or user.id not in settings.allowed_telegram_ids:
            logger.warning("Unauthorized access attempt from telegram_user_id=%s", user.id if user else None)
            if isinstance(event, Message):
                await event.answer("⛔ Доступ запрещён.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ запрещён.", show_alert=True)
            return None

        async with async_session_factory() as session:
            await UserRepository(session).touch(user.id, user.username)

        return await handler(event, data)
