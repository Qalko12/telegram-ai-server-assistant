"""Code Workspace — корневая директория (/opt/ai-workspace), внутри которой AI
создаёт и правит проекты. Все пути code-инструментов жёстко ограничены workspace'ом:
выход за его пределы (включая ../-эскейпы и симлинки) блокируется.
"""

import re
from pathlib import Path

from app.config import settings

_PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

MAX_LIST_ENTRIES = 500
MAX_SEARCH_MATCHES = 200


class WorkspaceError(Exception):
    pass


def workspace_root() -> Path:
    root = Path(settings.code_workspace)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_project_name(name: str) -> str:
    """Имя проекта = имя директории. Запрещаем разделители и спецсимволы."""
    if not _PROJECT_NAME_PATTERN.match(name):
        raise WorkspaceError(
            f"Недопустимое имя проекта: {name!r}. Разрешены буквы, цифры, '.', '_', '-', начало — буква/цифра."
        )
    if name in {".", ".."}:
        raise WorkspaceError(f"Недопустимое имя проекта: {name!r}")
    return name


def project_root(project: str) -> Path:
    """Корень проекта внутри workspace. Гарантирует, что путь остаётся внутри workspace."""
    ensure_project_name(project)
    root = workspace_root().resolve()
    candidate = (root / project).resolve()
    if root not in candidate.parents:
        raise WorkspaceError(f"Путь проекта выходит за пределы workspace: {project!r}")
    if not candidate.exists():
        raise WorkspaceError(f"Проект не найден: {project}. Создайте его (create_project) или проверьте имя (list_projects).")
    if not candidate.is_dir():
        raise WorkspaceError(f"Путь проекта не является директорией: {project}")
    return candidate


def resolve_inside(root: Path, relative: str) -> Path:
    """Резолвит относительный путь строго внутри root; блокирует выход за пределы."""
    if Path(relative).is_absolute():
        raise WorkspaceError(f"Путь должен быть относительным к проекту, получен абсолютный: {relative!r}")

    resolved_root = root.resolve()
    candidate = (root / relative).resolve()

    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise WorkspaceError(f"Путь выходит за пределы workspace: {relative!r}")
    return candidate


def list_project_dirs() -> list[str]:
    """Список директорий-проектов в workspace (без скрытых и служебных)."""
    root = workspace_root()
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


async def set_project_status(name: str, status: str) -> None:
    """Обновляет статус проекта в реестре (created → tests_passed → running и т.д.)."""
    from sqlalchemy import select

    from database.engine import async_session_factory
    from database.models import Project

    async with async_session_factory() as session:
        project = (await session.execute(select(Project).where(Project.name == name))).scalar_one_or_none()
        if project is not None:
            project.status = status
            await session.commit()
