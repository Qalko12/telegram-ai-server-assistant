from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import ai.memory as memory_module
from ai.memory import (
    append_message,
    build_context,
    clear_history,
    estimate_tokens,
    record_user_and_build_context,
)
from database.models import ConversationHistory, ConversationSummary


class _FakeBlock:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _FakeResponse:
    def __init__(self, content: list, stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


@pytest.fixture
def fake_client(monkeypatch):
    client = type("C", (), {})()
    client.messages = type("M", (), {})()
    client.messages.create = AsyncMock()
    monkeypatch.setattr(memory_module, "get_client", lambda: client)
    return client


async def _fill(session, chat_id: int, count: int, content_len: int = 100) -> None:
    for i in range(count):
        await append_message(session, chat_id, "user" if i % 2 == 0 else "assistant", f"msg-{i} " + "x" * content_len)


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 999) == 333


async def test_short_history_returned_as_is(session_factory) -> None:
    async with session_factory() as session:
        await append_message(session, 1, "user", "привет")
        await append_message(session, 1, "assistant", "здравствуй")
        context = await build_context(session, 1)

    assert context == [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "здравствуй"},
    ]


async def test_context_respects_history_max_messages(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(memory_module.settings, "history_max_messages", 5)
    async with session_factory() as session:
        await _fill(session, 1, 10)
        context = await build_context(session, 1)

    assert len(context) == 5
    assert context[-1]["content"].startswith("msg-9")
    assert context[0]["content"].startswith("msg-5")


async def test_over_budget_history_is_summarized(session_factory, fake_client, monkeypatch) -> None:
    monkeypatch.setattr(memory_module.settings, "context_token_budget", 200)
    monkeypatch.setattr(memory_module.settings, "history_keep_recent", 2)
    fake_client.messages.create.return_value = _FakeResponse(
        [_FakeBlock(type="text", text="- обсуждали backend\n- нашли проблему с портом")]
    )

    async with session_factory() as session:
        await _fill(session, 1, 20, content_len=300)  # ~3200 токенов — явно больше бюджета
        context = await build_context(session, 1)

    summaries = None
    async with session_factory() as session:
        summaries = (await session.execute(select(ConversationSummary))).scalars().all()

    assert len(summaries) == 1
    assert summaries[0].chat_id == 1

    # Контекст: суммаризация влита в первое из history_keep_recent свежих сообщений.
    assert len(context) == 2
    assert "Суммаризация" in context[0]["content"]
    assert "backend" in context[0]["content"]
    # msg-19 — самое свежее, msg-18 — первое сохранённое после cutoff.
    assert context[0]["content"].endswith("msg-18 " + "x" * 300)
    assert context[1]["content"].startswith("msg-19")


async def test_summary_covers_up_to_message_and_next_context_excludes_summarized(
    session_factory, fake_client, monkeypatch
) -> None:
    monkeypatch.setattr(memory_module.settings, "context_token_budget", 200)
    monkeypatch.setattr(memory_module.settings, "history_keep_recent", 2)
    fake_client.messages.create.return_value = _FakeResponse([_FakeBlock(type="text", text="- кратко о старом")])

    async with session_factory() as session:
        await _fill(session, 1, 10, content_len=300)
        await build_context(session, 1)
        summary = (await session.execute(select(ConversationSummary))).scalar_one()

        # Новое сообщение после суммаризации — попадает в контекст без повторной суммаризации.
        await append_message(session, 1, "user", "новый вопрос")
        context = await build_context(session, 1)

    assert summary.covers_up_to_message_id > 0
    assert context[-1]["content"] == "новый вопрос"
    assert "кратко о старом" in context[0]["content"]
    # Старые сообщения не вернулись в контекст.
    assert all("msg-0" not in str(message["content"]) for message in context)


async def test_previous_summary_is_folded_into_new_one(session_factory, fake_client, monkeypatch) -> None:
    monkeypatch.setattr(memory_module.settings, "context_token_budget", 200)
    monkeypatch.setattr(memory_module.settings, "history_keep_recent", 2)
    fake_client.messages.create.return_value = _FakeResponse([_FakeBlock(type="text", text="- новая суммаризация")])

    async with session_factory() as session:
        await _fill(session, 1, 10, content_len=300)
        await build_context(session, 1)  # первая суммаризация
        await _fill(session, 1, 10, content_len=300)
        await build_context(session, 1)  # вторая — должна учесть предыдущую

    summaries = None
    async with session_factory() as session:
        summaries = (
            await session.execute(
                select(ConversationSummary).order_by(ConversationSummary.covers_up_to_message_id.desc())
            )
        ).scalars().all()

    assert len(summaries) == 2
    assert summaries[0].covers_up_to_message_id > summaries[1].covers_up_to_message_id

    # Второй вызов суммаризатора получил предыдущую суммаризацию в payload.
    second_call_payload = fake_client.messages.create.await_args_list[1].kwargs["messages"][0]["content"]
    assert "Предыдущая суммаризация" in second_call_payload


async def test_summarizer_failure_degrades_to_recent_messages(session_factory, fake_client, monkeypatch) -> None:
    monkeypatch.setattr(memory_module.settings, "context_token_budget", 200)
    monkeypatch.setattr(memory_module.settings, "history_keep_recent", 2)
    fake_client.messages.create.side_effect = RuntimeError("API down")

    async with session_factory() as session:
        await _fill(session, 1, 10, content_len=300)
        context = await build_context(session, 1)

    # Диалог не рвётся: возвращены все сообщения (без суммаризации).
    assert len(context) == 10
    async with session_factory() as session:
        summaries = (await session.execute(select(ConversationSummary))).scalars().all()
    assert summaries == []


async def test_summarization_disabled_via_runtime_setting(session_factory, fake_client, monkeypatch) -> None:
    monkeypatch.setattr(memory_module.settings, "context_token_budget", 200)
    from app.runtime_settings import SettingsService

    async with session_factory() as session:
        await SettingsService(session).set("memory_summarization_enabled", "false")
        await _fill(session, 1, 10, content_len=300)
        context = await build_context(session, 1)

    fake_client.messages.create.assert_not_awaited()
    assert len(context) == 10


async def test_record_user_and_build_context_appends_before_loading(session_factory) -> None:
    async with session_factory() as session:
        await append_message(session, 1, "assistant", "ранний ответ")
        context = await record_user_and_build_context(session, 1, "новый вопрос")

    assert context[-1] == {"role": "user", "content": "новый вопрос"}
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(ConversationHistory).where(ConversationHistory.chat_id == 1)
                .order_by(ConversationHistory.id)
            )
        ).scalars().all()
    assert [row.role for row in rows] == ["assistant", "user"]


async def test_clear_history_removes_messages_and_summaries(session_factory) -> None:
    async with session_factory() as session:
        await _fill(session, 1, 4)
        await _fill(session, 2, 2)
        session.add(ConversationSummary(chat_id=1, summary_text="старое", covers_up_to_message_id=2))
        await session.commit()

        deleted = await clear_history(session, 1)
        assert deleted == 4

        left_chat1 = (
            await session.execute(select(ConversationHistory).where(ConversationHistory.chat_id == 1))
        ).scalars().all()
        left_chat2 = (
            await session.execute(select(ConversationHistory).where(ConversationHistory.chat_id == 2))
        ).scalars().all()
        summaries = (await session.execute(select(ConversationSummary))).scalars().all()

    assert left_chat1 == []
    assert len(left_chat2) == 2
    assert summaries == []


async def test_chats_are_isolated(session_factory) -> None:
    async with session_factory() as session:
        await append_message(session, 1, "user", "чат один")
        await append_message(session, 2, "user", "чат два")
        context1 = await build_context(session, 1)
        context2 = await build_context(session, 2)

    assert context1 == [{"role": "user", "content": "чат один"}]
    assert context2 == [{"role": "user", "content": "чат два"}]
