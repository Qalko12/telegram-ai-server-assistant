from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _enable_sqlite_wal(dbapi_connection: Any, connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine() -> AsyncEngine:
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(settings.database_url)

    if settings.database_url.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", _enable_sqlite_wal)

    return engine


engine = create_engine()
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
