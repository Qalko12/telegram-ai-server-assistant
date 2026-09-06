from server.system import (
    format_uptime,
    get_cpu_percent,
    get_disk_details,
    get_disk_usage,
    get_load_average,
    get_network_info,
    get_ram_usage,
    get_system_info,
    get_top_processes,
    get_uptime_seconds,
)


def test_get_system_info_has_hostname() -> None:
    info = get_system_info()
    assert info.hostname
    assert info.os_name


def test_get_uptime_seconds_is_positive() -> None:
    assert get_uptime_seconds() > 0


def test_format_uptime() -> None:
    assert format_uptime(0) == "0d 0h 0m"
    assert format_uptime(90061) == "1d 1h 1m"


async def test_get_cpu_percent_returns_float() -> None:
    usage = await get_cpu_percent(interval=0.1)
    assert isinstance(usage, float)
    assert 0.0 <= usage <= 100.0


def test_get_ram_usage_percent_in_range() -> None:
    ram = get_ram_usage()
    assert 0.0 <= ram.percent <= 100.0
    assert ram.total_mb > 0


def test_get_disk_usage_percent_in_range() -> None:
    disk = get_disk_usage(".")
    assert 0.0 <= disk.percent <= 100.0


def test_get_disk_details_returns_list() -> None:
    details = get_disk_details()
    assert isinstance(details, list)


def test_get_top_processes_returns_sorted_list() -> None:
    processes = get_top_processes(limit=5)
    assert len(processes) <= 5


def test_get_network_info_returns_list() -> None:
    interfaces = get_network_info()
    assert isinstance(interfaces, list)


def test_get_load_average_none_or_valid_on_this_platform() -> None:
    load = get_load_average()
    assert load is None or load.load1 >= 0
