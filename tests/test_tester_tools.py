import pytest
from unittest.mock import AsyncMock

import ai.tools.tester_tools as tester_tools_module
from ai.tools.registry import ExecutionContext
from ai.tools.tester_tools import (
    InstallDependencyParams,
    ProjectTaskParams,
    RunProjectParams,
    fix_guard,
    handle_install_dependency,
    handle_run_build,
    handle_run_formatter,
    handle_run_linter,
    handle_run_project,
    handle_run_tests,
)
from coding.sandbox import SandboxResult
from coding.tester import detect_language


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings
    from security.ratelimit import limiter

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(workspace))
    monkeypatch.setattr(tester_tools_module, "_set_status", AsyncMock())
    fix_guard._state.clear()
    limiter._hits.clear()
    return workspace


@pytest.fixture
def project(_workspace):
    root = _workspace / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    return root


@pytest.fixture
def sandbox_mock(monkeypatch):
    mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="2 passed", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module.tester, "run_task", mock)
    return mock


def test_detect_language_python(project) -> None:
    assert detect_language(project) == "python"


def test_detect_language_node(_workspace) -> None:
    root = _workspace / "nodeproj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    assert detect_language(root) == "node"


async def test_run_tests_success_resets_guard(project, sandbox_mock) -> None:
    fix_guard.on_edit("proj")
    fix_guard.on_test_failure("proj")
    assert fix_guard.iterations("proj") == 1

    result = await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    assert "2 passed" in result
    assert fix_guard.iterations("proj") == 0


async def test_run_tests_failure_at_limit_warns(project, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 2)
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="1 failed", stderr="", timed_out=False)

    # Два цикла: правка → упавшие тесты.
    for _ in range(2):
        fix_guard.on_edit("proj")
        await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    result = await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    assert "ЛИМИТ АВТОИСПРАВЛЕНИЙ ИСЧЕРПАН" in result
    assert fix_guard.iterations("proj") == 2


async def test_run_tests_failure_near_limit_warns(project, sandbox_mock, monkeypatch) -> None:
    monkeypatch.setattr(fix_guard, "_limit", 5)
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="1 failed", stderr="", timed_out=False)

    for _ in range(4):
        fix_guard.on_edit("proj")
        await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    result = await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    assert "Приближается лимит" in result


async def test_run_tests_failure_far_from_limit_no_warning(project, sandbox_mock) -> None:
    sandbox_mock.return_value = SandboxResult(exit_code=1, stdout="1 failed", stderr="", timed_out=False)
    fix_guard.on_edit("proj")

    result = await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    assert "ЛИМИТ" not in result
    assert "Приближается" not in result


async def test_run_linter_and_formatter_and_build(project, sandbox_mock) -> None:
    for handler in (handle_run_linter, handle_run_formatter, handle_run_build):
        result = await handler(ProjectTaskParams(project="proj"), CTX)
        assert "exit_code=0" in result

    # run_task вызывается позиционно: (root, task)
    tasks = [call.args[1] for call in sandbox_mock.await_args_list]
    assert tasks == ["lint", "format", "build"]


async def test_install_dependency_python(project, monkeypatch) -> None:
    sandbox_mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="installed", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module, "run_in_sandbox", sandbox_mock)

    result = await handle_install_dependency(
        InstallDependencyParams(project="proj", package="pydantic==2.9.2"), CTX
    )

    assert "installed" in result
    call_kwargs = sandbox_mock.await_args.kwargs
    assert call_kwargs["network"] is True
    script_arg = sandbox_mock.await_args.args[1]
    assert "pip install" in script_arg
    assert "requirements.txt" in script_arg


async def test_install_dependency_node_project(_workspace, monkeypatch) -> None:
    root = _workspace / "nodeproj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")

    sandbox_mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="added 1 package", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module, "run_in_sandbox", sandbox_mock)

    result = await handle_install_dependency(
        InstallDependencyParams(project="nodeproj", package="express"), CTX
    )

    assert "added 1 package" in result
    script_arg = sandbox_mock.await_args.args[1]
    assert "npm install" in script_arg


async def test_run_project_uses_entrypoint(project, monkeypatch) -> None:
    sandbox_mock = AsyncMock(return_value=SandboxResult(exit_code=0, stdout="listening", stderr="", timed_out=False))
    monkeypatch.setattr(tester_tools_module, "run_in_sandbox", sandbox_mock)

    result = await handle_run_project(
        RunProjectParams(project="proj", entrypoint="python app/main.py"), CTX
    )

    assert "listening" in result
    assert sandbox_mock.await_args.args[1] == "python app/main.py"
    assert sandbox_mock.await_args.kwargs["network"] is True


async def test_run_project_timeout_explains(project, monkeypatch) -> None:
    sandbox_mock = AsyncMock(return_value=SandboxResult(exit_code=-1, stdout="", stderr="", timed_out=True))
    monkeypatch.setattr(tester_tools_module, "run_in_sandbox", sandbox_mock)

    result = await handle_run_project(RunProjectParams(project="proj"), CTX)

    assert "таймаут" in result.lower()
    assert "деплой" in result.lower()


async def test_missing_image_returns_instruction(project, sandbox_mock) -> None:
    from coding.sandbox import SandboxImageMissingError

    sandbox_mock.side_effect = SandboxImageMissingError("нет образа ai-sandbox-python:latest, соберите docker build")

    result = await handle_run_tests(ProjectTaskParams(project="proj"), CTX)

    assert "⚠️" in result
    assert "docker build" in result
