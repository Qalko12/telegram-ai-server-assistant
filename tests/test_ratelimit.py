import time
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.middlewares.rate_limit import RateLimitMiddleware
from security.ratelimit import (
    RateLimit,
    RateLimitExceeded,
    SlidingWindowLimiter,
    USER_MESSAGES,
    limiter,
)


@pytest.fixture(autouse=True)
def _fresh_limiter():
    limiter._hits.clear()
    yield
    limiter._hits.clear()


async def test_limiter_allows_within_limit() -> None:
    local = SlidingWindowLimiter()
    limit = RateLimit(max_calls=3, window_seconds=60)
    for _ in range(3):
        await local.acquire("cat", 1, limit)


async def test_limiter_blocks_over_limit() -> None:
    local = SlidingWindowLimiter()
    limit = RateLimit(max_calls=2, window_seconds=60)
    await local.acquire("cat", 1, limit)
    await local.acquire("cat", 1, limit)

    with pytest.raises(RateLimitExceeded) as exc_info:
        await local.acquire("cat", 1, limit)
    assert exc_info.value.retry_after_seconds >= 1


async def test_limiter_isolated_by_key_and_category() -> None:
    local = SlidingWindowLimiter()
    limit = RateLimit(max_calls=1, window_seconds=60)
    await local.acquire("cat", 1, limit)

    # Другой пользователь и другая категория не затронуты.
    await local.acquire("cat", 2, limit)
    await local.acquire("other", 1, limit)


async def test_limiter_window_slides() -> None:
    local = SlidingWindowLimiter()
    limit = RateLimit(max_calls=1, window_seconds=0.2)
    await local.acquire("cat", 1, limit)

    with pytest.raises(RateLimitExceeded):
        await local.acquire("cat", 1, limit)

    time.sleep(0.25)
    await local.acquire("cat", 1, limit)  # окно прошло — снова можно


async def test_prune_removes_stale_buckets() -> None:
    local = SlidingWindowLimiter()
    await local.acquire("cat", 1, RateLimit(max_calls=5, window_seconds=60))
    local._hits[("cat", 1)][0] -= 7200  # устаревший бакет

    await local.prune()

    assert ("cat", 1) not in local._hits


def _make_message(user_id: int) -> Message:
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, is_bot=False, first_name="Test")
    return Message(message_id=1, date=0, chat=chat, from_user=user)


async def test_middleware_passes_within_limit() -> None:
    middleware = RateLimitMiddleware()
    message = _make_message(42)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, message, {"event_from_user": message.from_user})

    assert result == "ok"
    handler.assert_awaited_once()


async def test_middleware_blocks_flood(monkeypatch) -> None:
    answer_mock = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer_mock)

    middleware = RateLimitMiddleware()
    handler = AsyncMock()
    message = _make_message(42)

    limit = USER_MESSAGES.max_calls
    for _ in range(limit):
        await middleware(handler, message, {"event_from_user": message.from_user})
    assert handler.await_count == limit

    result = await middleware(handler, message, {"event_from_user": message.from_user})

    assert result is None
    assert handler.await_count == limit
    assert "Слишком много сообщений" in answer_mock.await_args.args[0]


async def test_middleware_blocks_callback_flood(monkeypatch) -> None:
    callback_answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", callback_answer)

    middleware = RateLimitMiddleware()
    handler = AsyncMock()
    user = User(id=77, is_bot=False, first_name="T")
    chat = Chat(id=77, type="private")
    message = Message(message_id=1, date=0, chat=chat, from_user=user)
    callback = CallbackQuery(id="c", from_user=user, chat_instance="x", data="confirm:1", message=message)

    for _ in range(USER_MESSAGES.max_calls):
        await middleware(handler, callback, {"event_from_user": user})
    result = await middleware(handler, callback, {"event_from_user": user})

    assert result is None
    assert callback_answer.await_args.kwargs.get("show_alert") is True


async def test_agent_loop_reports_rate_limit_to_claude(monkeypatch) -> None:
    """RateLimitExceeded из инструмента возвращается Claude как is_error с подсказкой."""
    import ai.agent_loop as agent_loop_module
    from ai.agent_loop import AgentFinalAnswer, AgentLoop
    from ai.tools.registry import ExecutionContext, ToolRegistry, ToolSpec
    from pydantic import BaseModel
    from security.levels import SecurityLevel

    class _P(BaseModel):
        pass

    async def _limited(params, ctx):
        raise RateLimitExceeded(42)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="busy_tool", description="t", input_model=_P, handler=_limited, security_level=SecurityLevel.SAFE)
    )

    class _FakeBlock:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

        def model_dump(self) -> dict:
            return dict(self.__dict__)

    class _FakeResponse:
        def __init__(self, content, stop_reason) -> None:
            self.content = content
            self.stop_reason = stop_reason

    tool_call = _FakeResponse([_FakeBlock(type="tool_use", id="c1", name="busy_tool", input={})], "tool_use")
    final = _FakeResponse([_FakeBlock(type="text", text="Подожди немного.")], "end_turn")

    client = type("C", (), {})()
    client.messages = type("M", (), {})()
    client.messages.create = AsyncMock(side_effect=[tool_call, final])
    monkeypatch.setattr(agent_loop_module, "get_client", lambda: client)

    loop = AgentLoop(registry)
    outcome = await loop.run([{"role": "user", "content": "x"}], ExecutionContext(telegram_user_id=1, chat_id=1))

    assert isinstance(outcome, AgentFinalAnswer)
    tool_result = client.messages.create.await_args_list[1].kwargs["messages"][2]["content"][0]
    assert tool_result["is_error"] is True
    assert "Rate limit" in tool_result["content"]
    assert "42" in tool_result["content"]
