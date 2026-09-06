from ai.tools.registry import ExecutionContext
from ai.tools.server_tools import GetCpuUsageParams, GetUptimeParams, handle_get_cpu_usage, handle_get_uptime

_ctx = ExecutionContext(telegram_user_id=42, chat_id=42)


async def test_get_uptime_returns_readable_string() -> None:
    result = await handle_get_uptime(GetUptimeParams(), _ctx)
    assert result.startswith("Uptime:")


async def test_get_cpu_usage_returns_percentage() -> None:
    result = await handle_get_cpu_usage(GetCpuUsageParams(), _ctx)
    assert result.startswith("CPU usage:")
    assert result.endswith("%")
