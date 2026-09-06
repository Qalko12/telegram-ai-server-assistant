from server.system import (
    get_cpu_percent,
    get_disk_usage,
    get_load_average,
    get_ram_usage,
    get_system_info,
    get_top_processes,
    get_uptime_seconds,
    format_uptime,
)


async def full_server_diagnostic() -> str:
    info = get_system_info()
    cpu_percent = await get_cpu_percent()
    ram = get_ram_usage()
    disk = get_disk_usage()
    load = get_load_average()
    uptime = format_uptime(get_uptime_seconds())
    processes = get_top_processes(limit=5)

    lines = [
        "🖥 SERVER",
        "",
        f"Host: {info.hostname} ({info.os_name} {info.kernel}, {info.architecture})",
        f"CPU: {cpu_percent}%",
        f"RAM: {ram.percent}% ({ram.used_mb:.0f}/{ram.total_mb:.0f} MB)",
        f"Disk: {disk.percent}% ({disk.used_gb:.1f}/{disk.total_gb:.1f} GB)",
        f"Uptime: {uptime}",
    ]

    if load is not None:
        lines.append(f"Load: {load.load1:.2f}, {load.load5:.2f}, {load.load15:.2f}")

    lines.append("")
    lines.append("🔝 TOP PROCESSES (by CPU)")
    if processes:
        for proc in processes:
            lines.append(f"  {proc.name} (pid {proc.pid}): CPU {proc.cpu_percent:.1f}%, RAM {proc.memory_percent:.1f}%")
    else:
        lines.append("  (нет данных)")

    return "\n".join(lines)
