import pytest

from server.executor import CommandResult
from server.services import (
    InvalidServiceNameError,
    get_service_logs,
    get_service_status,
    restart_service,
    start_service,
    stop_service,
    validate_service_name,
)


class _FakeExecutor:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, program: str, args: list[str] | None = None, *, cwd: str | None = None) -> CommandResult:
        self.calls.append((program, args or []))
        return self.result


@pytest.mark.parametrize("name", ["nginx", "my-service", "app.service", "app@1"])
def test_valid_service_names_pass(name: str) -> None:
    assert validate_service_name(name) == name


@pytest.mark.parametrize("name", ["nginx; rm -rf /", "app && reboot", "../../etc/passwd", ""])
def test_invalid_service_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidServiceNameError):
        validate_service_name(name)


async def test_get_service_status_calls_systemctl_with_service_name() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="active", stderr="", timed_out=False))

    result = await get_service_status("nginx", executor=fake)

    assert result.stdout == "active"
    assert fake.calls == [("systemctl", ["status", "nginx", "--no-pager", "-l"])]


async def test_get_service_status_rejects_bad_name_before_calling_executor() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="", stderr="", timed_out=False))

    with pytest.raises(InvalidServiceNameError):
        await get_service_status("nginx; rm -rf /", executor=fake)

    assert fake.calls == []


async def test_get_service_logs_calls_journalctl_with_unit_and_lines() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="log line", stderr="", timed_out=False))

    result = await get_service_logs("nginx", lines=20, executor=fake)

    assert result.stdout == "log line"
    assert fake.calls == [("journalctl", ["-u", "nginx", "-n", "20", "--no-pager"])]


async def test_start_stop_restart_service_call_systemctl() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="", stderr="", timed_out=False))

    await start_service("nginx", executor=fake)
    await stop_service("nginx", executor=fake)
    await restart_service("nginx", executor=fake)

    assert fake.calls == [
        ("systemctl", ["start", "nginx"]),
        ("systemctl", ["stop", "nginx"]),
        ("systemctl", ["restart", "nginx"]),
    ]
