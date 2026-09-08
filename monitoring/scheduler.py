import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from database.engine import async_session_factory
from monitoring.alerts import AlertSender
from monitoring.monitor import MonitorWorker
from security.confirmations import ConfirmationService

logger = logging.getLogger(__name__)

CONFIRMATION_SWEEP_INTERVAL_SECONDS = 60


async def sweep_expired_confirmations() -> None:
    async with async_session_factory() as session:
        expired = await ConfirmationService(session).sweep_expired()
        if expired:
            logger.info("Expired %d pending confirmation(s)", len(expired))


def create_scheduler(bot: Bot | None = None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(sweep_expired_confirmations, "interval", seconds=CONFIRMATION_SWEEP_INTERVAL_SECONDS)

    alert_sender = AlertSender(bot)
    # Воркер — один на весь процесс: состояние «условие выполняется N минут» живёт между тиками.
    monitor_worker = MonitorWorker(async_session_factory, alert_sender)
    scheduler.add_job(
        monitor_worker.check_all,
        "interval",
        seconds=settings.monitor_check_interval_seconds,
        id="monitor_check",
        max_instances=1,
        coalesce=True,
    )

    return scheduler
