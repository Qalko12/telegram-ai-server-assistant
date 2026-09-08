"""AI-инструменты управления правилами мониторинга.

Оператор говорит «если CPU выше 90% пять минут — сообщи» → Claude вызывает
create_monitoring_rule. Правила хранятся в БД, проверяются фоновым воркером.
"""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from ai.tools.registry import ExecutionContext, ToolSpec
from database.engine import async_session_factory
from database.models import MonitoringRule
from monitoring.rules import RULE_TYPES, RuleCondition, RuleType, describe_rule
from security.levels import SecurityLevel


class _NoParams(BaseModel):
    pass


class CreateMonitoringRuleParams(BaseModel):
    rule_type: RuleType = Field(description="Тип условия: cpu_above, ram_above, disk_free_below, container_not_running, service_failed.")
    threshold_percent: float | None = Field(
        default=None, ge=0, le=100,
        description="Порог в процентах. Обязателен для cpu_above/ram_above; для disk_free_below — процент СВОБОДНОГО места, ниже которого тревога.",
    )
    duration_minutes: int = Field(
        default=0, ge=0, le=1440,
        description="Сколько минут условие должно непрерывно выполняться перед алертом (0 — сразу).",
    )
    path: str = Field(default="/", description="Точка монтирования для disk_free_below.")
    container: str | None = Field(default=None, description="Имя контейнера для container_not_running.")
    service: str | None = Field(default=None, description="Имя systemd-сервиса для service_failed.")


class ListMonitoringRulesParams(_NoParams):
    pass


class DeleteMonitoringRuleParams(BaseModel):
    rule_id: int = Field(description="ID правила из list_monitoring_rules.")


class SetMonitoringRuleEnabledParams(BaseModel):
    rule_id: int
    enabled: bool


async def handle_create_monitoring_rule(params: CreateMonitoringRuleParams, ctx: ExecutionContext) -> str:
    condition = RuleCondition(
        threshold_percent=params.threshold_percent,
        duration_minutes=params.duration_minutes,
        path=params.path,
        container=params.container,
        service=params.service,
    )
    try:
        condition.validate_for(params.rule_type)
    except ValueError as exc:
        return f"Ошибка в параметрах правила: {exc}"

    async with async_session_factory() as session:
        rule = MonitoringRule(
            created_by_telegram_id=ctx.telegram_user_id,
            chat_id=ctx.chat_id,
            rule_type=params.rule_type,
            condition=condition.to_storage(),
            enabled=True,
        )
        session.add(rule)
        await session.commit()
        return f"Правило #{rule.id} создано: {describe_rule(params.rule_type, condition)}"


async def handle_list_monitoring_rules(params: ListMonitoringRulesParams, ctx: ExecutionContext) -> str:
    async with async_session_factory() as session:
        result = await session.execute(select(MonitoringRule).order_by(MonitoringRule.id))
        rules = list(result.scalars().all())

    if not rules:
        return "Правил мониторинга нет."

    lines = []
    for rule in rules:
        condition = RuleCondition.from_storage(rule.condition)
        state = "вкл" if rule.enabled else "выкл"
        lines.append(f"#{rule.id} [{state}] {describe_rule(rule.rule_type, condition)}")
    return "\n".join(lines)


async def handle_delete_monitoring_rule(params: DeleteMonitoringRuleParams, ctx: ExecutionContext) -> str:
    async with async_session_factory() as session:
        rule = await session.get(MonitoringRule, params.rule_id)
        if rule is None:
            return f"Правило #{params.rule_id} не найдено."
        await session.delete(rule)
        await session.commit()
    return f"Правило #{params.rule_id} удалено."


async def handle_set_monitoring_rule_enabled(params: SetMonitoringRuleEnabledParams, ctx: ExecutionContext) -> str:
    async with async_session_factory() as session:
        rule = await session.get(MonitoringRule, params.rule_id)
        if rule is None:
            return f"Правило #{params.rule_id} не найдено."
        rule.enabled = params.enabled
        await session.commit()
    state = "включено" if params.enabled else "выключено"
    return f"Правило #{params.rule_id} {state}."


CREATE_MONITORING_RULE = ToolSpec(
    name="create_monitoring_rule",
    description=(
        "Создать правило мониторинга: алерт в Telegram при выполнении условия. "
        f"Доступные типы: {', '.join(RULE_TYPES)}. "
        "Пример: 'если CPU выше 90% пять минут — сообщи' → rule_type=cpu_above, threshold_percent=90, duration_minutes=5."
    ),
    input_model=CreateMonitoringRuleParams,
    handler=handle_create_monitoring_rule,
    security_level=SecurityLevel.MODERATE,
)

LIST_MONITORING_RULES = ToolSpec(
    name="list_monitoring_rules",
    description="Показать все правила мониторинга с их ID и статусом.",
    input_model=ListMonitoringRulesParams,
    handler=handle_list_monitoring_rules,
    security_level=SecurityLevel.SAFE,
)

DELETE_MONITORING_RULE = ToolSpec(
    name="delete_monitoring_rule",
    description="Удалить правило мониторинга по ID.",
    input_model=DeleteMonitoringRuleParams,
    handler=handle_delete_monitoring_rule,
    security_level=SecurityLevel.MODERATE,
)

SET_MONITORING_RULE_ENABLED = ToolSpec(
    name="set_monitoring_rule_enabled",
    description="Включить или выключить правило мониторинга по ID (без удаления).",
    input_model=SetMonitoringRuleEnabledParams,
    handler=handle_set_monitoring_rule_enabled,
    security_level=SecurityLevel.MODERATE,
)
