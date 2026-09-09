from unittest.mock import AsyncMock

import pytest

from ai.tools.registry import ExecutionContext
from ai.tools.server_tools import ValidateConfigParams, handle_validate_config
from server.executor import CommandResult


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


async def test_validate_config_nginx_success(monkeypatch) -> None:
    mock_run = AsyncMock(return_value=CommandResult(exit_code=0, stdout="syntax is ok", stderr="", timed_out=False))
    monkeypatch.setattr("ai.tools.server_tools.CommandExecutor", lambda: type("E", (), {"run": mock_run})())

    result = await handle_validate_config(ValidateConfigParams(config_type="nginx"), CTX)

    assert "syntax is ok" in result
    mock_run.assert_awaited_once_with("nginx", ["-t"])


async def test_validate_config_nginx_failure(monkeypatch) -> None:
    mock_run = AsyncMock(return_value=CommandResult(exit_code=1, stdout="", stderr="emerg: invalid directive", timed_out=False))
    monkeypatch.setattr("ai.tools.server_tools.CommandExecutor", lambda: type("E", (), {"run": mock_run})())

    result = await handle_validate_config(ValidateConfigParams(config_type="nginx"), CTX)

    assert "invalid directive" in result


async def test_validate_config_unknown_type() -> None:
    # Pydantic не даст создать с неправильным типом, но проверим на всякий случай
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ValidateConfigParams(config_type="unknown")


async def test_validate_config_sshd(monkeypatch) -> None:
    mock_run = AsyncMock(return_value=CommandResult(exit_code=0, stdout="sshd_config OK", stderr="", timed_out=False))
    monkeypatch.setattr("ai.tools.server_tools.CommandExecutor", lambda: type("E", (), {"run": mock_run})())

    result = await handle_validate_config(ValidateConfigParams(config_type="sshd"), CTX)

    mock_run.assert_awaited_once_with("sshd", ["-t"])
    assert "OK" in result
