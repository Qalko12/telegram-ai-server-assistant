import pytest

from security.validator import CommandDeniedError
from server.docker_manager import (
    InvalidContainerNameError,
    docker_exec,
    docker_logs,
    docker_ps,
    docker_restart,
    docker_start,
    docker_stop,
    validate_container_name,
)
from server.executor import CommandResult


class _FakeExecutor:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, program: str, args: list[str] | None = None, *, cwd: str | None = None) -> CommandResult:
        self.calls.append((program, args or []))
        return self.result


@pytest.mark.parametrize("name", ["backend", "my-app_1", "web.1"])
def test_valid_container_names_pass(name: str) -> None:
    assert validate_container_name(name) == name


@pytest.mark.parametrize("name", ["backend; rm -rf /", "../etc", ""])
def test_invalid_container_names_rejected(name: str) -> None:
    with pytest.raises(InvalidContainerNameError):
        validate_container_name(name)


async def test_docker_ps_calls_docker() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="backend\tUp\tnginx", stderr="", timed_out=False))
    result = await docker_ps(executor=fake)
    assert result.stdout == "backend\tUp\tnginx"
    assert fake.calls[0][0] == "docker"
    assert fake.calls[0][1][0] == "ps"


async def test_docker_logs_uses_container_and_lines() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="log", stderr="", timed_out=False))
    await docker_logs("backend", lines=20, executor=fake)
    assert fake.calls == [("docker", ["logs", "--tail", "20", "backend"])]


async def test_docker_start_stop_restart_validate_name() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="", stderr="", timed_out=False))
    with pytest.raises(InvalidContainerNameError):
        await docker_start("bad; name", executor=fake)
    with pytest.raises(InvalidContainerNameError):
        await docker_stop("bad; name", executor=fake)
    with pytest.raises(InvalidContainerNameError):
        await docker_restart("bad; name", executor=fake)
    assert fake.calls == []


async def test_docker_exec_applies_deny_list() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="", stderr="", timed_out=False))
    with pytest.raises(CommandDeniedError):
        await docker_exec("backend", ["rm", "-rf", "/"], executor=fake)
    assert fake.calls == []


async def test_docker_exec_runs_safe_command() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="total 0", stderr="", timed_out=False))
    result = await docker_exec("backend", ["ls", "-la"], executor=fake)
    assert result.stdout == "total 0"
    assert fake.calls == [("docker", ["exec", "backend", "ls", "-la"])]
