from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User

import bot.middlewares.auth as auth_module
from app.config import settings
from bot.middlewares.auth import AuthMiddleware


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(auth_module, "async_session_factory", session_factory)


@pytest.fixture(autouse=True)
def _patch_allowed_ids(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_ids_raw", "42")


def _make_message(user_id: int) -> Message:
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, is_bot=False, first_name="Test")
    return Message(message_id=1, date=0, chat=chat, from_user=user)


async def test_authorized_user_reaches_handler(monkeypatch):
    monkeypatch.setattr(Message, "answer", AsyncMock())
    message = _make_message(42)
    handler = AsyncMock(return_value="handled")
    middleware = AuthMiddleware()

    result = await middleware(handler, message, {"event_from_user": message.from_user})

    handler.assert_awaited_once_with(message, {"event_from_user": message.from_user})
    assert result == "handled"


async def test_unauthorized_user_is_blocked(monkeypatch):
    answer_mock = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer_mock)
    message = _make_message(999)
    handler = AsyncMock()
    middleware = AuthMiddleware()

    result = await middleware(handler, message, {"event_from_user": message.from_user})

    handler.assert_not_awaited()
    answer_mock.assert_awaited_once_with("⛔ Доступ запрещён.")
    assert result is None
