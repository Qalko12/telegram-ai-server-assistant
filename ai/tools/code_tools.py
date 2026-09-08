"""AI-инструменты Code Workspace (файловая часть).

Все операции строго внутри CODE_WORKSPACE/<project>. Уровни безопасности:
- чтение/листинг/поиск — SAFE;
- создание проекта, запись/правка файлов — SAFE, так как workspace изолирован
  от системных путей и не может повредить сервер (в отличие от write_file из
  server_tools, который работает по всему ALLOWED_PATHS и требует подтверждения);
- удаление файлов — MODERATE (необратимая операция, через подтверждение).

Исполнение кода (тесты/сборка/запуск) — отдельные инструменты в coding/sandbox
и coding/tester, подключаются в фазе 8.
"""

from pydantic import BaseModel, Field
from sqlalchemy import select

from ai.tools.registry import ExecutionContext, ToolSpec
from coding import editor
from coding.workspace import (
    WorkspaceError,
    ensure_project_name,
    list_project_dirs,
    project_root,
    resolve_inside,
    workspace_root,
)
from database.engine import async_session_factory
from database.models import Project
from security.levels import SecurityLevel


class _NoParams(BaseModel):
    pass


class ProjectNameParams(BaseModel):
    project: str = Field(description="Имя проекта — директория внутри Code Workspace, например 'my-api'.")


class CreateProjectParams(BaseModel):
    project: str = Field(description="Имя нового проекта (латиница, цифры, '-', '_', '.').")
    description: str = Field(default="", description="Краткое описание проекта (попадёт в реестр проектов).")


class ProjectPathParams(BaseModel):
    project: str = Field(description="Имя проекта внутри Code Workspace.")
    path: str = Field(default=".", description="Относительный путь внутри проекта, например 'app/main.py' или '.'")


class WriteCodeFileParams(BaseModel):
    project: str
    path: str = Field(description="Относительный путь файла внутри проекта, например 'app/main.py'.")
    content: str = Field(description="Полное содержимое файла.")


class EditCodeFileParams(BaseModel):
    project: str
    path: str
    old_string: str = Field(description="Точный фрагмент для замены. Должен встречаться в файле ровно один раз (или используйте replace_all).")
    new_string: str = Field(description="Заменяющий фрагмент.")
    replace_all: bool = Field(default=False, description="Заменить все вхождения вместо одного.")


class DeleteCodeFileParams(BaseModel):
    project: str
    path: str


class SearchCodeParams(BaseModel):
    project: str
    query: str = Field(description="Подстрока для поиска (без учёта регистра).")
    file_pattern: str = Field(default="*", description="Glob-фильтр имён файлов, например '*.py'.")


async def _sync_project_registry(name: str, path: str) -> None:
    """Вносит проект в реестр (таблица projects), если его там ещё нет."""
    async with async_session_factory() as session:
        existing = (await session.execute(select(Project).where(Project.name == name))).scalar_one_or_none()
        if existing is None:
            session.add(Project(name=name, path=path, status="created"))
            await session.commit()


async def handle_list_projects(params: _NoParams, ctx: ExecutionContext) -> str:
    dirs = list_project_dirs()

    async with async_session_factory() as session:
        rows = (await session.execute(select(Project))).scalars().all()
        registry: dict[str, Project] = {row.name: row for row in rows}

    if not dirs:
        return f"Code Workspace пуст: {workspace_root()}. Проекты ещё не созданы."

    lines = []
    for name in dirs:
        project = registry.get(name)
        status = project.status if project else "—"
        lines.append(f"• {name} (статус: {status}) — {workspace_root() / name}")
    return "Проекты в Code Workspace:\n" + "\n".join(lines)


async def handle_create_project(params: CreateProjectParams, ctx: ExecutionContext) -> str:
    name = ensure_project_name(params.project)
    root = workspace_root() / name
    if root.exists():
        raise WorkspaceError(f"Проект уже существует: {root}. Используйте его или выберите другое имя.")

    root.mkdir(parents=True)
    (root / "app").mkdir()
    (root / "tests").mkdir()
    readme = f"# {name}\n\n{params.description or 'Проект создан AI-ассистентом в Code Workspace.'}\n"
    (root / "README.md").write_text(readme, encoding="utf-8")

    await _sync_project_registry(name, str(root))
    return (
        f"Проект создан: {root}\n"
        "Структура: app/, tests/, README.md\n"
        "Дальше можно писать код: write_code_file / edit_code_file."
    )


