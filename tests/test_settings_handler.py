from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User
from sqlalchemy import select

import bot.handlers.settings as settings_module
from database.models import ConversationHistory, Setting


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(settings_module, "async_session_factory", session_factory)


@pytest.fixture
def answer_mock(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(Message, "answer", mock)
    return mock


def _make_message(text: str, user_id: int = 42) -> Message:
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, is_bot=False, first_name="Test")
    return Message(message_id=1, date=0, chat=chat, from_user=user, text=text)


async def test_settings_without_args_lists_values(answer_mock) -> None:
    await settings_module.handle_settings(_make_message("/settings"))

    text = answer_mock.await_args.args[0]
    assert "memory_summarization_enabled" in text
    assert "history_keep_recent" in text
    assert "voice_response_mode" in text


async def test_settings_set_valid_value(answer_mock, session_factory) -> None:
    await settings_module.handle_settings(_make_message("/settings history_keep_recent 30"))

    assert answer_mock.await_args.args[0] == "✅ history_keep_recent = 30"
    async with session_factory() as session:
        row = (await session.execute(select(Setting).where(Setting.key == "history_keep_recent"))).scalar_one()
    assert row.value == "30"


async def test_settings_set_invalid_value_reports_error(answer_mock) -> None:
    await settings_module.handle_settings(_make_message("/settings history_keep_recent 999"))

    assert "⚠️" in answer_mock.await_args.args[0]


async def test_settings_unknown_key(answer_mock) -> None:
    await settings_module.handle_settings(_make_message("/settings something_else 1"))

    assert "неизвестная настройка" in answer_mock.await_args.args[0]


async def test_settings_reset(answer_mock, session_factory) -> None:
    async with session_factory() as session:
        session.add(Setting(key="history_keep_recent", value="50"))
        await session.commit()

    await settings_module.handle_settings(_make_message("/settings history_keep_recent reset"))

    assert "сброшена" in answer_mock.await_args.args[0]
    async with session_factory() as session:
        rows = (await session.execute(select(Setting))).scalars().all()
    assert rows == []


async def test_settings_key_only_shows_usage(answer_mock) -> None:
    await settings_module.handle_settings(_make_message("/settings history_keep_recent"))

    assert "Использование" in answer_mock.await_args.args[0]


async def test_clear_removes_only_this_chat(answer_mock, session_factory) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                ConversationHistory(chat_id=42, role="user", content="a"),
                ConversationHistory(chat_id=42, role="assistant", content="b"),
                ConversationHistory(chat_id=99, role="user", content="чужой чат"),
            ]
        )
        await session.commit()

    await settings_module.handle_clear(_make_message("/clear"))

    assert "удалено сообщений: 2" in answer_mock.await_args.args[0]
    async with session_factory() as session:
        rows = (await session.execute(select(ConversationHistory))).scalars().all()
    assert len(rows) == 1
    assert rows[0].chat_id == 99


async def test_help_lists_commands(answer_mock) -> None:
    await settings_module.handle_help(_make_message("/help"))

    text = answer_mock.await_args.args[0]
    assert "/settings" in text
    assert "/clear" in text
