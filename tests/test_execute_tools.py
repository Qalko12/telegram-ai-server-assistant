import sys

import pytest

from ai.tools.registry import ExecutionContext
from ai.tools.server_tools import ExecuteCommandParams, ExecuteShellParams, handle_execute_command, handle_execute_shell
from security.validator import CommandDeniedError

_ctx = ExecutionContext(telegram_user_id=1, chat_id=1)


async def test_execute_command_runs_and_returns_output() -> None:
    result = await handle_execute_command(
        ExecuteCommandParams(program=sys.executable, args=["-c", "print('ok')"]), _ctx
    )
    assert "ok" in result


async def test_execute_command_blocks_deny_listed_command() -> None:
    with pytest.raises(CommandDeniedError):
        await handle_execute_command(ExecuteCommandParams(program="rm", args=["-rf", "/"]), _ctx)


async def test_execute_shell_blocks_deny_listed_pattern() -> None:
    with pytest.raises(CommandDeniedError):
        await handle_execute_shell(ExecuteShellParams(command="rm -rf / --no-preserve-root"), _ctx)
