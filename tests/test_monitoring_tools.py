import pytest
from sqlalchemy import select

import ai.tools.monitoring_tools as monitoring_tools_module
from ai.tools.monitoring_tools import (
    CreateMonitoringRuleParams,
    DeleteMonitoringRuleParams,
    ListMonitoringRulesParams,
    SetMonitoringRuleEnabledParams,
    handle_create_monitoring_rule,
    handle_delete_monitoring_rule,
    handle_list_monitoring_rules,
    handle_set_monitoring_rule_enabled,
)
from ai.tools.registry import ExecutionContext
from database.models import MonitoringRule


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(monitoring_tools_module, "async_session_factory", session_factory)


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


async def test_create_cpu_rule(session_factory) -> None:
    result = await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="cpu_above", threshold_percent=90, duration_minutes=5), CTX
    )

    assert "создано" in result
    assert "CPU выше 90% в течение 5 мин" in result

    async with session_factory() as session:
        rule = (await session.execute(select(MonitoringRule))).scalar_one()
    assert rule.rule_type == "cpu_above"
    assert rule.created_by_telegram_id == 42
    assert rule.enabled is True


async def test_create_container_rule(session_factory) -> None:
    result = await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="container_not_running", container="backend"), CTX
    )

    assert "backend" in result
    async with session_factory() as session:
        rule = (await session.execute(select(MonitoringRule))).scalar_one()
    assert rule.condition["container"] == "backend"


async def test_create_rule_missing_threshold_returns_error(session_factory) -> None:
    result = await handle_create_monitoring_rule(CreateMonitoringRuleParams(rule_type="cpu_above"), CTX)

    assert "Ошибка в параметрах" in result
    async with session_factory() as session:
        rules = (await session.execute(select(MonitoringRule))).scalars().all()
    assert rules == []


async def test_create_rule_missing_container_returns_error(session_factory) -> None:
    result = await handle_create_monitoring_rule(CreateMonitoringRuleParams(rule_type="container_not_running"), CTX)

    assert "container" in result


async def test_list_rules(session_factory) -> None:
    await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="cpu_above", threshold_percent=90), CTX
    )
    await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="service_failed", service="nginx"), CTX
    )

    result = await handle_list_monitoring_rules(ListMonitoringRulesParams(), CTX)

    assert "#1" in result
    assert "#2" in result
    assert "CPU выше 90%" in result
    assert "Сервис nginx" in result


async def test_list_rules_empty(session_factory) -> None:
    result = await handle_list_monitoring_rules(ListMonitoringRulesParams(), CTX)
    assert "нет" in result.lower()


async def test_delete_rule(session_factory) -> None:
    await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="cpu_above", threshold_percent=90), CTX
    )

    result = await handle_delete_monitoring_rule(DeleteMonitoringRuleParams(rule_id=1), CTX)
    assert "удалено" in result

    result = await handle_delete_monitoring_rule(DeleteMonitoringRuleParams(rule_id=99), CTX)
    assert "не найдено" in result


async def test_toggle_rule(session_factory) -> None:
    await handle_create_monitoring_rule(
        CreateMonitoringRuleParams(rule_type="cpu_above", threshold_percent=90), CTX
    )

    result = await handle_set_monitoring_rule_enabled(
        SetMonitoringRuleEnabledParams(rule_id=1, enabled=False), CTX
    )
    assert "выключено" in result

    async with session_factory() as session:
        rule = (await session.execute(select(MonitoringRule))).scalar_one()
    assert rule.enabled is False

    result = await handle_set_monitoring_rule_enabled(
        SetMonitoringRuleEnabledParams(rule_id=99, enabled=True), CTX
    )
    assert "не найдено" in result
