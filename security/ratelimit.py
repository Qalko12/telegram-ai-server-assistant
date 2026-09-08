"""Rate limits (ТЗ §41): скользящее окно на сообщения пользователей и на тяжёлые
действия (прогоны агента, команды, sandbox, web search).

Реализация in-memory: бот — один процесс на один VPS, распределённые лимиты не нужны.
Вся структура защищена asyncio.Lock — конкурентные запросы не проскакивают окно.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimit:
    max_calls: int
    window_seconds: float


# Пресеты: что и от чего защищаем.
USER_MESSAGES = RateLimit(max_calls=20, window_seconds=60)  # обычный чат
AGENT_RUNS = RateLimit(max_calls=10, window_seconds=60)  # полные прогоны агента (дорого: Claude API)
COMMANDS = RateLimit(max_calls=30, window_seconds=60)  # execute_command/execute_shell
SANDBOX_RUNS = RateLimit(max_calls=10, window_seconds=300)  # docker sandbox (тяжело для 2 ГБ VPS)
WEB_SEARCHES = RateLimit(max_calls=10, window_seconds=60)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(f"Rate limit exceeded, retry after {self.retry_after_seconds}s")


class SlidingWindowLimiter:
    """Один лимитер на все пресеты; ключ = (категория, идентификатор)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, int], deque[float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, category: str, key: int, limit: RateLimit) -> None:
        """Регистрирует обращение; бросает RateLimitExceeded, если окно переполнено."""
        now = time.monotonic()
        async with self._lock:
            bucket_key = (category, key)
            hits = self._hits.setdefault(bucket_key, deque())

            cutoff = now - limit.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit.max_calls:
                oldest = hits[0]
                retry_after = limit.window_seconds - (now - oldest)
                raise RateLimitExceeded(retry_after)

            hits.append(now)

    async def prune(self) -> None:
        """Удаляет устаревшие бакеты (вызывается из планировщика)."""
        now = time.monotonic()
        async with self._lock:
            stale = [
                key
                for key, hits in self._hits.items()
                if not hits or hits[-1] < now - 3600
            ]
            for key in stale:
                del self._hits[key]


# Общий лимитер процесса.
limiter = SlidingWindowLimiter()
