import re

from server.executor import CommandExecutor, CommandResult

_SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]+$")


class InvalidServiceNameError(Exception):
    pass


def validate_service_name(name: str) -> str:
    if not _SERVICE_NAME_PATTERN.match(name):
        raise InvalidServiceNameError(f"Invalid service name: {name!r}")
    return name


async def get_service_status(service: str, executor: CommandExecutor | None = None) -> CommandResult:
    validate_service_name(service)
    executor = executor or CommandExecutor()
    return await executor.run("systemctl", ["status", service, "--no-pager", "-l"])


async def get_service_logs(service: str, lines: int = 50, executor: CommandExecutor | None = None) -> CommandResult:
    validate_service_name(service)
    executor = executor or CommandExecutor()
    return await executor.run("journalctl", ["-u", service, "-n", str(lines), "--no-pager"])
