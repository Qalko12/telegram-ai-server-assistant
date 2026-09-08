"""Ограничитель циклов автоисправления кода (ТЗ §31).

Сценарий: write/edit → run_tests → ERROR → analyze → edit → run_tests → ...
Без ограничителя агент может зациклиться. CodeFixGuard считает именно циклы
«правка → проверка» на один проект и после MAX_CODE_FIX_ITERATIONS требует
остановиться и сообщить оператору.

Guard живёт в памяти процесса (dict по проекту) — этого достаточно: цикл
автоисправления происходит в рамках одной сессии агента.
"""

import time
from dataclasses import dataclass, field

from app.config import settings

# Состояние fix-цикла проекта сбрасывается, если правок не было дольше этого интервала.
FIX_SESSION_TTL_SECONDS = 3600


@dataclass
class FixGuardState:
    iterations: int = 0
    last_edit_at: float = field(default_factory=time.monotonic)


class FixLimitReachedError(Exception):
    def __init__(self, project: str, limit: int) -> None:
        self.project = project
        self.limit = limit
        super().__init__(
            f"Достигнут лимит автоматических исправлений для проекта {project!r} ({limit} циклов правка→проверка). "
            "Нужно сообщить оператору и остановить автофикс."
        )


class CodeFixGuard:
    def __init__(self, limit: int | None = None) -> None:
        self._limit = limit if limit is not None else settings.max_code_fix_iterations
        self._state: dict[str, FixGuardState] = {}

    @property
    def limit(self) -> int:
        return self._limit

    def on_edit(self, project: str) -> int:
        """Регистрирует правку кода. Возвращает номер итерации (1-based)."""
        now = time.monotonic()
        state = self._state.get(project)
        if state is None or now - state.last_edit_at > FIX_SESSION_TTL_SECONDS:
            state = FixGuardState(iterations=0, last_edit_at=now)
            self._state[project] = state

        state.iterations += 1
        state.last_edit_at = now
        return state.iterations

    def ensure_within_limit(self, project: str) -> None:
        """Бросает FixLimitReachedError, если лимит правок для проекта исчерпан."""
        state = self._state.get(project)
        if state is None:
            return
        now = time.monotonic()
        if now - state.last_edit_at > FIX_SESSION_TTL_SECONDS:
            # Цикл давно завершён — начинаем отсчёт заново.
            del self._state[project]
            return
        if state.iterations > self._limit:
            raise FixLimitReachedError(project, self._limit)

    def remaining(self, project: str) -> int:
        state = self._state.get(project)
        if state is None:
            return self._limit
        return max(0, self._limit - state.iterations)

    def reset(self, project: str) -> None:
        """Сбрасывает счётчик (например, после успешного прогона тестов)."""
        self._state.pop(project, None)

    def iterations(self, project: str) -> int:
        state = self._state.get(project)
        return state.iterations if state is not None else 0
