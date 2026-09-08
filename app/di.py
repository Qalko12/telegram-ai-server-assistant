from ai.agent_loop import AgentLoop
from ai.tools.code_tools import all_code_tools
from ai.tools.docker_tools import (
    DOCKER_EXEC,
    DOCKER_INSPECT,
    DOCKER_LOGS,
    DOCKER_PS,
    DOCKER_RESTART,
    DOCKER_START,
    DOCKER_STATS,
    DOCKER_STOP,
)
from ai.tools.monitoring_tools import (
    CREATE_MONITORING_RULE,
    DELETE_MONITORING_RULE,
    LIST_MONITORING_RULES,
    SET_MONITORING_RULE_ENABLED,
)
from ai.tools.registry import ToolRegistry
from ai.tools.server_tools import (
    CREATE_DIRECTORY,
    DELETE_FILE,
    EXECUTE_COMMAND,
    EXECUTE_SHELL,
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
    RESTART_SERVICE,
    SEARCH_LOGS,
    START_SERVICE,
    STOP_SERVICE,
    WRITE_FILE,
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
        START_SERVICE,
        STOP_SERVICE,
        RESTART_SERVICE,
        DOCKER_PS,
        DOCKER_STATS,
        DOCKER_LOGS,
        DOCKER_INSPECT,
        DOCKER_START,
        DOCKER_STOP,
        DOCKER_RESTART,
        DOCKER_EXEC,
        WRITE_FILE,
        DELETE_FILE,
        CREATE_DIRECTORY,
        EXECUTE_COMMAND,
        EXECUTE_SHELL,
        LIST_MONITORING_RULES,
        CREATE_MONITORING_RULE,
        DELETE_MONITORING_RULE,
        SET_MONITORING_RULE_ENABLED,
        *all_code_tools(),
    ):
        registry.register(spec)

    return registry


agent_loop = AgentLoop(build_tool_registry())
