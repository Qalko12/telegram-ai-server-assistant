import pytest
from sqlalchemy import select

import ai.tools.code_tools as code_tools_module
from ai.tools.code_tools import (
    CreateProjectParams,
    DeleteCodeFileParams,
    EditCodeFileParams,
    ProjectPathParams,
    SearchCodeParams,
    WriteCodeFileParams,
    handle_create_project,
    handle_create_project_directory,
    handle_delete_code_file,
    handle_edit_code_file,
    handle_list_project_files,
    handle_list_projects,
    handle_read_code_file,
    handle_search_code,
    handle_write_code_file,
)
from ai.tools.registry import ExecutionContext
from coding.workspace import WorkspaceError, ensure_project_name, resolve_inside
from database.models import Project


@pytest.fixture(autouse=True)
def _patch_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr(code_tools_module, "async_session_factory", session_factory)


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "code_workspace", str(tmp_path / "workspace"))
    return tmp_path / "workspace"


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


def test_ensure_project_name_valid() -> None:
    assert ensure_project_name("my-api") == "my-api"
    assert ensure_project_name("bot_v2") == "bot_v2"


def test_ensure_project_name_rejects_bad_names() -> None:
    for bad in ["../etc", "a/b", "-leading", ".hidden", "with space", "", "x" * 200]:
        with pytest.raises(WorkspaceError):
            ensure_project_name(bad)


def test_resolve_inside_blocks_escape(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    assert resolve_inside(root, "app/main.py").name == "main.py"
    for bad in ["../secret", "app/../../outside", "/etc/passwd"]:
        with pytest.raises(WorkspaceError):
            resolve_inside(root, bad)


async def test_create_project_structure(_workspace, session_factory) -> None:
    result = await handle_create_project(
        CreateProjectParams(project="my-api", description="Тестовый API"), CTX
    )

    assert "Проект создан" in result
    assert (_workspace / "my-api" / "app").is_dir()
    assert (_workspace / "my-api" / "tests").is_dir()
    assert "Тестовый API" in (_workspace / "my-api" / "README.md").read_text(encoding="utf-8")

    async with session_factory() as session:
        project = (await session.execute(select(Project))).scalar_one()
    assert project.name == "my-api"
    assert project.status == "created"


async def test_create_project_duplicate_rejected(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="my-api"), CTX)
    with pytest.raises(WorkspaceError, match="уже существует"):
        await handle_create_project(CreateProjectParams(project="my-api"), CTX)


async def test_list_projects(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="alpha"), CTX)
    await handle_create_project(CreateProjectParams(project="beta"), CTX)

    result = await handle_list_projects(code_tools_module._NoParams(), CTX)

    assert "alpha" in result
    assert "beta" in result


async def test_list_projects_empty_workspace(_workspace) -> None:
    result = await handle_list_projects(code_tools_module._NoParams(), CTX)
    assert "пуст" in result.lower()


async def test_write_and_read_code_file(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)

    write_result = await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="app/main.py", content="print('hello')"), CTX
    )
    assert "записан" in write_result

    content = await handle_read_code_file(ProjectPathParams(project="proj", path="app/main.py"), CTX)
    assert content == "print('hello')"


async def test_read_missing_file_reports_error(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    with pytest.raises(WorkspaceError, match="не найден"):
        await handle_read_code_file(ProjectPathParams(project="proj", path="nope.py"), CTX)


async def test_operations_on_missing_project_report_error(_workspace) -> None:
    with pytest.raises(WorkspaceError, match="Проект не найден"):
        await handle_read_code_file(ProjectPathParams(project="ghost", path="x.py"), CTX)


async def test_edit_code_file_single_occurrence(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="app/x.py", content="a = 1\nb = a + 1"), CTX
    )

    result = await handle_edit_code_file(
        EditCodeFileParams(project="proj", path="app/x.py", old_string="b = a + 1", new_string="b = a + 2"), CTX
    )
    assert "1" in result

    content = await handle_read_code_file(ProjectPathParams(project="proj", path="app/x.py"), CTX)
    assert content == "a = 1\nb = a + 2"