async def handle_list_project_files(params: ProjectPathParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    entries = editor.list_files(root, params.path)
    if not entries:
        return "(пустая директория)"
    lines = [f"{'[dir] ' if e['is_dir'] else ''}{e['path']}" + ("" if e["is_dir"] else f" ({e['size']} bytes)") for e in entries]
    return f"Файлы проекта {params.project}:\n" + "\n".join(lines)


async def handle_read_code_file(params: ProjectPathParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    target = resolve_inside(root, params.path)
    return editor.read_code(target)


async def handle_write_code_file(params: WriteCodeFileParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    target = resolve_inside(root, params.path)
    result = editor.write_code(target, params.content)
    await _sync_project_registry(params.project, str(root))
    return f"{result} ({params.project}/{params.path})"


async def handle_edit_code_file(params: EditCodeFileParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    target = resolve_inside(root, params.path)
    result = editor.edit_code(target, params.old_string, params.new_string, replace_all=params.replace_all)
    return f"{result} ({params.project}/{params.path})"


async def handle_delete_code_file(params: DeleteCodeFileParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    target = resolve_inside(root, params.path)
    result = editor.delete_code(target)
    return f"{result}: {params.project}/{params.path}"


async def handle_create_project_directory(params: ProjectPathParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    target = resolve_inside(root, params.path)
    result = editor.create_directory(target)
    return f"{result}: {params.project}/{params.path}"


async def handle_search_code(params: SearchCodeParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    matches = editor.search_code(root, params.query, params.file_pattern)
    if not matches:
        return f"Совпадений не найдено: {params.query!r} в {params.project} (паттерн: {params.file_pattern})."
    return f"Найдено совпадений: {len(matches)}\n" + "\n".join(matches)


LIST_PROJECTS = ToolSpec(
    name="list_projects",
    description="Показать все проекты в Code Workspace с их статусами.",
    input_model=_NoParams,
    handler=handle_list_projects,
    security_level=SecurityLevel.SAFE,
)

CREATE_PROJECT = ToolSpec(
    name="create_project",
    description=(
        "Создать новый проект в Code Workspace: директория с базовой структурой (app/, tests/, README.md). "
        "Используй, когда оператор просит создать приложение/бота/API/сайт/скрипт."
    ),
    input_model=CreateProjectParams,
    handler=handle_create_project,
    security_level=SecurityLevel.SAFE,
)

LIST_PROJECT_FILES = ToolSpec(
    name="list_project_files",
    description="Показать дерево файлов проекта в Code Workspace (служебные директории вроде node_modules/.git пропускаются).",
    input_model=ProjectPathParams,
    handler=handle_list_project_files,
    security_level=SecurityLevel.SAFE,
)

READ_CODE_FILE = ToolSpec(
    name="read_code_file",
    description="Прочитать файл проекта в Code Workspace по относительному пути.",
    input_model=ProjectPathParams,
    handler=handle_read_code_file,
    security_level=SecurityLevel.SAFE,
)

WRITE_CODE_FILE = ToolSpec(
    name="write_code_file",
    description=(
        "Записать файл в проект Code Workspace (полное содержимое). Для правки существующего "
        "файла предпочтительнее edit_code_file — она не теряет остальной код."
    ),
    input_model=WriteCodeFileParams,
    handler=handle_write_code_file,
    security_level=SecurityLevel.SAFE,
)

EDIT_CODE_FILE = ToolSpec(
    name="edit_code_file",
    description=(
        "Точечная правка файла проекта: заменить old_string на new_string. old_string должен "
        "совпадать с текстом файла буквально и встречаться ровно один раз (иначе уточните фрагмент "
        "или поставьте replace_all=true)."
    ),
    input_model=EditCodeFileParams,
    handler=handle_edit_code_file,
    security_level=SecurityLevel.SAFE,
)

DELETE_CODE_FILE = ToolSpec(
    name="delete_code_file",
    description="Удалить файл из проекта Code Workspace. Требует подтверждения.",
    input_model=DeleteCodeFileParams,
    handler=handle_delete_code_file,
    security_level=SecurityLevel.MODERATE,
)

CREATE_PROJECT_DIRECTORY = ToolSpec(
    name="create_project_directory",
    description="Создать поддиректорию внутри проекта Code Workspace.",
    input_model=ProjectPathParams,
    handler=handle_create_project_directory,
    security_level=SecurityLevel.SAFE,
)

SEARCH_CODE = ToolSpec(
    name="search_code",
    description="Подстрочный поиск по коду проекта (без учёта регистра), с glob-фильтром имён файлов. Возвращает файл:строку:текст.",
    input_model=SearchCodeParams,
    handler=handle_search_code,
    security_level=SecurityLevel.SAFE,
)

# find_code_references из ТЗ — поиск мест использования идентификатора; реализуем тем же
# механизмом: отдельная регистрация с акцентом на поиск ссылок.
FIND_CODE_REFERENCES = ToolSpec(
    name="find_code_references",
    description="Найти все места использования имени (функции, класса, переменной) в коде проекта.",
    input_model=SearchCodeParams,
    handler=handle_search_code,
    security_level=SecurityLevel.SAFE,
)


def all_code_tools() -> tuple[ToolSpec, ...]:
    return (
        LIST_PROJECTS,
        CREATE_PROJECT,
        LIST_PROJECT_FILES,
        READ_CODE_FILE,
        WRITE_CODE_FILE,
        EDIT_CODE_FILE,
        DELETE_CODE_FILE,
        CREATE_PROJECT_DIRECTORY,
        SEARCH_CODE,
        FIND_CODE_REFERENCES,
    )
