"""Настройки, изменяемые оператором через Telegram (/settings) во время работы бота.

Хранятся в таблице `settings` (ключ → строковое значение). Значение из БД имеет
приоритет над значением из .env; при отсутствии записи используется дефолт из конфига.
Каждый ключ имеет валидатор — невалидное значение отклоняется до записи в БД.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import Setting


class RuntimeSettingError(Exception):
    pass


def _validate_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "on", "yes", "да"}:
        return True
    if normalized in {"false", "0", "off", "no", "нет"}:
        return False
    raise RuntimeSettingError(f"ожидалось true/false, получено {raw!r}")


def _validate_keep_recent(raw: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError:
        raise RuntimeSettingError(f"ожидалось целое число, получено {raw!r}") from None
    if not 1 <= value <= 100:
        raise RuntimeSettingError("допустимый диапазон: 1..100")
    return value


def _validate_voice_mode(raw: str) -> Literal["text", "voice", "auto"]:
    normalized = raw.strip().lower()
    if normalized not in {"text", "voice", "auto"}:
        raise RuntimeSettingError(f"допустимые значения: text, voice, auto; получено {raw!r}")
    return normalized  # type: ignore[return-value]


@dataclass(frozen=True)
class RuntimeSetting:
    key: str
    description: str
    validate: Callable[[str], Any]
    # Дефолт читается лениво из .env-конфига, чтобы переопределение settings
    # (например, в тестах) влияло и на значения по умолчанию.
    default_factory: Callable[[], str]

    @property
    def default(self) -> str:
        return self.default_factory()


RUNTIME_SETTINGS: dict[str, RuntimeSetting] = {
    spec.key: spec
    for spec in (
        RuntimeSetting(
            key="memory_summarization_enabled",
            description="суммаризация длинной истории диалога",
            validate=_validate_bool,
            default_factory=lambda: "true",
        ),
        RuntimeSetting(
            key="history_keep_recent",
            description="сколько последних сообщений оставлять без суммаризации",
            validate=_validate_keep_recent,
            default_factory=lambda: str(settings.history_keep_recent),
        ),
        RuntimeSetting(
            key="voice_response_mode",
            description="режим ответов: text, voice, auto (голос подключается отдельно)",
            validate=_validate_voice_mode,
            default_factory=lambda: settings.voice_response_mode,
        ),
    )
}


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def known_keys() -> list[str]:
        return list(RUNTIME_SETTINGS.keys())

    async def get_raw(self, key: str) -> str:
        spec = self._require_spec(key)
        row = await self._session.execute(select(Setting).where(Setting.key == key))
        setting = row.scalar_one_or_none()
        return setting.value if setting is not None else spec.default

    async def get(self, key: str) -> Any:
        spec = self._require_spec(key)
        return spec.validate(await self.get_raw(key))

    async def set(self, key: str, raw_value: str) -> Any:
        spec = self._require_spec(key)
        parsed = spec.validate(raw_value)

        row = await self._session.execute(select(Setting).where(Setting.key == key))
        setting = row.scalar_one_or_none()
        if setting is None:
            self._session.add(Setting(key=key, value=raw_value.strip()))
        else:
            setting.value = raw_value.strip()
        await self._session.commit()
        return parsed

    async def reset(self, key: str) -> str:
        spec = self._require_spec(key)
        row = await self._session.execute(select(Setting).where(Setting.key == key))
        setting = row.scalar_one_or_none()
        if setting is not None:
            await self._session.delete(setting)
            await self._session.commit()
        return spec.default

    async def all_raw(self) -> dict[str, str]:
        return {key: await self.get_raw(key) for key in RUNTIME_SETTINGS}

    @staticmethod
    def _require_spec(key: str) -> RuntimeSetting:
        spec = RUNTIME_SETTINGS.get(key.strip())
        if spec is None:
            raise RuntimeSettingError(
                f"неизвестная настройка {key!r}; доступны: {', '.join(RUNTIME_SETTINGS)}"
            )
        return spec
