"""Тесты git-операций на реальных временных репозиториях."""

import pytest

from coding.git_ops import (
    GitError,
    git_commit_all,
    git_create_branch,
    git_current_branch,
    git_diff,
    git_init,
    git_log,
    git_status,
    is_protected_branch,
    validate_branch_name,
)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    # Локальная (для процесса) идентичность — коммиты работают в CI и на любой машине.
    # setenv обновляет настоящее os.environ (с putenv), поэтому видно subprocess'ам.
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Bot")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "bot@test.local")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Bot")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bot@test.local")


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    return root


async def test_init_creates_repo_on_main(project) -> None:
    result = await git_init(project)
    assert "инициализирован" in result

    assert (project / ".git").is_dir()
    assert await git_current_branch(project) == "main"

    # Повторный init — не ошибка.
    result2 = await git_init(project)
    assert "уже является" in result2


async def test_status_on_non_repo_raises(project) -> None:
    with pytest.raises(GitError, match="не является git-репозиторием"):
        await git_status(project)


async def test_status_shows_untracked(project) -> None:
    await git_init(project)
    (project / "app.py").write_text("print(1)\n", encoding="utf-8")

    status = await git_status(project)
    assert "app.py" in status


async def test_commit_all_creates_commit(project) -> None:
    await git_init(project)
    (project / "app.py").write_text("print(1)\n", encoding="utf-8")

    result = await git_commit_all(project, "первый коммит")

    assert "Коммит создан" in result
    assert "main" in result
    log = await git_log(project)
    assert "первый коммит" in log


async def test_commit_nothing_to_commit(project) -> None:
    await git_init(project)
    (project / "app.py").write_text("x", encoding="utf-8")
    await git_commit_all(project, "c1")

    result = await git_commit_all(project, "c2")
    assert "Нет изменений" in result


async def test_diff_shows_changes(project) -> None:
    await git_init(project)
    (project / "app.py").write_text("a = 1\n", encoding="utf-8")
    await git_commit_all(project, "init")

    (project / "app.py").write_text("a = 2\n", encoding="utf-8")
    diff = await git_diff(project)
    assert "-a = 1" in diff
    assert "+a = 2" in diff

    staged = await git_diff(project, staged=True)
    assert "Изменений нет" in staged or staged == ""


async def test_create_branch_and_checkout(project) -> None:
    await git_init(project)
    (project / "f.txt").write_text("1", encoding="utf-8")
    await git_commit_all(project, "init")

    await git_create_branch(project, "feature/x")
    assert await git_current_branch(project) == "main"

    await git_create_branch(project, "hotfix", checkout=True)
    assert await git_current_branch(project) == "hotfix"


async def test_branch_name_validation(project) -> None:
    await git_init(project)
    for bad in ["-evil", "../escape", "with space", "", "a" * 200]:
        with pytest.raises(GitError):
            validate_branch_name(bad)

    with pytest.raises(GitError):
        await git_create_branch(project, "--exec=rm -rf /")


async def test_commit_message_validation(project) -> None:
    await git_init(project)
    (project / "f.txt").write_text("1", encoding="utf-8")

    with pytest.raises(GitError):
        await git_commit_all(project, "   ")
    with pytest.raises(GitError):
        await git_commit_all(project, "x" * 5000)


async def test_log_limit(project) -> None:
    await git_init(project)
    for i in range(5):
        (project / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        await git_commit_all(project, f"commit-{i}")

    log = await git_log(project, limit=3)
    assert "commit-4" in log
    assert "commit-1" not in log


async def test_log_on_empty_repo(project) -> None:
    await git_init(project)
    log = await git_log(project)
    assert "нет коммитов" in log.lower()


def test_is_protected_branch() -> None:
    assert is_protected_branch("main")
    assert is_protected_branch("MASTER")
    assert not is_protected_branch("feature/x")
    assert not is_protected_branch("dev")
