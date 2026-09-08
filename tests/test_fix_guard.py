import pytest

from coding.fix_guard import CodeFixGuard, FixLimitReachedError


def test_edits_alone_do_not_count_iterations() -> None:
    guard = CodeFixGuard(limit=3)
    guard.on_edit("proj")
    guard.on_edit("proj")
    guard.ensure_within_limit("proj")
    assert guard.iterations("proj") == 0


def test_edit_then_failure_counts_one_cycle() -> None:
    guard = CodeFixGuard(limit=3)
    guard.on_edit("proj")
    assert guard.on_test_failure("proj") == 1

    # Повторный провал без новой правки — не новый цикл (тот же самый тест снова упал).
    assert guard.on_test_failure("proj") == 1


def test_limit_reached_blocks_edits() -> None:
    guard = CodeFixGuard(limit=2)

    guard.on_edit("proj")
    guard.on_test_failure("proj")
    guard.ensure_within_limit("proj")

    guard.on_edit("proj")
    guard.on_test_failure("proj")

    with pytest.raises(FixLimitReachedError) as exc_info:
        guard.ensure_within_limit("proj")
    assert "2" in str(exc_info.value)


def test_guard_is_per_project() -> None:
    guard = CodeFixGuard(limit=1)
    guard.on_edit("a")
    guard.on_test_failure("a")

    with pytest.raises(FixLimitReachedError):
        guard.ensure_within_limit("a")
    guard.ensure_within_limit("b")
    guard.on_edit("b")


def test_success_resets_counter() -> None:
    guard = CodeFixGuard(limit=2)
    guard.on_edit("proj")
    guard.on_test_failure("proj")
    guard.on_edit("proj")
    guard.on_test_failure("proj")

    guard.on_test_success("proj")

    assert guard.iterations("proj") == 0
    guard.ensure_within_limit("proj")
    guard.on_edit("proj")


def test_remaining() -> None:
    guard = CodeFixGuard(limit=5)
    assert guard.remaining("proj") == 5
    guard.on_edit("proj")
    guard.on_test_failure("proj")
    guard.on_edit("proj")
    guard.on_test_failure("proj")
    assert guard.remaining("proj") == 3


def test_stale_session_restarts_counting() -> None:
    guard = CodeFixGuard(limit=1)
    guard.on_edit("proj")
    guard.on_test_failure("proj")

    guard._state["proj"].last_activity -= 7200

    guard.ensure_within_limit("proj")  # не бросает: сессия устарела
    assert guard.iterations("proj") == 0


def test_default_limit_from_settings() -> None:
    from app.config import settings

    guard = CodeFixGuard()
    assert guard.limit == settings.max_code_fix_iterations
