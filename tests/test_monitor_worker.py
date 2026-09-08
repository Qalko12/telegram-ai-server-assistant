import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import monitoring.monitor as monitor_module
from database.models import MonitoringRule
from monitoring.alerts import AlertSender
from monitoring.monitor import MonitorWorker
from server.executor import CommandResult
from server.system import DiskUsage, RamUsage


@pytest.fixture
def alert_sender():
    bot = type("B", (), {"send_message": AsyncMock()})()
    return AlertSender(bot)


@pytest.fixture
def worker(session_factory, alert_sender) -> MonitorWorker:
    return MonitorWorker(session_factory, alert_sender)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _add_rule(
    session_factory, rule_type: str, condition: dict, *, chat_id: int = 42, enabled: bool = True,
    last_triggered_at: datetime.datetime | None = None,
) -> int:
    async with session_factory() as session:
        rule = MonitoringRule(
            created_by_telegram_id=42,
            chat_id=chat_id,
            rule_type=rule_type,
            condition=condition,
            enabled=enabled,
            last_triggered_at=last_triggered_at,
        )
        session.add(rule)
        await session.commit()
        return rule.id


async def test_cpu_above_triggers_immediately_with_zero_duration(
    session_factory, worker, alert_sender, monkeypatch
) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=96.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 0})

    alerts = await worker.check_all()

    assert len(alerts) == 1
    assert "CPU выше 90%" in alerts[0]
    assert "96%" in alerts[0]
    alert_sender._bot.send_message.assert_awaited_once()

    rule_id = None
    async with session_factory() as session:
        rule = (await session.execute(select(MonitoringRule))).scalar_one()
        rule_id = rule.id
        assert rule.last_triggered_at is not None


async def test_cpu_below_threshold_does_not_trigger(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=10.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 0})

    alerts = await worker.check_all()

    assert alerts == []


async def test_duration_requires_sustained_breach(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=95.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    rule_id = await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 5})

    # Первый тик: нарушение началось, но 5 минут ещё не прошло.
    alerts = await worker.check_all()
    assert alerts == []
    assert rule_id in worker._breach_started

    # Имитируем, что нарушение длится уже 6 минут.
    worker._breach_started[rule_id] = _now() - datetime.timedelta(minutes=6)
    alerts = await worker.check_all()
    assert len(alerts) == 1


async def test_breach_resets_when_condition_recovers(session_factory, worker, monkeypatch) -> None:
    cpu_mock = AsyncMock()
    monkeypatch.setattr(monitor_module, "get_cpu_percent", cpu_mock)
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    rule_id = await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 5})

    cpu_mock.return_value = 95.0
    await worker.check_all()
    assert rule_id in worker._breach_started

    cpu_mock.return_value = 20.0
    alerts = await worker.check_all()
    assert alerts == []
    assert rule_id not in worker._breach_started


async def test_cooldown_prevents_repeat_alerts(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=99.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    await _add_rule(
        session_factory,
        "cpu_above",
        {"threshold_percent": 90, "duration_minutes": 0},
        last_triggered_at=_now().replace(tzinfo=None) - datetime.timedelta(minutes=5),
    )

    alerts = await worker.check_all()

    assert alerts == []


async def test_ram_above(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(
        monitor_module, "get_ram_usage", lambda: RamUsage(total_mb=2048, used_mb=1900, available_mb=148, percent=92.8)
    )
    await _add_rule(session_factory, "ram_above", {"threshold_percent": 85, "duration_minutes": 0})

    alerts = await worker.check_all()

    assert len(alerts) == 1
    assert "RAM выше 85%" in alerts[0]


async def test_disk_free_below(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(
        monitor_module, "get_disk_usage", lambda path: DiskUsage(total_gb=100, used_gb=95, free_gb=5, percent=95.0)
    )
    await _add_rule(session_factory, "disk_free_below", {"threshold_percent": 10, "duration_minutes": 0, "path": "/"})

    alerts = await worker.check_all()

    assert len(alerts) == 1
    assert "меньше 10%" in alerts[0]
    assert "5.0 GB" in alerts[0]


async def test_container_not_running(session_factory, worker, monkeypatch) -> None:
    async def fake_run(program, args, **kwargs):
        return CommandResult(exit_code=0, stdout="exited\n", stderr="", timed_out=False)

    monkeypatch.setattr(worker._executor, "run", fake_run)
    await _add_rule(session_factory, "container_not_running", {"container": "backend", "duration_minutes": 0})

    alerts = await worker.check_all()

    assert len(alerts) == 1
    assert "backend" in alerts[0]
    assert "exited" in alerts[0]


async def test_container_running_does_not_trigger(session_factory, worker, monkeypatch) -> None:
    async def fake_run(program, args, **kwargs):
        return CommandResult(exit_code=0, stdout="running\n", stderr="", timed_out=False)

    monkeypatch.setattr(worker._executor, "run", fake_run)
    await _add_rule(session_factory, "container_not_running", {"container": "backend", "duration_minutes": 0})

    alerts = await worker.check_all()

    assert alerts == []


async def test_service_failed(session_factory, worker, monkeypatch) -> None:
    async def fake_run(program, args, **kwargs):
        return CommandResult(exit_code=3, stdout="failed\n", stderr="", timed_out=False)

    monkeypatch.setattr(worker._executor, "run", fake_run)
    await _add_rule(session_factory, "service_failed", {"service": "nginx", "duration_minutes": 0})

    alerts = await worker.check_all()

    assert len(alerts) == 1
    assert "nginx" in alerts[0]


async def test_disabled_rules_are_skipped(session_factory, worker, monkeypatch) -> None:
    cpu_mock = AsyncMock(return_value=99.0)
    monkeypatch.setattr(monitor_module, "get_cpu_percent", cpu_mock)
    await _add_rule(session_factory, "cpu_above", {"threshold_percent": 10, "duration_minutes": 0}, enabled=False)

    alerts = await worker.check_all()

    assert alerts == []
    cpu_mock.assert_not_awaited()


async def test_alerts_go_to_rule_chat(session_factory, worker, alert_sender, monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=99.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 0}, chat_id=777)

    await worker.check_all()

    chat_id = alert_sender._bot.send_message.await_args.args[0]
    assert chat_id == 777


async def test_alert_sender_without_bot_logs_and_returns_false(alert_sender) -> None:
    sender = AlertSender(None)
    assert await sender.send(1, "text") is False


async def test_broken_rule_does_not_stop_others(session_factory, worker, monkeypatch) -> None:
    monkeypatch.setattr(monitor_module, "get_cpu_percent", AsyncMock(return_value=99.0))
    monkeypatch.setattr(monitor_module, "get_top_processes", lambda limit, sort_by: [])
    await _add_rule(session_factory, "cpu_above", {"duration_minutes": 0})  # без threshold — битое
    await _add_rule(session_factory, "cpu_above", {"threshold_percent": 90, "duration_minutes": 0})

    alerts = await worker.check_all()

    assert len(alerts) == 1
