import pytest

from app.runtime_settings import RUNTIME_SETTINGS, RuntimeSettingError, SettingsService
from database.models import Setting
from sqlalchemy import select


async def test_defaults_without_db_rows(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        assert await service.get("memory_summarization_enabled") is True
        assert await service.get("history_keep_recent") == 10
        assert await service.get("voice_response_mode") == "auto"


async def test_set_and_persist(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        assert await service.set("history_keep_recent", "25") == 25
        assert await service.set("voice_response_mode", "text") == "text"
        assert await service.set("memory_summarization_enabled", "нет") is False

    async with session_factory() as session:
        rows = (await session.execute(select(Setting))).scalars().all()
        assert {row.key: row.value for row in rows} == {
            "history_keep_recent": "25",
            "voice_response_mode": "text",
            "memory_summarization_enabled": "нет",
        }

        service = SettingsService(session)
        assert await service.get("history_keep_recent") == 25


async def test_set_overwrites_existing_row(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        await service.set("history_keep_recent", "5")
        await service.set("history_keep_recent", "7")
        rows = (await session.execute(select(Setting).where(Setting.key == "history_keep_recent"))).scalars().all()

    assert len(rows) == 1
    assert rows[0].value == "7"


async def test_invalid_value_raises_and_is_not_persisted(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        with pytest.raises(RuntimeSettingError):
            await service.set("history_keep_recent", "abc")
        with pytest.raises(RuntimeSettingError):
            await service.set("history_keep_recent", "0")
        with pytest.raises(RuntimeSettingError):
            await service.set("voice_response_mode", "screaming")
        rows = (await session.execute(select(Setting))).scalars().all()

    assert rows == []


async def test_unknown_key_raises(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        with pytest.raises(RuntimeSettingError):
            await service.get("nonexistent")


async def test_reset_restores_default(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        await service.set("history_keep_recent", "40")
        assert await service.reset("history_keep_recent") == RUNTIME_SETTINGS["history_keep_recent"].default
        assert await service.get("history_keep_recent") == 10
        rows = (await session.execute(select(Setting))).scalars().all()

    assert rows == []


async def test_all_raw(session_factory) -> None:
    async with session_factory() as session:
        service = SettingsService(session)
        await service.set("voice_response_mode", "voice")
        values = await service.all_raw()

    assert set(values) == set(RUNTIME_SETTINGS)
    assert values["voice_response_mode"] == "voice"
