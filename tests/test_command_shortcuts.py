from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User
from sqlalchemy import select

import bot.agent_dispatch as agent_dispatch_module
import bot.handlers.start as start_module
from ai.agent_loop import AgentFinalAnswer
from database.models import ConversationHistory


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(agent_dispatch_module, "async_session_factory", session_factory)


@pytest.fixture
def agent_mock(monkeypatch):
    mock = AsyncMock(return_value=AgentFinalAnswer(text="отчёт готов"))
    monkeypatch.setattr(agent_dispatch_module, "agent_loop", type("L", (), {"run": mock})())
    return mock


@pytest.fixture
def answer_mock(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(Message, "answer", mock)
    return mock


def _make_message(text: str, user_id: int = 42) -> Message:
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, is_bot=False, first_name="Test")
    message = Message(message_id=1, date=0, chat=chat, from_user=user, text=text)
    fake_bot = type("B", (), {"send_chat_action": AsyncMock()})()
    return message.as_(fake_bot)


async def test_server_command_sends_diagnostic_prompt(agent_mock, answer_mock) -> None:
    await start_module.handle_command_shortcut(_make_message("/server"))

    conversation = agent_mock.await_args.args[0]
    assert "диагностику" in conversation[-1]["content"].lower()


async def test_docker_command(agent_mock, answer_mock) -> None:
    await start_module.handle_command_shortcut(_make_message("/docker"))

    conversation = agent_mock.await_args.args[0]
    assert "Docker" in conversation[-1]["content"]


async def test_coding_command_activates_dev_mode(agent_mock, answer_mock) -> None:
    await start_module.handle_command_shortcut(_make_message("/coding"))

    conversation = agent_mock.await_args.args[0]
    assert "Code Workspace" in conversation[-1]["content"]


async def test_unknown_command_is_ignored(agent_mock, answer_mock) -> None:
    await start_module.handle_command_shortcut(_make_message("/whatever"))

    agent_mock.assert_not_awaited()


async def test_text_handler_records_and_answers(agent_mock, answer_mock, session_factory) -> None:
    await start_module.handle_text(_make_message("почему сайт не работает?"))

    answer_mock.assert_awaited()
    assert answer_mock.await_args.args[0] == "отчёт готов"

    async with session_factory() as session:
        rows = (
            await session.execute(select(ConversationHistory).order_by(ConversationHistory.id))
        ).scalars().all()

    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[0].content == "почему сайт не работает?"


async def test_status_command(agent_mock, answer_mock) -> None:
    await start_module.handle_status(_make_message("/status"))

    conversation = agent_mock.await_args.args[0]
    assert "статус сервера" in conversation[-1]["content"].lower()
