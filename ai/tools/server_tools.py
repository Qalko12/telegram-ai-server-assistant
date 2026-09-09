from typing import Literal

from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from security.levels import SecurityLevel
from security.ratelimit import COMMANDS, limiter
from security.validator import validate_command
from server.diagnostics import full_server_diagnostic
from server.executor import CommandExecutor, CommandResult
from server.files import create_directory, delete_file, find_file, list_directory, read_file, write_file
from server.logs import get_system_logs, search_logs
from server.services import get_service_logs, get_service_status, restart_service, start_service, stop_service
from server.system import (
    format_uptime,
    get_cpu_percent,
    get_disk_details,
    get_disk_usage,
    get_network_info,
    get_ram_usage,
    get_system_info,
    get_top_processes,
    get_uptime_seconds,
)


def _format_command_result(result: CommandResult) -> str:
    output = result.stdout.strip() or result.stderr.strip()
    if result.timed_out:
        return f"Команда не завершилась за отведённое время.\n{output}"
    if not output:
        return f"(пустой вывод, exit_code={result.exit_code})"
    return output


class _NoParams(BaseModel):
    pass


class GetUptimeParams(_NoParams):
    pass


class GetCpuUsageParams(_NoParams):
    pass


class GetSystemInfoParams(_NoParams):
    pass


class GetRamUsageParams(_NoParams):
    pass


class GetDiskUsageParams(BaseModel):
    path: str = Field(default="/", description="Точка монтирования для проверки места на диске.")


class GetDiskDetailsParams(_NoParams):
    pass


