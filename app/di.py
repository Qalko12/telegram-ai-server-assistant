from ai.tools.registry import ToolRegistry
from ai.tools.server_tools import GET_CPU_USAGE, GET_UPTIME


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GET_UPTIME)
    registry.register(GET_CPU_USAGE)
    return registry
