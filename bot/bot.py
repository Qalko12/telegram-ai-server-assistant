from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from bot.handlers import start
from bot.middlewares.auth import AuthMiddleware


def create_bot() -> Bot:
    return Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    auth_middleware = AuthMiddleware()
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    dp.include_router(start.router)

    return dp
