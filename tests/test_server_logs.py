from server.executor import CommandResult
from server.logs import get_system_logs, search_logs


class _FakeExecutor:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, program: str, args: list[str] | None = None, *, cwd: str | None = None) -> CommandResult:
        self.calls.append((program, args or []))
        return self.result


async def test_get_system_logs_calls_journalctl_with_lines() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="log", stderr="", timed_out=False))

    result = await get_system_logs(lines=30, executor=fake)

    assert result.stdout == "log"
    assert fake.calls == [("journalctl", ["-n", "30", "--no-pager"])]


async def test_search_logs_passes_grep_query() -> None:
    fake = _FakeExecutor(CommandResult(exit_code=0, stdout="match", stderr="", timed_out=False))

    result = await search_logs("connection refused", lines=50, executor=fake)

    assert result.stdout == "match"
    assert fake.calls == [("journalctl", ["--no-pager", "-n", "50", "-g", "connection refused"])]
