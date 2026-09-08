import pytest

import ai.tools.git_tools as git_tools_module
from ai.tools.git_tools import (
    GIT_COMMIT,
    GitBranchParams,
    GitCommitParams,
    GitInitParams,
    GitLogParams,
    ProjectParams,
    handle_git_commit,
    handle_git_create_branch,
    handle_git_init,
    handle_git_log,
    handle_git_status,
    all_git_tools,
)
from ai.tools.registry import ExecutionContext
from security.levels import SecurityLevel


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(workspace))

    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Bot")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "bot@test.local")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Bot")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bot@test.local")
    return workspace


@pytest.fixture
async def git_project(_workspace):
    (_workspace / "proj").mkdir()
    return "proj"


def test_git_tools_security_levels() -> None:
    for tool in all_git_tools():
        if tool.name in {"git_status", "git_diff", "git_log"}:
            assert tool.security_level == SecurityLevel.SAFE, tool.name
        else:
            assert tool.security_level == SecurityLevel.MODERATE, tool.name

    assert GIT_COMMIT.security_level == SecurityLevel.MODERATE


async def test_init_status_commit_flow(git_project) -> None:
    init_result = await handle_git_init(GitInitParams(project="proj"), CTX)
    assert "инициализирован" in init_result

    status = await handle_git_status(ProjectParams(project="proj"), CTX)
    assert "чистое" in status or "##" in status

    from ai.tools.code_tools import WriteCodeFileParams, handle_write_code_file

    await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="main.py", content="print('hi')"), CTX
    )

    status = await handle_git_status(ProjectParams(project="proj"), CTX)
    assert "main.py" in status

    commit_result = await handle_git_commit(
        GitCommitParams(project="proj", message="добавил main.py"), CTX
    )
    assert "добавил main.py" in commit_result
    assert "⚠️" in commit_result  # коммит в основную ветку — с предупреждением

    log = await handle_git_log(GitLogParams(project="proj"), CTX)
    assert "добавил main.py" in log


async def test_create_branch_then_commit_not_protected(git_project) -> None:
    await handle_git_init(GitInitParams(project="proj"), CTX)

    from ai.tools.code_tools import WriteCodeFileParams, handle_write_code_file

    await handle_write_code_file(WriteCodeFileParams(project="proj", path="f.py", content="x"), CTX)
    await handle_git_commit(GitCommitParams(project="proj", message="init"), CTX)

    branch_result = await handle_git_create_branch(
        GitBranchParams(project="proj", branch="feature/x", checkout=True), CTX
    )
    assert branch_result

    await handle_write_code_file(WriteCodeFileParams(project="proj", path="g.py", content="y"), CTX)
    commit_result = await handle_git_commit(GitCommitParams(project="proj", message="feature work"), CTX)

    assert "feature/x" in commit_result
    assert "⚠️" not in commit_result


async def test_missing_project_reports_error() -> None:
    from coding.workspace import WorkspaceError

    with pytest.raises(WorkspaceError, match="Проект не найден"):
        await handle_git_status(ProjectParams(project="ghost"), CTX)
