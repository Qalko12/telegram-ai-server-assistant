from server.executor import CommandExecutor, CommandResult


async def get_system_logs(lines: int = 50, executor: CommandExecutor | None = None) -> CommandResult:
    executor = executor or CommandExecutor()
    return await executor.run("journalctl", ["-n", str(lines), "--no-pager"])


async def search_logs(query: str, lines: int = 100, executor: CommandExecutor | None = None) -> CommandResult:
    executor = executor or CommandExecutor()
    return await executor.run("journalctl", ["--no-pager", "-n", str(lines), "-g", query])
