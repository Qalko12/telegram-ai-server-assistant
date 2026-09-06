from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

import ai.agent_loop as agent_loop_module
from ai.agent_loop import AgentLoop
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


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_: str, name: str, input_: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_ or {})


def _response(content: list, stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason)


@pytest.fixture
def fake_client(monkeypatch):
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))
    monkeypatch.setattr(agent_loop_module, "get_client", lambda: client)
    return client


async def test_direct_text_response_without_tool_use(fake_client) -> None:
    fake_client.messages.create.return_value = _response([_text_block("Привет!")], stop_reason="end_turn")

    loop = AgentLoop(_make_registry())
    result = await loop.run([{"role": "user", "content": "hi"}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert result == "Привет!"
    fake_client.messages.create.assert_awaited_once()


async def test_tool_use_round_trip(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    final = _response([_text_block("Сервер работает 42 дня.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry())
    result = await loop.run(
        [{"role": "user", "content": "проверь аптайм"}], ExecutionContext(telegram_user_id=1, chat_id=1)
    )

    assert result == "Сервер работает 42 дня."
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
    result = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert result == "Такого инструмента нет."
    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_block = second_call_kwargs["messages"][2]["content"][0]
    assert tool_result_block["is_error"] is True


async def test_moderate_tool_is_not_executed_without_confirmation(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    final = _response([_text_block("Нужно подтверждение.")], stop_reason="end_turn")
    fake_client.messages.create.side_effect = [tool_call, final]

    loop = AgentLoop(_make_registry(security_level=SecurityLevel.MODERATE))
    result = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert result == "Нужно подтверждение."
    second_call_kwargs = fake_client.messages.create.await_args_list[1].kwargs
    tool_result_block = second_call_kwargs["messages"][2]["content"][0]
    assert tool_result_block["is_error"] is True
    assert "confirmation" in tool_result_block["content"]


async def test_iteration_limit_is_enforced(fake_client) -> None:
    tool_call = _response([_tool_use_block("call_1", "get_uptime")], stop_reason="tool_use")
    fake_client.messages.create.return_value = tool_call

    loop = AgentLoop(_make_registry())
    result = await loop.run([{"role": "user", "content": "..."}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert "лимит итераций" in result
    assert fake_client.messages.create.await_count == 15