async def test_edit_code_file_ambiguous_raises(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="dup.py", content="x = 1\nx = 1"), CTX
    )

    from coding.editor import EditAmbiguousError

    with pytest.raises(EditAmbiguousError):
        await handle_edit_code_file(
            EditCodeFileParams(project="proj", path="dup.py", old_string="x = 1", new_string="y = 2"), CTX
        )

    # replace_all меняет все вхождения
    result = await handle_edit_code_file(
        EditCodeFileParams(project="proj", path="dup.py", old_string="x = 1", new_string="y = 2", replace_all=True), CTX
    )
    assert "2" in result
    content = await handle_read_code_file(ProjectPathParams(project="proj", path="dup.py"), CTX)
    assert content == "y = 2\ny = 2"


async def test_edit_code_file_not_found_raises(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="proj", path="f.py", content="abc"), CTX)

    from coding.editor import EditNotFoundError

    with pytest.raises(EditNotFoundError):
        await handle_edit_code_file(
            EditCodeFileParams(project="proj", path="f.py", old_string="zzz", new_string="q"), CTX
        )


async def test_path_escape_blocked(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    with pytest.raises(WorkspaceError):
        await handle_read_code_file(ProjectPathParams(project="proj", path="../../etc/passwd"), CTX)
    with pytest.raises(WorkspaceError):
        await handle_write_code_file(
            WriteCodeFileParams(project="proj", path="../evil.py", content="x"), CTX
        )


async def test_delete_code_file_requires_confirmation_level_and_works(_workspace) -> None:
    from ai.tools.code_tools import DELETE_CODE_FILE
    from security.levels import SecurityLevel

    assert DELETE_CODE_FILE.security_level == SecurityLevel.MODERATE

    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="proj", path="del.py", content="x"), CTX)

    result = await handle_delete_code_file(DeleteCodeFileParams(project="proj", path="del.py"), CTX)
    assert "удалён" in result
    assert not (_workspace / "proj" / "del.py").exists()


async def test_create_project_directory(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_create_project_directory(
        ProjectPathParams(project="proj", path="src/utils"), CTX
    )
    assert (_workspace / "proj" / "src" / "utils").is_dir()


async def test_list_project_files(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(WriteCodeFileParams(project="proj", path="app/main.py", content="x"), CTX)

    result = await handle_list_project_files(ProjectPathParams(project="proj", path="."), CTX)

    assert "app/main.py" in result
    assert "README.md" in result
    assert "[dir] tests/" in result


async def test_search_code(_workspace) -> None:
    await handle_create_project(CreateProjectParams(project="proj"), CTX)
    await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="app/a.py", content="def hello_world():\n    pass"), CTX
    )
    await handle_write_code_file(
        WriteCodeFileParams(project="proj", path="app/b.py", content="x = 1"), CTX
    )

    result = await handle_search_code(
        SearchCodeParams(project="proj", query="hello_world"), CTX
    )
    assert "app/a.py:1" in result

    result_filtered = await handle_search_code(
        SearchCodeParams(project="proj", query="x =", file_pattern="*.py"), CTX
    )
    assert "app/b.py" in result_filtered

    result_none = await handle_search_code(
        SearchCodeParams(project="proj", query="nonexistent"), CTX
    )
    assert "не найдено" in result_none.lower()


async def test_write_code_file_registers_project_in_registry(_workspace, session_factory) -> None:
    # Проект создан на диске вручную (без create_project) — запись файла регистрирует его.
    (_workspace / "manual").mkdir(parents=True)

    await handle_write_code_file(
        WriteCodeFileParams(project="manual", path="main.py", content="x"), CTX
    )

    async with session_factory() as session:
        project = (await session.execute(select(Project))).scalar_one_or_none()
    assert project is not None
    assert project.name == "manual"
