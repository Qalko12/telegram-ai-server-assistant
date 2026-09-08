"""Определения и валидация правил мониторинга.

Правила создаёт AI по запросу оператора («если CPU выше 90% пять минут — сообщи»)
и хранит в БД (monitoring_rules). Проверка выполняется фоновым воркером.
"""

from typing import Literal

from pydantic import BaseModel, Field

RuleType = Literal[
    "cpu_above",
    "ram_above",
    "disk_free_below",
    "container_not_running",
    "service_failed",
]

RULE_TYPES: tuple[str, ...] = (
    "cpu_above",
    "ram_above",
    "disk_free_below",
    "container_not_running",
    "service_failed",
)


class RuleCondition(BaseModel):
    """Параметры правила; набор значимых полей зависит от rule_type."""

    threshold_percent: float | None = Field(
        default=None, ge=0, le=100, description="Порог в процентах (для cpu_above/ram_above/disk_free_below)."
    )
    duration_minutes: int = Field(
        default=0, ge=0, le=1440, description="Сколько минут условие должно непрерывно выполняться до алерта."
    )
    path: str = Field(default="/", description="Точка монтирования для disk_free_below.")
    container: str | None = Field(default=None, description="Имя Docker-контейнера для container_not_running.")
    service: str | None = Field(default=None, description="Имя systemd-сервиса для service_failed.")

    def validate_for(self, rule_type: str) -> None:
        if rule_type not in RULE_TYPES:
            raise ValueError(f"Неизвестный тип правила: {rule_type!r}; доступны: {', '.join(RULE_TYPES)}")
        if rule_type in {"cpu_above", "ram_above", "disk_free_below"} and self.threshold_percent is None:
            raise ValueError(f"Для правила {rule_type} обязательно укажите threshold_percent.")
        if rule_type == "disk_free_below" and not self.path:
            raise ValueError("Для правила disk_free_below обязательно укажите path.")
        if rule_type == "container_not_running" and not self.container:
            raise ValueError("Для правила container_not_running обязательно укажите container.")
        if rule_type == "service_failed" and not self.service:
            raise ValueError("Для правила service_failed обязательно укажите service.")

    def to_storage(self) -> dict:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_storage(cls, data: dict) -> "RuleCondition":
        return cls.model_validate(data)


def describe_rule(rule_type: str, condition: RuleCondition) -> str:
    """Человекочитаемое описание правила для алертов и списков."""
    duration = f" в течение {condition.duration_minutes} мин" if condition.duration_minutes else ""
    if rule_type == "cpu_above":
        return f"CPU выше {condition.threshold_percent:g}%{duration}"
    if rule_type == "ram_above":
        return f"RAM выше {condition.threshold_percent:g}%{duration}"
    if rule_type == "disk_free_below":
        return f"Свободного места на {condition.path} меньше {condition.threshold_percent:g}%{duration}"
    if rule_type == "container_not_running":
        return f"Контейнер {condition.container} не работает{duration}"
    if rule_type == "service_failed":
        return f"Сервис {condition.service} не активен{duration}"
    return f"{rule_type}: {condition.to_storage()}"
