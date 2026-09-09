from unittest.mock import AsyncMock

import pytest
from aiogram.types import BufferedInputFile

from ai.tools.file_send_tools import SendFileParams, handle_send_file_to_chat
from ai.tools.registry import ExecutionContext


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings

    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(ws))
    return ws


@pytest.fixture
def project(workspace):
    root = workspace / "test-proj"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    return root


async def test_send_file_success(project) -> None:
    bot_mock = AsyncMock()
    ctx = ExecutionContext(telegram_user_id=42, chat_id=42, bot=bot_mock)

    result = await handle_send_file_to_chat(
        SendFileParams(project="test-proj", path="main.py", caption="Тестовый файл"), ctx
    )

    assert "✅ Файл отправлен" in result
    assert "main.py" in result

    # Проверяем, что bot.send_document вызван
    bot_mock.send_document.assert_awaited_once()
    call = bot_mock.send_document.await_args
    assert call.kwargs["chat_id"] == 42
    assert call.kwargs["caption"] == "Тестовый файл"
    assert isinstance(call.kwargs["document"], BufferedInputFile)


async def test_send_file_not_found(project) -> None:
    bot_mock = AsyncMock()
    ctx = ExecutionContext(telegram_user_id=42, chat_id=42, bot=bot_mock)

    result = await handle_send_file_to_chat(
        SendFileParams(project="test-proj", path="missing.py"), ctx
    )

    assert "❌ Файл не найден" in result
    bot_mock.send_document.assert_not_awaited()


async def test_send_file_no_bot(project) -> None:
    ctx = ExecutionContext(telegram_user_id=42, chat_id=42, bot=None)

    result = await handle_send_file_to_chat(
        SendFileParams(project="test-proj", path="main.py"), ctx
    )

    assert "⚠️ Ошибка: нет доступа к bot" in result


async def test_send_file_directory_rejected(project) -> None:
    (project / "subdir").mkdir()
    bot_mock = AsyncMock()
    ctx = ExecutionContext(telegram_user_id=42, chat_id=42, bot=bot_mock)

    result = await handle_send_file_to_chat(
        SendFileParams(project="test-proj", path="subdir"), ctx
    )

    assert "❌ Это директория" in result


async def test_send_file_in_registry() -> None:
    from app.di import build_tool_registry

    registry = build_tool_registry()
    tool_names = [t["name"] for t in registry.to_anthropic_tools()]
    assert "send_file_to_chat" in tool_names
