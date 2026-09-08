import asyncio
import logging

from app.config import settings
from bot.bot import create_bot, create_dispatcher
from monitoring.scheduler import create_scheduler


async def main() -> None:
    logging.basicConfig(level=settings.log_level)
    bot = create_bot()
    dp = create_dispatcher()

    scheduler = create_scheduler(bot)
    scheduler.start()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