class GetProcessesParams(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    sort_by: Literal["cpu", "memory"] = "cpu"


class GetNetworkInfoParams(_NoParams):
    pass


class GetServiceStatusParams(BaseModel):
    service: str = Field(description="Имя systemd-сервиса, например nginx.")


class GetServiceLogsParams(BaseModel):
    service: str
    lines: int = Field(default=50, ge=1, le=1000)


class GetSystemLogsParams(BaseModel):
    lines: int = Field(default=50, ge=1, le=1000)


class SearchLogsParams(BaseModel):
    query: str
    lines: int = Field(default=100, ge=1, le=1000)


class ListDirectoryParams(BaseModel):
    path: str


class FindFileParams(BaseModel):
    name: str = Field(description="Имя файла или glob-паттерн, например *.log")
    path: str = Field(description="Директория, в которой искать.")


class ReadFileParams(BaseModel):
    path: str


class FullServerDiagnosticParams(_NoParams):
    pass


class ServiceControlParams(BaseModel):
    service: str = Field(description="Имя systemd-сервиса, например nginx.")


class WriteFileParams(BaseModel):
    path: str
    content: str
    validate_command: list[str] | None = Field(
        default=None, description="Опциональная команда для проверки файла после записи, например ['nginx', '-t']."
    )


class DeleteFileParams(BaseModel):
    path: str


class CreateDirectoryParams(BaseModel):
    path: str


class ExecuteCommandParams(BaseModel):
    program: str = Field(description="Исполняемый файл без shell-интерпретации, например 'ls'.")
    args: list[str] = Field(default_factory=list)


class ExecuteShellParams(BaseModel):
    command: str = Field(description="Полная shell-команда (с пайпами/редиректами). Требует явного подтверждения.")


async def handle_get_uptime(params: GetUptimeParams, ctx: ExecutionContext) -> str:
    return f"Uptime: {format_uptime(get_uptime_seconds())}"


async def handle_get_cpu_usage(params: GetCpuUsageParams, ctx: ExecutionContext) -> str:
    usage = await get_cpu_percent()
    return f"CPU usage: {usage}%"


async def handle_get_system_info(params: GetSystemInfoParams, ctx: ExecutionContext) -> str:
    info = get_system_info()
    return (
        f"Host: {info.hostname}\nOS: {info.os_name} {info.os_version}\n"
        f"Kernel: {info.kernel}\nArch: {info.architecture}\nPython: {info.python_version}"
    )


async def handle_get_ram_usage(params: GetRamUsageParams, ctx: ExecutionContext) -> str:
    ram = get_ram_usage()
    return f"RAM: {ram.percent}% used ({ram.used_mb:.0f}/{ram.total_mb:.0f} MB, {ram.available_mb:.0f} MB available)"


async def handle_get_disk_usage(params: GetDiskUsageParams, ctx: ExecutionContext) -> str:
    disk = get_disk_usage(params.path)
    return f"Disk ({params.path}): {disk.percent}% used ({disk.used_gb:.1f}/{disk.total_gb:.1f} GB, {disk.free_gb:.1f} GB free)"


async def handle_get_disk_details(params: GetDiskDetailsParams, ctx: ExecutionContext) -> str:
    details = get_disk_details()
    if not details:
        return "Нет доступных дисковых разделов."
    lines = [
        f"{d.device} -> {d.mountpoint} ({d.fstype}): {d.percent}% used ({d.used_gb:.1f}/{d.total_gb:.1f} GB)"
        for d in details
    ]
    return "\n".join(lines)


async def handle_get_processes(params: GetProcessesParams, ctx: ExecutionContext) -> str:
    processes = get_top_processes(limit=params.limit, sort_by=params.sort_by)
    if not processes:
        return "Нет данных о процессах."
    lines = [f"{p.name} (pid {p.pid}): CPU {p.cpu_percent:.1f}%, RAM {p.memory_percent:.1f}%" for p in processes]
    return "\n".join(lines)


async def handle_get_network_info(params: GetNetworkInfoParams, ctx: ExecutionContext) -> str:
    interfaces = get_network_info()
    if not interfaces:
        return "Нет сетевых интерфейсов."
    lines = [f"{i.name}: {', '.join(i.addresses) if i.addresses else '(без адресов)'}" for i in interfaces]
    return "\n".join(lines)


async def handle_get_service_status(params: GetServiceStatusParams, ctx: ExecutionContext) -> str:
    result = await get_service_status(params.service)
    return _format_command_result(result)


async def handle_get_service_logs(params: GetServiceLogsParams, ctx: ExecutionContext) -> str:
    result = await get_service_logs(params.service, params.lines)
    return _format_command_result(result)


async def handle_get_system_logs(params: GetSystemLogsParams, ctx: ExecutionContext) -> str:
    result = await get_system_logs(params.lines)
    return _format_command_result(result)


async def handle_search_logs(params: SearchLogsParams, ctx: ExecutionContext) -> str:
    result = await search_logs(params.query, params.lines)
    return _format_command_result(result)


async def handle_list_directory(params: ListDirectoryParams, ctx: ExecutionContext) -> str:
    entries = list_directory(params.path)
    if not entries:
        return "(пустая директория)"
    lines = [f"{'[dir] ' if e['is_dir'] else ''}{e['name']} ({e['size']} bytes)" for e in entries]
    return "\n".join(lines)


async def handle_find_file(params: FindFileParams, ctx: ExecutionContext) -> str:
    matches = find_file(params.name, params.path)
    if not matches:
        return "Файлы не найдены."
    return "\n".join(matches)


async def handle_read_file(params: ReadFileParams, ctx: ExecutionContext) -> str:
    return read_file(params.path)


async def handle_full_server_diagnostic(params: FullServerDiagnosticParams, ctx: ExecutionContext) -> str:
    return await full_server_diagnostic()


async def handle_start_service(params: ServiceControlParams, ctx: ExecutionContext) -> str:
    return _format_command_result(await start_service(params.service))


async def handle_stop_service(params: ServiceControlParams, ctx: ExecutionContext) -> str:
    return _format_command_result(await stop_service(params.service))


async def handle_restart_service(params: ServiceControlParams, ctx: ExecutionContext) -> str:
    return _format_command_result(await restart_service(params.service))


async def handle_write_file(params: WriteFileParams, ctx: ExecutionContext) -> str:
    return await write_file(params.path, params.content, params.validate_command)


async def handle_delete_file(params: DeleteFileParams, ctx: ExecutionContext) -> str:
    return delete_file(params.path)


async def handle_create_directory(params: CreateDirectoryParams, ctx: ExecutionContext) -> str:
    return create_directory(params.path)


async def handle_execute_command(params: ExecuteCommandParams, ctx: ExecutionContext) -> str:
    validate_command(params.program, params.args)
    await limiter.acquire("commands", ctx.telegram_user_id, COMMANDS)
    result = await CommandExecutor().run(params.program, params.args)
    return _format_command_result(result)


async def handle_execute_shell(params: ExecuteShellParams, ctx: ExecutionContext) -> str:
    validate_command(params.command, [])
    await limiter.acquire("commands", ctx.telegram_user_id, COMMANDS)
    result = await CommandExecutor().run("/bin/sh", ["-c", params.command])
    return _format_command_result(result)


GET_UPTIME = ToolSpec(
    name="get_uptime",
    description="Получить время работы сервера с момента последней перезагрузки.",
    input_model=GetUptimeParams,
    handler=handle_get_uptime,
    security_level=SecurityLevel.SAFE,
)

GET_CPU_USAGE = ToolSpec(
    name="get_cpu_usage",
    description="Получить текущую загрузку CPU в процентах.",
    input_model=GetCpuUsageParams,
    handler=handle_get_cpu_usage,
    security_level=SecurityLevel.SAFE,
)

GET_SYSTEM_INFO = ToolSpec(
    name="get_system_info",
    description="Получить общую информацию о сервере: хостнейм, ОС, ядро, архитектуру.",
    input_model=GetSystemInfoParams,
    handler=handle_get_system_info,
    security_level=SecurityLevel.SAFE,
)

GET_RAM_USAGE = ToolSpec(
    name="get_ram_usage",
    description="Получить текущее использование оперативной памяти.",
    input_model=GetRamUsageParams,
    handler=handle_get_ram_usage,
    security_level=SecurityLevel.SAFE,
)

GET_DISK_USAGE = ToolSpec(
    name="get_disk_usage",
    description="Получить использование диска для указанной точки монтирования (по умолчанию корень).",
    input_model=GetDiskUsageParams,
    handler=handle_get_disk_usage,
    security_level=SecurityLevel.SAFE,
)

GET_DISK_DETAILS = ToolSpec(
    name="get_disk_details",
    description="Получить подробную информацию по всем дисковым разделам.",
    input_model=GetDiskDetailsParams,
    handler=handle_get_disk_details,
    security_level=SecurityLevel.SAFE,
)

GET_PROCESSES = ToolSpec(
    name="get_processes",
    description="Получить список процессов, отсортированных по CPU или памяти.",
    input_model=GetProcessesParams,
    handler=handle_get_processes,
    security_level=SecurityLevel.SAFE,
)

GET_NETWORK_INFO = ToolSpec(
    name="get_network_info",
    description="Получить список сетевых интерфейсов и их адресов.",
    input_model=GetNetworkInfoParams,
    handler=handle_get_network_info,
    security_level=SecurityLevel.SAFE,
)

GET_SERVICE_STATUS = ToolSpec(
    name="get_service_status",
    description="Получить статус systemd-сервиса (без изменения его состояния).",
    input_model=GetServiceStatusParams,
    handler=handle_get_service_status,
    security_level=SecurityLevel.SAFE,
)

GET_SERVICE_LOGS = ToolSpec(
    name="get_service_logs",
    description="Получить последние логи указанного systemd-сервиса из journalctl.",
    input_model=GetServiceLogsParams,
    handler=handle_get_service_logs,
    security_level=SecurityLevel.SAFE,
)

GET_SYSTEM_LOGS = ToolSpec(
    name="get_system_logs",
    description="Получить последние системные логи (journalctl).",
    input_model=GetSystemLogsParams,
    handler=handle_get_system_logs,
    security_level=SecurityLevel.SAFE,
)

SEARCH_LOGS = ToolSpec(
    name="search_logs",
    description="Найти строки в системных логах по подстроке через journalctl --grep.",
    input_model=SearchLogsParams,
    handler=handle_search_logs,
    security_level=SecurityLevel.SAFE,
)

LIST_DIRECTORY = ToolSpec(
    name="list_directory",
    description="Показать содержимое директории (только в пределах ALLOWED_PATHS).",
    input_model=ListDirectoryParams,
    handler=handle_list_directory,
    security_level=SecurityLevel.SAFE,
)

FIND_FILE = ToolSpec(
    name="find_file",
    description="Найти файлы по имени/glob-паттерну в директории (только в пределах ALLOWED_PATHS).",
    input_model=FindFileParams,
    handler=handle_find_file,
    security_level=SecurityLevel.SAFE,
)

READ_FILE = ToolSpec(
    name="read_file",
    description="Прочитать содержимое текстового файла (только в пределах ALLOWED_PATHS).",
    input_model=ReadFileParams,
    handler=handle_read_file,
    security_level=SecurityLevel.SAFE,
)

FULL_SERVER_DIAGNOSTIC = ToolSpec(
    name="full_server_diagnostic",
    description=(
        "Провести полную диагностику сервера: CPU, RAM, диск, load average, uptime, топ-процессы. "
        "Используй это, когда пользователь просит 'проверь сервер' без уточнения — не спрашивай, что именно проверить."
    ),
    input_model=FullServerDiagnosticParams,
    handler=handle_full_server_diagnostic,
    security_level=SecurityLevel.SAFE,
)

START_SERVICE = ToolSpec(
    name="start_service",
    description="Запустить systemd-сервис. Требует подтверждения.",
    input_model=ServiceControlParams,
    handler=handle_start_service,
    security_level=SecurityLevel.MODERATE,
)

STOP_SERVICE = ToolSpec(
    name="stop_service",
    description="Остановить systemd-сервис. Требует подтверждения.",
    input_model=ServiceControlParams,
    handler=handle_stop_service,
    security_level=SecurityLevel.MODERATE,
)

RESTART_SERVICE = ToolSpec(
    name="restart_service",
    description="Перезапустить systemd-сервис. Требует подтверждения.",
    input_model=ServiceControlParams,
    handler=handle_restart_service,
    security_level=SecurityLevel.MODERATE,
)

WRITE_FILE = ToolSpec(
    name="write_file",
    description=(
        "Записать содержимое в файл (в пределах ALLOWED_PATHS). Существующий файл автоматически "
        "бэкапится перед перезаписью. Можно указать validate_command (например ['nginx','-t']) — "
        "при неудачной проверке изменение автоматически откатывается."
    ),
    input_model=WriteFileParams,
    handler=handle_write_file,
    security_level=SecurityLevel.SAFE,
)

DELETE_FILE = ToolSpec(
    name="delete_file",
    description="Удалить файл (в пределах ALLOWED_PATHS). Перед удалением создаётся бэкап.",
    input_model=DeleteFileParams,
    handler=handle_delete_file,
    security_level=SecurityLevel.MODERATE,
)

CREATE_DIRECTORY = ToolSpec(
    name="create_directory",
    description="Создать директорию (в пределах ALLOWED_PATHS).",
    input_model=CreateDirectoryParams,
    handler=handle_create_directory,
    security_level=SecurityLevel.SAFE,
)

EXECUTE_COMMAND = ToolSpec(
    name="execute_command",
    description=(
        "Выполнить произвольную программу с аргументами (без shell-интерпретации). "
        "Проверяется deny-list деструктивных команд даже после подтверждения."
    ),
    input_model=ExecuteCommandParams,
    handler=handle_execute_command,
    security_level=SecurityLevel.MODERATE,
)

EXECUTE_SHELL = ToolSpec(
    name="execute_shell",
    description=(
        "Выполнить сырую shell-команду с пайпами/редиректами. Самый опасный инструмент — "
        "всегда требует явного подтверждения, плюс deny-list."
    ),
    input_model=ExecuteShellParams,
    handler=handle_execute_shell,
    security_level=SecurityLevel.CRITICAL,
)
