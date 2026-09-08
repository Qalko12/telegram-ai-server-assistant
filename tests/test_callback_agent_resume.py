from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User
from sqlalchemy import select

import ai.agent_loop as agent_loop_module
import bot.agent_dispatch as agent_dispatch_module
import bot.handlers.callbacks as callbacks_module
from ai.tools.registry import ExecutionContext
from app.di import agent_loop
from bot.agent_dispatch import deliver_outcome
from bot.handlers.callbacks import handle_cancel, handle_confirm
from database.models import AuditLog


class _FakeBlock:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)

    def model_dump(self) -> dict:
        return dict(self.__dict__)


class _FakeResponse:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


@pytest.fixture(autouse=True)
def _patch_session_factories(session_factory, monkeypatch):
    monkeypatch.setattr(callbacks_module, "async_session_factory", session_factory)
    monkeypatch.setattr(agent_dispatch_module, "async_session_factory", session_factory)


@pytest.fixture
def fake_client(monkeypatch):
    client = type("C", (), {})()
    client.messages = type("M", (), {})()
    client.messages.create = AsyncMock()
    monkeypatch.setattr(agent_loop_module, "get_client", lambda: client)
    return client


def _make_callback(user_id: int, data: str) -> CallbackQuery:
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    message = Message(message_id=1, date=0, chat=chat, from_user=user)
    return CallbackQuery(id="1", from_user=user, chat_instance="x", data=data, message=message)


async def test_approving_moderate_tool_resumes_and_delivers_final_answer(fake_client, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())

    tool_call = _FakeResponse(
        [_FakeBlock(type="text", text="Перезапускаю nginx."), _FakeBlock(type="tool_use", id="call_1", name="start_service", input={"service": "nginx"})],
        stop_reason="tool_use",
    )
    final = _FakeResponse([_FakeBlock(type="text", text="Готово, nginx запущен.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    ctx = ExecutionContext(telegram_user_id=42, chat_id=42)
    outcome = await agent_loop.run([{"role": "user", "content": "запусти nginx"}], ctx)

    async def _answer(text, reply_markup=None):
        _answer.last_text = text
        _answer.last_markup = reply_markup

    await deliver_outcome(outcome, chat_id=42, telegram_user_id=42, answer=_answer)

    async with session_factory() as session:
        from database.models import PendingConfirmation

        confirmation = (await session.execute(select(PendingConfirmation))).scalar_one()

    callback = _make_callback(42, f"confirm:{confirmation.action_id}")
    await handle_confirm(callback)

    callback.message.answer.assert_awaited_once_with("Готово, nginx запущен.", parse_mode=None)

    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLog))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].tool_name == "start_service"
        assert audit_rows[0].success is True


async def test_denying_moderate_tool_resumes_with_error_result(fake_client, session_factory, monkeypatch) -> None:
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())

    tool_call = _FakeResponse(
        [_FakeBlock(type="tool_use", id="call_1", name="start_service", input={"service": "nginx"})],
        stop_reason="tool_use",
    )
    final = _FakeResponse([_FakeBlock(type="text", text="Хорошо, не буду запускать.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    ctx = ExecutionContext(telegram_user_id=42, chat_id=42)
    outcome = await agent_loop.run([{"role": "user", "content": "запусти nginx"}], ctx)

    async def _answer(text, reply_markup=None):
        pass

    await deliver_outcome(outcome, chat_id=42, telegram_user_id=42, answer=_answer)

    async with session_factory() as session:
        from database.models import PendingConfirmation

        confirmation = (await session.execute(select(PendingConfirmation))).scalar_one()

    callback = _make_callback(42, f"cancel:{confirmation.action_id}")
    await handle_cancel(callback)

    callback.message.answer.assert_awaited_once_with("Хорошо, не буду запускать.", parse_mode=None)

    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLog))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].success is False
        assert audit_rows[0].error == "denied_by_user"
