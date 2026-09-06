from ai.tools.registry import ToolRegistry
from ai.tools.server_tools import (
    FIND_FILE,
    FULL_SERVER_DIAGNOSTIC,
    GET_CPU_USAGE,
    GET_DISK_DETAILS,
    GET_DISK_USAGE,
    GET_NETWORK_INFO,
    GET_PROCESSES,
    GET_RAM_USAGE,
    GET_SERVICE_LOGS,
    GET_SERVICE_STATUS,
    GET_SYSTEM_INFO,
    GET_SYSTEM_LOGS,
    GET_UPTIME,
    LIST_DIRECTORY,
    READ_FILE,
    SEARCH_LOGS,
)


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    for spec in (
        GET_UPTIME,
        GET_CPU_USAGE,
        GET_SYSTEM_INFO,
        GET_RAM_USAGE,
        GET_DISK_USAGE,
        GET_DISK_DETAILS,
        GET_PROCESSES,
        GET_NETWORK_INFO,
        GET_SERVICE_STATUS,
        GET_SERVICE_LOGS,
        GET_SYSTEM_LOGS,
        SEARCH_LOGS,
        LIST_DIRECTORY,
        FIND_FILE,
        READ_FILE,
        FULL_SERVER_DIAGNOSTIC,
    ):
        registry.register(spec)

    return registry
