from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User

from bot.formatting import (
    ATTACH_FILE_THRESHOLD,
    SAFE_CHUNK_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    deliver_long_text,
    split_text,
)


def test_split_short_text_unchanged() -> None:
    assert split_text("короткий текст") == ["короткий текст"]


def test_split_long_text_respects_limit() -> None:
    text = "\n".join(f"строка {i}" * 10 for i in range(1000))
    chunks = split_text(text, limit=500)

    assert len(chunks) > 1
    assert all(len(chunk) <= 500 for chunk in chunks)
    # Содержание не потеряно (без учёта склеек переводов строк).
    assert sum(len(chunk) for chunk in chunks) >= len(text) - len(chunks) * 2


def test_split_without_newlines_hard_cuts() -> None:
    text = "x" * 10_000
    chunks = split_text(text, limit=1000)

    assert len(chunks) == 10
    assert all(chunk == "x" * 1000 for chunk in chunks)


def _make_message(user_id: int = 42) -> Message:
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, is_bot=False, first_name="Test")
    return Message(message_id=1, date=0, chat=chat, from_user=user)


async def test_short_text_sent_as_single_message() -> None:
    answer = AsyncMock()
    await deliver_long_text("привет", None, answer=answer)

    answer.assert_awaited_once_with("привет", parse_mode=None)


async def test_empty_text_replaced_with_placeholder() -> None:
    answer = AsyncMock()
    await deliver_long_text("", None, answer=answer)

    answer.assert_awaited_once_with("(пустой ответ)", parse_mode=None)


async def test_medium_text_split_into_chunks() -> None:
    answer = AsyncMock()
    text = "a" * (TELEGRAM_MESSAGE_LIMIT + 500)

    await deliver_long_text(text, None, answer=answer)

    assert answer.await_count == 2
    for call in answer.await_args_list:
        assert len(call.args[0]) <= SAFE_CHUNK_LIMIT


async def test_very_long_text_attached_as_file(monkeypatch) -> None:
    answer = AsyncMock()
    document_mock = AsyncMock()
    monkeypatch.setattr(Message, "answer_document", document_mock)
    message = _make_message()
    text = "b" * (ATTACH_FILE_THRESHOLD + 1000)

    await deliver_long_text(text, message, answer=answer, filename="log.txt")

    # Короткое сообщение-голова + файл.
    answer.assert_awaited_once()
    assert "вложенном файле" in answer.await_args.args[0]
    document_mock.assert_awaited_once()
    assert "Полный вывод" in document_mock.await_args.kwargs["caption"]


async def test_file_attach_failure_falls_back_to_chunks(monkeypatch) -> None:
    answer = AsyncMock()
    document_mock = AsyncMock(side_effect=RuntimeError("telegram down"))
    monkeypatch.setattr(Message, "answer_document", document_mock)
    message = _make_message()
    text = "c" * (ATTACH_FILE_THRESHOLD + 10)

    await deliver_long_text(text, message, answer=answer)

    # Голова + куски остатка; исключение не propagate'нулось.
    assert answer.await_count >= 2
    assert "вложенном файле" in answer.await_args_list[0].args[0]
    document_mock.assert_awaited_once()
