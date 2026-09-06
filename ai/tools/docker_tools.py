from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from security.levels import SecurityLevel
from server.docker_manager import (
    docker_exec,
    docker_inspect,
    docker_logs,
    docker_ps,
    docker_restart,
    docker_start,
    docker_stats,
    docker_stop,
)
from server.executor import CommandResult


def _format(result: CommandResult) -> str:
    output = result.stdout.strip() or result.stderr.strip()
    if result.timed_out:
        return f"Команда не завершилась за отведённое время.\n{output}"
    if not output:
        return f"(пустой вывод, exit_code={result.exit_code})"
    return output


class DockerPsParams(BaseModel):
    pass


class DockerStatsParams(BaseModel):
    pass


class DockerLogsParams(BaseModel):
    container: str
    lines: int = Field(default=100, ge=1, le=1000)


class DockerInspectParams(BaseModel):
    container: str


class DockerContainerParams(BaseModel):
    container: str


class DockerExecParams(BaseModel):
    container: str
    command: list[str] = Field(description="Команда в виде списка аргументов, например ['ls', '-la'].")


async def handle_docker_ps(params: DockerPsParams, ctx: ExecutionContext) -> str:
    return _format(await docker_ps())


async def handle_docker_stats(params: DockerStatsParams, ctx: ExecutionContext) -> str:
    return _format(await docker_stats())


async def handle_docker_logs(params: DockerLogsParams, ctx: ExecutionContext) -> str:
    return _format(await docker_logs(params.container, params.lines))


async def handle_docker_inspect(params: DockerInspectParams, ctx: ExecutionContext) -> str:
    return _format(await docker_inspect(params.container))


async def handle_docker_start(params: DockerContainerParams, ctx: ExecutionContext) -> str:
    return _format(await docker_start(params.container))


async def handle_docker_stop(params: DockerContainerParams, ctx: ExecutionContext) -> str:
    return _format(await docker_stop(params.container))


async def handle_docker_restart(params: DockerContainerParams, ctx: ExecutionContext) -> str:
    return _format(await docker_restart(params.container))


async def handle_docker_exec(params: DockerExecParams, ctx: ExecutionContext) -> str:
    return _format(await docker_exec(params.container, params.command))


DOCKER_PS = ToolSpec(
    name="docker_ps",
    description="Показать список Docker-контейнеров и их статус.",
    input_model=DockerPsParams,
    handler=handle_docker_ps,
    security_level=SecurityLevel.SAFE,
)

DOCKER_STATS = ToolSpec(
    name="docker_stats",
    description="Показать использование CPU/RAM контейнерами.",
    input_model=DockerStatsParams,
    handler=handle_docker_stats,
    security_level=SecurityLevel.SAFE,
)

DOCKER_LOGS = ToolSpec(
    name="docker_logs",
    description="Показать последние логи контейнера.",
    input_model=DockerLogsParams,
    handler=handle_docker_logs,
    security_level=SecurityLevel.SAFE,
)

DOCKER_INSPECT = ToolSpec(
    name="docker_inspect",
    description="Показать подробную конфигурацию контейнера.",
    input_model=DockerInspectParams,
    handler=handle_docker_inspect,
    security_level=SecurityLevel.SAFE,
)

DOCKER_START = ToolSpec(
    name="docker_start",
    description="Запустить остановленный Docker-контейнер.",
    input_model=DockerContainerParams,
    handler=handle_docker_start,
    security_level=SecurityLevel.MODERATE,
)

DOCKER_STOP = ToolSpec(
    name="docker_stop",
    description="Остановить Docker-контейнер.",
    input_model=DockerContainerParams,
    handler=handle_docker_stop,
    security_level=SecurityLevel.MODERATE,
)

DOCKER_RESTART = ToolSpec(
    name="docker_restart",
    description="Перезапустить Docker-контейнер.",
    input_model=DockerContainerParams,
    handler=handle_docker_restart,
    security_level=SecurityLevel.MODERATE,
)

DOCKER_EXEC = ToolSpec(
    name="docker_exec",
    description="Выполнить произвольную команду внутри контейнера. Требует явного подтверждения.",
    input_model=DockerExecParams,
    handler=handle_docker_exec,
    security_level=SecurityLevel.CRITICAL,
)
