from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from sqlalchemy import select

import bot.handlers.callbacks as callbacks_module
from bot.handlers.callbacks import handle_cancel, handle_confirm, register_action_executor
from database.models import AuditLog, PendingConfirmation
from security.confirmations import ConfirmationRequest, ConfirmationService


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(callbacks_module, "async_session_factory", session_factory)


def _make_callback(user_id: int, data: str) -> CallbackQuery:
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    message = Message(message_id=1, date=0, chat=chat, from_user=user)
    return CallbackQuery(id="1", from_user=user, chat_instance="x", data=data, message=message)


async def test_confirm_runs_registered_executor_and_reports_result(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())

    async with session_factory() as session:
        confirmation = await ConfirmationService(session).create(
            ConfirmationRequest(
                telegram_user_id=42,
                chat_id=42,
                tool_name="dummy_critical",
                arguments={"target": "server"},
                reason="dummy critical action for testing",
                agent_session_snapshot={},
            )
        )

    executor = AsyncMock(return_value="✅ Готово: dummy critical action executed.")
    register_action_executor("dummy_critical", executor)

    callback = _make_callback(42, f"confirm:{confirmation.action_id}")

    await handle_confirm(callback)

    executor.assert_awaited_once_with(confirmation.action_id, {"target": "server"})
    callback.message.answer.assert_awaited_once_with("✅ Готово: dummy critical action executed.")

    async with session_factory() as session:
        refreshed = await session.get(PendingConfirmation, confirmation.action_id)
        assert refreshed.status == "APPROVED"

        audit_rows = (await session.execute(select(AuditLog))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].tool_name == "dummy_critical"
        assert audit_rows[0].success is True
        assert audit_rows[0].result == "✅ Готово: dummy critical action executed."


async def test_cancel_denies_without_running_executor(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())

    async with session_factory() as session:
        confirmation = await ConfirmationService(session).create(
            ConfirmationRequest(
                telegram_user_id=42,
                chat_id=42,
                tool_name="dummy_critical",
                arguments={},
                reason="dummy critical action for testing",
                agent_session_snapshot={},
            )
        )

    executor = AsyncMock()
    register_action_executor("dummy_critical", executor)

    callback = _make_callback(42, f"cancel:{confirmation.action_id}")

    await handle_cancel(callback)

    executor.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with("❌ Действие отменено.")

    async with session_factory() as session:
        audit_rows = (await session.execute(select(AuditLog))).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].success is False
        assert audit_rows[0].error == "denied_by_user"


async def test_wrong_user_gets_alert_and_executor_not_called(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(Message, "answer", AsyncMock())
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    answer_mock = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)

    async with session_factory() as session:
        confirmation = await ConfirmationService(session).create(
            ConfirmationRequest(
                telegram_user_id=42,
                chat_id=42,
                tool_name="dummy_critical",
                arguments={},
                reason="dummy critical action for testing",
                agent_session_snapshot={},
            )
        )

    executor = AsyncMock()
    register_action_executor("dummy_critical", executor)

    callback = _make_callback(999, f"confirm:{confirmation.action_id}")

    await handle_confirm(callback)

    executor.assert_not_awaited()
    answer_mock.assert_awaited_once_with("Это не твоё подтверждение.", show_alert=True)
