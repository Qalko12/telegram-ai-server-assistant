"""Фаза 9: полный цикл автоисправления — правки + упавшие тесты считают циклы,
при исчерпании лимита правки блокируются, успешные тесты сбрасывают счётчик.
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


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings
    from security.ratelimit import limiter

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(workspace))
    monkeypatch.setattr(code_tools_module, "async_session_factory", _FakeSessionFactory())
    monkeypatch.setattr(tester_tools_module, "_set_status", AsyncMock())
    fix_guard._state.clear()
    limiter._hits.clear()
    return workspace


@pytest.fixture
def sandbox_mock(monkeypatch):
    mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="all passed", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module.tester, "run_task", mock)
    return mock


async def test_full_autofix_cycle_until_success(_workspace, sandbox_mock) -> None:
    await handle_create_project(CreateProjectParams(project="api"), CTX)

    # Итерация 1: пишем код, тесты падают → один цикл.
    await handle_write_code_file(
        WriteCodeFileParams(project="api", path="app/main.py", content="print('v1')"), CTX
    )
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="FAILED", stderr="", timed_out=False)
    result = await handle_run_tests(ProjectTaskParams(project="api"), CTX)
    assert "FAILED" in result
    assert fix_guard.iterations("api") == 1

    # Итерация 2: правим, тесты снова падают → два цикла.
    await handle_edit_code_file(
        EditCodeFileParams(project="api", path="app/main.py", old_string="v1", new_string="v2"), CTX
    )
    await handle_run_tests(ProjectTaskParams(project="api"), CTX)
    assert fix_guard.iterations("api") == 2

    # Тесты прошли — счётчик сброшен.
    sandbox_mock.return_value = SandboxResult(exit_code=0, stdout="1 passed", stderr="", timed_out=False)
    result = await handle_run_tests(ProjectTaskParams(project="api"), CTX)
    assert fix_guard.iterations("api") == 0
    assert "ЛИМИТ" not in result


async def test_failing_run_at_limit_shows_stop_message(_workspace, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 1)
    await handle_create_project(CreateProjectParams(project="api"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="api", path="a.py", content="1"), CTX)

    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="FAILED", stderr="", timed_out=False)
    result = await handle_run_tests(ProjectTaskParams(project="api"), CTX)

    assert "ЛИМИТ АВТОИСПРАВЛЕНИЙ ИСЧЕРПАН" in result


async def test_fix_limit_blocks_further_edits(_workspace, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 2)
    await handle_create_project(CreateProjectParams(project="api"), CTX)
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="FAILED", stderr="", timed_out=False)

    # Два полных цикла: правка → упавшие тесты.
    for name in ("a.py", "b.py"):
        await handle_write_code_file(WriteCodeFileParams(project="api", path=name, content="x"), CTX)
        await handle_run_tests(ProjectTaskParams(project="api"), CTX)

    assert fix_guard.iterations("api") == 2

    # Третья правка блокируется.
    with pytest.raises(FixLimitReachedError):
        await handle_write_code_file(WriteCodeFileParams(project="api", path="c.py", content="y"), CTX)
    with pytest.raises(FixLimitReachedError):
        await handle_edit_code_file(
            EditCodeFileParams(project="api", path="a.py", old_string="x", new_string="z"), CTX
        )


async def test_successful_tests_unlock_further_fixes(_workspace, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 1)
    await handle_create_project(CreateProjectParams(project="api"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="api", path="a.py", content="1"), CTX)

    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="FAILED", stderr="", timed_out=False)
    await handle_run_tests(ProjectTaskParams(project="api"), CTX)

    with pytest.raises(FixLimitReachedError):
        await handle_write_code_file(WriteCodeFileParams(project="api", path="b.py", content="2"), CTX)

    sandbox_mock.return_value = SandboxResult(exit_code=0, stdout="ok", stderr="", timed_out=False)
    await handle_run_tests(ProjectTaskParams(project="api"), CTX)  # успех — сброс

    result = await handle_write_code_file(
        WriteCodeFileParams(project="api", path="b.py", content="2"), CTX
    )
    assert "записан" in result
