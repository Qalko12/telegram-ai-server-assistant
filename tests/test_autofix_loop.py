"""Фаза 9: полный цикл автоисправления — правки считают итерации, при исчерпании
лимита write/edit_code_file падают с FixLimitReachedError, успешные тесты сбрасывают счётчик.
"""

import pytest
from unittest.mock import AsyncMock

import ai.tools.code_tools as code_tools_module
import ai.tools.tester_tools as tester_tools_module
from ai.tools.code_tools import (
    CreateProjectParams,
    EditCodeFileParams,
    WriteCodeFileParams,
    handle_create_project,
    handle_edit_code_file,
    handle_write_code_file,
)
from ai.tools.registry import ExecutionContext
from ai.tools.tester_tools import ProjectTaskParams, fix_guard, handle_run_tests
from coding.fix_guard import FixLimitReachedError
from coding.sandbox import SandboxResult


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(workspace))
    monkeypatch.setattr(code_tools_module, "async_session_factory", _noop_session_factory)
    fix_guard._state.clear()
    return workspace


class _FakeSession:
    async def execute(self, *args, **kwargs):
        class _Result:
            def scalar_one_or_none(self):
                return None

        return _Result()

    async def commit(self):
        pass

    def add(self, obj):
        pass


class _FakeSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, *args):
        return False


_noop_session_factory = _FakeSessionFactory()


@pytest.fixture
def sandbox_mock(monkeypatch):
    mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="all passed", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module.tester, "run_task", mock)
    return mock


async def test_full_autofix_cycle_until_success(_workspace, sandbox_mock) -> None:
    await handle_create_project(CreateProjectParams(project="api"), CTX)

    # Итерация 1: пишем код, тесты падают.
    await handle_write_code_file(
        WriteCodeFileParams(project="api", path="app/main.py", content="print('v1')"), CTX
    )
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="FAILED", stderr="", timed_out=False)
    result = await handle_run_tests(ProjectTaskParams(project="api"), CTX)
    assert "FAILED" in result
    assert fix_guard.iterations("api") == 1

    # Итерация 2: правим — счётчик растёт.
    await handle_edit_code_file(
        EditCodeFileParams(project="api", path="app/main.py", old_string="v1", new_string="v2"), CTX
    )
    assert fix_guard.iterations("api") == 2

    # Тесты прошли — счётчик сброшен.
    sandbox_mock.return_value = SandboxResult(exit_code=0, stdout="1 passed", stderr="", timed_out=False)
    await handle_run_tests(ProjectTaskParams(project="api"), CTX)
    assert fix_guard.iterations("api") == 0


async def test_fix_limit_blocks_further_edits(_workspace, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 2)
    await handle_create_project(CreateProjectParams(project="api"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="api", path="a.py", content="1"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="api", path="b.py", content="2"), CTX)

    # Третья правка сверх лимита — блокируется.
    with pytest.raises(FixLimitReachedError):
        await handle_write_code_file(WriteCodeFileParams(project="api", path="c.py", content="3"), CTX)

    # И edit тоже блокируется.
    with pytest.raises(FixLimitReachedError):
        await handle_edit_code_file(
            EditCodeFileParams(project="api", path="a.py", old_string="1", new_string="9"), CTX
        )


async def test_successful_tests_unlock_further_fixes(_workspace, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 1)
    await handle_create_project(CreateProjectParams(project="api"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="api", path="a.py", content="1"), CTX)

    with pytest.raises(FixLimitReachedError):
        await handle_write_code_file(WriteCodeFileParams(project="api", path="b.py", content="2"), CTX)

    await handle_run_tests(ProjectTaskParams(project="api"), CTX)  # успех — сброс

    # После сброса снова можно править.
    result = await handle_write_code_file(
        WriteCodeFileParams(project="api", path="b.py", content="2"), CTX
    )
    assert "записан" in result
