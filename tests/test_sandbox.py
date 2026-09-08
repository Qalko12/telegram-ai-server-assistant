import pytest

import coding.sandbox as sandbox_module
from app.config import settings as app_settings
from coding.sandbox import (
    SandboxImageMissingError,
    format_sandbox_result,
    run_in_sandbox,
    sandbox_image,
)
from server.executor import CommandResult


class FakeExecutor:
    """Записывает вызовы и отдаёт заготовленные результаты по имени программы."""

    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.results = results or {}

    async def run(self, program, args=None, **kwargs):
        args = args or []
        self.calls.append((program, args))
        key = f"{program} {' '.join(args[:2])}"
        for prefix, result in self.results.items():
            if key.startswith(prefix):
                return result
        return CommandResult(exit_code=0, stdout="ok", stderr="", timed_out=False)


@pytest.fixture(autouse=True)
def _patch_chown(monkeypatch):
    monkeypatch.setattr(sandbox_module, "_chown_tree_for_sandbox", lambda root: None)


def test_sandbox_image_selection() -> None:
    assert sandbox_image("python") == app_settings.sandbox_image_python
    assert sandbox_image("node") == app_settings.sandbox_image_node
    with pytest.raises(ValueError):
        sandbox_image("rust")


async def test_run_in_sandbox_builds_hardened_docker_args(tmp_path) -> None:
    executor = FakeExecutor()
    result = await run_in_sandbox(
        tmp_path, "python -m pytest", language="python", network=False, executor=executor
    )

    assert result.success
    docker_args = executor.calls[-1][1]

    assert docker_args[0] == "run"
    assert "--rm" in docker_args
    assert "--network" in docker_args
    assert docker_args[docker_args.index("--network") + 1] == "none"
    assert "--cap-drop" in docker_args
    assert docker_args[docker_args.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in docker_args
    assert docker_args[docker_args.index("--security-opt") + 1] == "no-new-privileges"
    assert "--user" in docker_args
    assert docker_args[docker_args.index("--user") + 1] == "1000:1000"
    assert app_settings.sandbox_memory_limit in docker_args
    assert str(tmp_path.resolve()) in " ".join(docker_args)
    assert docker_args[-1] == "python -m pytest"


async def test_run_in_sandbox_with_network_flag(tmp_path) -> None:
    executor = FakeExecutor()
    await run_in_sandbox(tmp_path, "pip install x", language="python", network=True, executor=executor)

    docker_args = executor.calls[-1][1]
    assert docker_args[docker_args.index("--network") + 1] == "bridge"


async def test_missing_image_raises_helpful_error(tmp_path) -> None:
    executor = FakeExecutor(
        {"docker image": CommandResult(exit_code=1, stdout="", stderr="No such image", timed_out=False)}
    )

    with pytest.raises(SandboxImageMissingError, match="docker build"):
        await run_in_sandbox(tmp_path, "echo hi", language="python", executor=executor)


async def test_timeout_forces_container_removal(tmp_path, monkeypatch) -> None:
    executor = FakeExecutor(
        {
            "docker run": CommandResult(exit_code=-1, stdout="", stderr="", timed_out=True),
        }
    )

    cleanup_executor = FakeExecutor()
    monkeypatch.setattr(sandbox_module, "CommandExecutor", lambda timeout: cleanup_executor)

    result = await run_in_sandbox(tmp_path, "sleep 999", language="python", executor=executor)

    assert result.timed_out
    assert len(cleanup_executor.calls) == 1
    program, args = cleanup_executor.calls[0]
    assert program == "docker"
    assert args[:2] == ["rm", "-f"]
    assert args[2].startswith(sandbox_module.CONTAINER_NAME_PREFIX)


def test_format_sandbox_result() -> None:
    from coding.sandbox import SandboxResult

    text = format_sandbox_result(
        SandboxResult(exit_code=1, stdout="FAILED tests/test_x.py", stderr="boom", timed_out=False),
        context="test в проекте demo",
    )
    assert "exit_code=1" in text
    assert "FAILED" in text
    assert "boom" in text

    timeout_text = format_sandbox_result(
        SandboxResult(exit_code=-1, stdout="", stderr="", timed_out=True), context="run"
    )
    assert "таймаут" in timeout_text
