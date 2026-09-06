import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.engine import async_session_factory
from security.confirmations import ConfirmationService

logger = logging.getLogger(__name__)

CONFIRMATION_SWEEP_INTERVAL_SECONDS = 60


async def sweep_expired_confirmations() -> None:
    async with async_session_factory() as session:
        expired = await ConfirmationService(session).sweep_expired()
        if expired:
            logger.info("Expired %d pending confirmation(s)", len(expired))


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(sweep_expired_confirmations, "interval", seconds=CONFIRMATION_SWEEP_INTERVAL_SECONDS)
    return scheduler
