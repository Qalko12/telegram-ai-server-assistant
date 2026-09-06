from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

import ai.agent_loop as agent_loop_module
from ai.agent_loop import AgentConfirmationNeeded, AgentFinalAnswer, AgentLoop
from ai.tools.registry import ExecutionContext, ToolRegistry, ToolSpec
from security.levels import SecurityLevel


class _Params(BaseModel):
    pass


async def _echo_handler(params: _Params, ctx: ExecutionContext) -> str:
    return "42 days uptime"


def _make_registry(security_level: SecurityLevel = SecurityLevel.SAFE) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="get_uptime",
            description="test",
            input_model=_Params,
            handler=_echo_handler,
            security_level=security_level,
        )
    )
    return registry


class _FakeBlock:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)

    def model_dump(self) -> dict:
        return dict(self.__dict__)


def _text_block(text: str) -> _FakeBlock:
    return _FakeBlock(type="text", text=text)


def _tool_use_block(id_: str, name: str, input_: dict | None = None) -> _FakeBlock:
    return _FakeBlock(type="tool_use", id=id_, name=name, input=input_ or {})


class _FakeResponse:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


def _response(content: list, stop_reason: str) -> _FakeResponse:
    return _FakeResponse(content, stop_reason)


@pytest.fixture
def fake_client(monkeypatch):
    client = type("C", (), {})()
    client.messages = type("M", (), {})()
    client.messages.create = AsyncMock()
    monkeypatch.setattr(agent_loop_module, "get_client", lambda: client)
    return client


async def test_direct_text_response_without_tool_use(fake_client) -> None:
    fake_client.messages.create.return_value = _response([_text_block("Привет!")], stop_reason="end_turn")

    loop = AgentLoop(_make_registry())
    outcome = await loop.run([{"role": "user", "content": "hi"}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert isinstance(outcome, AgentFinalAnswer)
    assert outcome.text == "Привет!"
    fake_client.messages.create.assert_awaited_once()


async def test_tool_use_round_trip(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    final = _response([_text_block("Сервер работает 42 дня.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry())
    outcome = await loop.run(
        [{"role": "user", "content": "проверь аптайм"}], ExecutionContext(telegram_user_id=1, chat_id=1)
    )

    assert isinstance(outcome, AgentFinalAnswer)
    assert outcome.text == "Сервер работает 42 дня."
    assert fake_client.messages.create.await_count == 2

    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_message = second_call_kwargs["messages"][2]
    assert tool_result_message["role"] == "user"
    tool_result_block = tool_result_message["content"][0]
    assert tool_result_block["tool_use_id"] == "call_1"
    assert "42 days uptime" in tool_result_block["content"]
    assert "<untrusted_tool_output" in tool_result_block["content"]


async def test_unknown_tool_returns_error_and_continues(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "nonexistent_tool")], stop_reason="tool_use")
    final = _response([_text_block("Такого инструмента нет.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry())
    outcome = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert isinstance(outcome, AgentFinalAnswer)
    assert outcome.text == "Такого инструмента нет."
    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_block = second_call_kwargs["messages"][2]["content"][0]
    assert tool_result_block["is_error"] is True


async def test_moderate_tool_pauses_for_confirmation(fake_client) -> None:
    tool_call = _response(
        [_text_block("Нужно перезапустить сервис."), _tool_use_block("call_1", "get_uptime", {"x": 1})],
        stop_reason="tool_use",
    )
    fake_client.messages.create.return_value = tool_call

    loop = AgentLoop(_make_registry(security_level=SecurityLevel.MODERATE))
    outcome = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert isinstance(outcome, AgentConfirmationNeeded)
    assert outcome.tool_use_id == "call_1"
    assert outcome.tool_name == "get_uptime"
    assert outcome.arguments == {"x": 1}
    assert outcome.reason == "Нужно перезапустить сервис."
    assert outcome.pending_tool_results == []
    fake_client.messages.create.assert_awaited_once()


async def test_resume_after_approval_continues_the_conversation(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    final = _response([_text_block("Готово, сервис перезапущен.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry(security_level=SecurityLevel.MODERATE))
    pending = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))
    assert isinstance(pending, AgentConfirmationNeeded)

    outcome = await loop.resume(
        pending, "nginx restarted successfully", is_error=False, ctx=ExecutionContext(telegram_user_id=1, chat_id=1)
    )

    assert isinstance(outcome, AgentFinalAnswer)
    assert outcome.text == "Готово, сервис перезапущен."

    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_message = second_call_kwargs["messages"][2]
    tool_result_block = tool_result_message["content"][0]
    assert tool_result_block["tool_use_id"] == "call_1"
    assert tool_result_block["content"] == "nginx restarted successfully"
    assert tool_result_block["is_error"] is False


async def test_resume_after_denial_marks_tool_result_as_error(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    final = _response([_text_block("Понял, не буду перезапускать.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry(security_level=SecurityLevel.MODERATE))
    pending = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    outcome = await loop.resume(
        pending, "Пользователь отклонил это действие.", is_error=True, ctx=ExecutionContext(telegram_user_id=1, chat_id=1)
    )

    assert isinstance(outcome, AgentFinalAnswer)
    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_block = second_call_kwargs["messages"][2]["content"][0]
    assert tool_result_block["is_error"] is True


async def test_iteration_limit_is_enforced(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    fake_client.messages.create.return_value = tool_call

    loop = AgentLoop(_make_registry())
    outcome = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert isinstance(outcome, AgentFinalAnswer)
    assert "лимит итераций" in outcome.text
    assert fake_client.messages.create.await_count == 15
