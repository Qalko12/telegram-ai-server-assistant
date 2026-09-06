import asyncio
import datetime
import platform
import socket
from dataclasses import dataclass

import psutil


@dataclass
class SystemInfo:
    hostname: str
    os_name: str
    os_version: str
    kernel: str
    architecture: str
    python_version: str


def get_system_info() -> SystemInfo:
    return SystemInfo(
        hostname=socket.gethostname(),
        os_name=platform.system(),
        os_version=platform.version(),
        kernel=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
    )


def get_uptime_seconds() -> float:
    return (datetime.datetime.now(datetime.timezone.utc) - _boot_time()).total_seconds()


def _boot_time() -> datetime.datetime:
    return datetime.datetime.fromtimestamp(psutil.boot_time(), tz=datetime.timezone.utc)


def format_uptime(seconds: float) -> str:
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f"{days}d {hours}h {minutes}m"


async def get_cpu_percent(interval: float = 1.0) -> float:
    return await asyncio.to_thread(psutil.cpu_percent, interval)


@dataclass
class RamUsage:
    total_mb: float
    used_mb: float
    available_mb: float
    percent: float


def get_ram_usage() -> RamUsage:
    vm = psutil.virtual_memory()
    mb = 1024 * 1024
    return RamUsage(
        total_mb=round(vm.total / mb, 1),
        used_mb=round(vm.used / mb, 1),
        available_mb=round(vm.available / mb, 1),
        percent=vm.percent,
    )


@dataclass
class DiskUsage:
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


def get_disk_usage(path: str = "/") -> DiskUsage:
    du = psutil.disk_usage(path)
    gb = 1024**3
    return DiskUsage(
        total_gb=round(du.total / gb, 2),
        used_gb=round(du.used / gb, 2),
        free_gb=round(du.free / gb, 2),
        percent=du.percent,
    )


@dataclass
class DiskPartitionInfo:
    device: str
    mountpoint: str
    fstype: str
    total_gb: float
    used_gb: float
    percent: float


def get_disk_details() -> list[DiskPartitionInfo]:
    gb = 1024**3
    details = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        details.append(
            DiskPartitionInfo(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                total_gb=round(usage.total / gb, 2),
                used_gb=round(usage.used / gb, 2),
                percent=usage.percent,
            )
        )
    return details


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float


def get_top_processes(limit: int = 10, sort_by: str = "cpu") -> list[ProcessInfo]:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            processes.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info["name"] or "",
                    cpu_percent=info["cpu_percent"] or 0.0,
                    memory_percent=round(info["memory_percent"] or 0.0, 2),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    processes.sort(key=lambda p: getattr(p, key), reverse=True)
    return processes[:limit]


@dataclass
class NetworkInterfaceInfo:
    name: str
    addresses: list[str]


def get_network_info() -> list[NetworkInterfaceInfo]:
    result = []
    for name, addrs in psutil.net_if_addrs().items():
        addresses = [addr.address for addr in addrs if addr.family.name in ("AF_INET", "AF_INET6")]
        result.append(NetworkInterfaceInfo(name=name, addresses=addresses))
    return result


@dataclass
class LoadAverage:
    load1: float
    load5: float
    load15: float


def get_load_average() -> LoadAverage | None:
    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        return None
    return LoadAverage(load1=load1, load5=load5, load15=load15)
