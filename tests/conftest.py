import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Глобальный rate limiter не должен накапливать попадания между тестами."""
    from security.ratelimit import limiter

    limiter._hits.clear()
    yield
    limiter._hits.clear()


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    await engine.dispose()
