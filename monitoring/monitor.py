"""Фоновый воркер мониторинга: периодическая проверка правил и отправка алертов.

Условия «в течение N минут» отслеживаются в памяти: запоминаем момент, когда условие
начала выполняться; если оно перестало выполняться — счётчик сбрасывается. Алерт уходит
один раз и не повторяется чаще cooldown'а (last_triggered_at хранится в БД).
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import MonitoringRule
from monitoring.alerts import AlertSender
from monitoring.rules import RuleCondition, describe_rule
from server.executor import CommandExecutor
from server.system import get_cpu_percent, get_disk_usage, get_ram_usage, get_top_processes

logger = logging.getLogger(__name__)


class MonitorWorker:
    def __init__(self, session_factory, alert_sender: AlertSender) -> None:
        self._session_factory = session_factory
        self._alerts = alert_sender
        self._executor = CommandExecutor(timeout=15)
        # rule_id -> момент, когда условие начало непрерывно выполняться
        self._breach_started: dict[int, datetime.datetime] = {}

    async def check_all(self) -> list[str]:
        """Проверяет все включённые правила. Возвращает список отправленных алертов (для тестов)."""
        sent_alerts: list[str] = []

        async with self._session_factory() as session:
            rules = await self._load_enabled_rules(session)
            now = datetime.datetime.now(datetime.timezone.utc)

            for rule in rules:
                try:
                    condition = RuleCondition.from_storage(rule.condition)
                    is_breached, current_text = await self._evaluate(rule.rule_type, condition)
                except Exception:
                    logger.exception("Ошибка проверки правила %s (%s)", rule.id, rule.rule_type)
                    continue

                if not is_breached:
                    self._breach_started.pop(rule.id, None)
                    continue

                if rule.id not in self._breach_started:
                    self._breach_started[rule.id] = now

                breach_duration = now - self._breach_started[rule.id]
                required = datetime.timedelta(minutes=condition.duration_minutes)
                if breach_duration < required:
                    continue

                if rule.last_triggered_at is not None:
                    last = rule.last_triggered_at.replace(tzinfo=datetime.timezone.utc)
                    if now - last < datetime.timedelta(minutes=settings.monitor_alert_cooldown_minutes):
                        continue

                alert_text = self._format_alert(rule.rule_type, condition, current_text)
                delivered = await self._alerts.send(rule.chat_id, alert_text)
                if delivered:
                    rule.last_triggered_at = now
                    sent_alerts.append(alert_text)
                    # Длительность обнуляется: следующий алерт — только после нового непрерывного нарушения.
                    self._breach_started.pop(rule.id, None)

            await session.commit()

        return sent_alerts

    async def _load_enabled_rules(self, session: AsyncSession) -> list[MonitoringRule]:
        result = await session.execute(select(MonitoringRule).where(MonitoringRule.enabled.is_(True)))
        return list(result.scalars().all())

    async def _evaluate(self, rule_type: str, condition: RuleCondition) -> tuple[bool, str]:
        """Возвращает (нарушено ли условие, текст с текущими значениями для алерта)."""
        if rule_type == "cpu_above":
            usage = await get_cpu_percent(interval=0.5)
            breached = usage > condition.threshold_percent
            top = get_top_processes(limit=3, sort_by="cpu")
            top_text = "\n".join(f"  {p.name}: {p.cpu_percent:.0f}%" for p in top)
            return breached, f"Current:\n{usage:.0f}%\n\nTop processes:\n{top_text}" if top else f"Current:\n{usage:.0f}%"

        if rule_type == "ram_above":
            ram = get_ram_usage()
            return ram.percent > condition.threshold_percent, (
                f"Current:\n{ram.percent:.0f}% ({ram.used_mb:.0f}/{ram.total_mb:.0f} MB)"
            )

        if rule_type == "disk_free_below":
            disk = get_disk_usage(condition.path)
            free_percent = 100.0 - disk.percent
            return free_percent < condition.threshold_percent, (
                f"Mount: {condition.path}\nFree: {free_percent:.1f}% ({disk.free_gb:.1f} GB)"
            )

        if rule_type == "container_not_running":
            result = await self._executor.run(
                "docker", ["inspect", "-f", "{{.State.Status}}", condition.container]
            )
            status = result.stdout.strip() or ("не найден" if result.exit_code != 0 else "unknown")
            return status != "running", f"Container: {condition.container}\nStatus: {status}"

        if rule_type == "service_failed":
            result = await self._executor.run("systemctl", ["is-active", condition.service])
            status = result.stdout.strip() or "unknown"
            return status != "active", f"Service: {condition.service}\nStatus: {status}"

        logger.warning("Неизвестный тип правила: %s", rule_type)
        return False, ""

    def _format_alert(self, rule_type: str, condition: RuleCondition, current_text: str) -> str:
        emoji = {
            "cpu_above": "🚨 SERVER ALERT",
            "ram_above": "🚨 SERVER ALERT",
            "disk_free_below": "🚨 DISK ALERT",
            "container_not_running": "🚨 DOCKER ALERT",
            "service_failed": "🚨 SERVICE ALERT",
        }.get(rule_type, "🚨 ALERT")
        return f"{emoji}\n\nПравило:\n{describe_rule(rule_type, condition)}\n\n{current_text}"
