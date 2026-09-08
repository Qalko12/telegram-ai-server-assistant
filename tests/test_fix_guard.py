import pytest

from coding.fix_guard import CodeFixGuard, FixLimitReachedError


def test_guard_counts_iterations_and_raises_after_limit() -> None:
    guard = CodeFixGuard(limit=3)

    assert guard.on_edit("proj") == 1
    guard.ensure_within_limit("proj")
    assert guard.on_edit("proj") == 2
    guard.ensure_within_limit("proj")
    assert guard.on_edit("proj") == 3
    guard.ensure_within_limit("proj")

    assert guard.on_edit("proj") == 4
    with pytest.raises(FixLimitReachedError) as exc_info:
        guard.ensure_within_limit("proj")
    assert "3" in str(exc_info.value)


def test_guard_is_per_project() -> None:
    guard = CodeFixGuard(limit=1)
    guard.on_edit("a")
    guard.on_edit("a")

    with pytest.raises(FixLimitReachedError):
        guard.ensure_within_limit("a")
    # Другой проект не затронут.
    guard.ensure_within_limit("b")


def test_reset_clears_counter() -> None:
    guard = CodeFixGuard(limit=2)
    guard.on_edit("proj")
    guard.on_edit("proj")

    guard.reset("proj")

    assert guard.iterations("proj") == 0
    guard.on_edit("proj")
    guard.ensure_within_limit("proj")


def test_remaining() -> None:
    guard = CodeFixGuard(limit=5)
    assert guard.remaining("proj") == 5
    guard.on_edit("proj")
    guard.on_edit("proj")
    assert guard.remaining("proj") == 3


def test_stale_session_restarts_counting() -> None:
    guard = CodeFixGuard(limit=2)
    guard.on_edit("proj")
    guard.on_edit("proj")

    # Имитируем, что последняя правка была давно.
    guard._state["proj"].last_edit_at -= 7200

    guard.ensure_within_limit("proj")  # не бросает: сессия сброшена
    assert guard.iterations("proj") == 0


def test_default_limit_from_settings() -> None:
    from app.config import settings

    guard = CodeFixGuard()
    assert guard.limit == settings.max_code_fix_iterations
