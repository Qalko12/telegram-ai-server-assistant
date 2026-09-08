"""Ограничитель циклов автоисправления кода (ТЗ §31, PLAN.md: «CodeFixGuard считает
именно циклы write→test»).

Цикл автофикса: правка кода → run_tests → ошибка → анализ → правка → run_tests → ...
Guard считает завершённые циклы «правка → упавшие тесты». Простые правки без прогонов
тестов счётчик не увеличивают (оператор может свободно редактировать код руками).
После MAX_CODE_FIX_ITERATIONS неудачных циклов следующие правки блокируются —
агент обязан остановиться и сообщить оператору. Успешный прогон тестов сбрасывает счёт.

Состояние живёт в памяти процесса по проектам и устаревает через TTL (защита от
вечной блокировки проекта после давно забытой серии неудач).
"""

import time
from dataclasses import dataclass, field

from app.config import settings

# Состояние fix-цикла проекта сбрасывается, если активности не было дольше этого интервала.
FIX_SESSION_TTL_SECONDS = 3600


@dataclass
class FixGuardState:
    iterations: int = 0  # завершённые циклы «правка → упавшие тесты»
    pending_edit: bool = False  # были правки после последнего прогона тестов
    last_activity: float = field(default_factory=time.monotonic)


class FixLimitReachedError(Exception):
    def __init__(self, project: str, limit: int) -> None:
        self.project = project
        self.limit = limit
        super().__init__(
            f"Достигнут лимит автоматических исправлений для проекта {project!r}: "
            f"{limit} циклов правка→упавшие тесты подряд. Автоматическое исправление остановлено. "
            "Сообщи оператору, что именно не получилось, и предложи варианты дальше."
        )


class CodeFixGuard:
    def __init__(self, limit: int | None = None) -> None:
        self._limit = limit if limit is not None else settings.max_code_fix_iterations
        self._state: dict[str, FixGuardState] = {}

    @property
    def limit(self) -> int:
        return self._limit

    def _fresh_state(self, project: str) -> FixGuardState | None:
        state = self._state.get(project)
        if state is None:
            return None
        if time.monotonic() - state.last_activity > FIX_SESSION_TTL_SECONDS:
            del self._state[project]
            return None
        return state

    def on_edit(self, project: str) -> None:
        """Регистрирует правку кода (цикл начнётся после провала тестов)."""
        state = self._fresh_state(project) or FixGuardState()
        state.pending_edit = True
        state.last_activity = time.monotonic()
        self._state[project] = state

    def on_test_failure(self, project: str) -> int:
        """Тесты упали. Если после прошлого прогона были правки — это завершённый цикл.

        Возвращает текущее число циклов.
        """
        state = self._fresh_state(project) or FixGuardState()
        if state.pending_edit:
            state.iterations += 1
            state.pending_edit = False
        state.last_activity = time.monotonic()
        self._state[project] = state
        return state.iterations

    def on_test_success(self, project: str) -> None:
        """Тесты прошли — цикл автофикса завершён успешно, счётчик обнуляется."""
        self._state.pop(project, None)

    def ensure_within_limit(self, project: str) -> None:
        """Бросает FixLimitReachedError, если лимит неудачных циклов исчерпан."""
        state = self._fresh_state(project)
        if state is not None and state.iterations >= self._limit:
            raise FixLimitReachedError(project, self._limit)

    def remaining(self, project: str) -> int:
        state = self._fresh_state(project)
        if state is None:
            return self._limit
        return max(0, self._limit - state.iterations)

    def reset(self, project: str) -> None:
        self._state.pop(project, None)

    def iterations(self, project: str) -> int:
        state = self._fresh_state(project)
        return state.iterations if state is not None else 0
