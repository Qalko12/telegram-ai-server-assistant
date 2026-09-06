import asyncio
import datetime

import psutil
from pydantic import BaseModel

from ai.tools.registry import ExecutionContext, ToolSpec
from security.levels import SecurityLevel


class GetUptimeParams(BaseModel):
    pass


class GetCpuUsageParams(BaseModel):
    pass


async def handle_get_uptime(params: GetUptimeParams, ctx: ExecutionContext) -> str:
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), tz=datetime.timezone.utc)
    uptime = datetime.datetime.now(datetime.timezone.utc) - boot_time
    days, remainder = divmod(int(uptime.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f"Uptime: {days}d {hours}h {minutes}m (boot time: {boot_time.isoformat()})"


async def handle_get_cpu_usage(params: GetCpuUsageParams, ctx: ExecutionContext) -> str:
    usage = await asyncio.to_thread(psutil.cpu_percent, 1.0)
    return f"CPU usage: {usage}%"


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
