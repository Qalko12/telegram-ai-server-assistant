import re

from security.validator import validate_command
from server.executor import CommandExecutor, CommandResult

_CONTAINER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class InvalidContainerNameError(Exception):
    pass


def validate_container_name(name: str) -> str:
    if not _CONTAINER_NAME_PATTERN.match(name):
        raise InvalidContainerNameError(f"Invalid container name: {name!r}")
    return name


async def docker_ps(executor: CommandExecutor | None = None) -> CommandResult:
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"])


async def docker_stats(executor: CommandExecutor | None = None) -> CommandResult:
    executor = executor or CommandExecutor()
    return await executor.run(
        "docker", ["stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"]
    )


async def docker_logs(container: str, lines: int = 100, executor: CommandExecutor | None = None) -> CommandResult:
    validate_container_name(container)
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["logs", "--tail", str(lines), container])


async def docker_inspect(container: str, executor: CommandExecutor | None = None) -> CommandResult:
    validate_container_name(container)
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["inspect", container])


async def docker_start(container: str, executor: CommandExecutor | None = None) -> CommandResult:
    validate_container_name(container)
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["start", container])


async def docker_stop(container: str, executor: CommandExecutor | None = None) -> CommandResult:
    validate_container_name(container)
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["stop", container])


async def docker_restart(container: str, executor: CommandExecutor | None = None) -> CommandResult:
    validate_container_name(container)
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["restart", container])


async def docker_exec(
    container: str, command: list[str], executor: CommandExecutor | None = None
) -> CommandResult:
    validate_container_name(container)
    if not command:
        raise ValueError("command must not be empty")
    validate_command(command[0], command[1:])
    executor = executor or CommandExecutor()
    return await executor.run("docker", ["exec", container, *command])
