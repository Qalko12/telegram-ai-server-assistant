import logging

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    """AsyncAnthropic-клиент. Поддерживает сторонний Anthropic-совместимый эндпоинт.

    ANTHROPIC_BASE_URL читается из settings явно (а не только через переменную окружения,
    как делает SDK сам), чтобы конфигурация из .env работала одинаково при локальном
    запуске и в Docker.
    """
    global _client
    if _client is None:
        kwargs: dict[str, str] = {"api_key": settings.anthropic_api_key}
        base_url = settings.anthropic_base_url.strip().rstrip("/")
        if base_url:
            kwargs["base_url"] = base_url
            if base_url.startswith("http://"):
                logger.warning(
                    "ANTHROPIC_BASE_URL использует незащищённый HTTP (%s): API-ключ и всё "
                    "содержимое диалогов (включая логи и конфиги сервера) передаются в открытом виде.",
                    base_url,
                )
            else:
                logger.info("Claude API через нестандартный эндпоинт: %s", base_url)
        _client = AsyncAnthropic(**kwargs)
    return _client


def reset_client() -> None:
    """Сбрасывает кэш клиента (после смены настроек и в тестах)."""
    global _client
    _client = None
