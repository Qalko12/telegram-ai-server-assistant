import asyncio
import logging

from app.config import settings
from bot.bot import create_bot, create_dispatcher


async def main() -> None:
    logging.basicConfig(level=settings.log_level)
    bot = create_bot()
    dp = create_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
