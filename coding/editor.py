"""Файловые операции внутри Code Workspace: чтение, запись, точечное редактирование,
поиск по коду. Все функции работают только с путями, проверенными через
workspace.resolve_inside (см. coding/workspace.py).
"""

import fnmatch
from pathlib import Path

from app.config import settings
from coding.workspace import MAX_LIST_ENTRIES, MAX_SEARCH_MATCHES, WorkspaceError

# Директории, которые не имеет смысла обходить при поиске/листинге.
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build", ".next"}

MAX_EDIT_FILE_SIZE = 2 * 1024 * 1024  # 2 МБ — code-инструменты не работают с бинарниками/логами гигантских размеров


class EditNotFoundError(WorkspaceError):
    pass


class EditAmbiguousError(WorkspaceError):
    pass


def list_files(root: Path, relative: str = ".") -> list[dict[str, object]]:
    """Плоский список файлов/директорий с путями относительно root."""
    base = (root / relative) if relative != "." else root
    if not base.exists():
        raise WorkspaceError(f"Путь не найден: {relative!r}")
    if base.is_file():
        stat = base.stat()
        return [{"path": relative, "is_dir": False, "size": stat.st_size}]

    entries: list[dict[str, object]] = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir():
            entries.append({"path": rel + "/", "is_dir": True, "size": 0})
        else:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append({"path": rel, "is_dir": False, "size": size})
        if len(entries) >= MAX_LIST_ENTRIES:
            entries.append({"path": f"[... список обрезан на {MAX_LIST_ENTRIES} записях]", "is_dir": False, "size": 0})
            break
    return entries


def read_code(path: Path) -> str:
    if path.is_dir():
        raise WorkspaceError(f"Это директория, а не файл: {path.name}")
    if not path.exists():
        raise WorkspaceError(f"Файл не найден: {path.name}")

    size = path.stat().st_size
    limit = min(settings.max_file_size, 512 * 1024)
    if size > limit:
        raise WorkspaceError(f"Файл слишком большой для чтения как код: {size} байт (лимит {limit})")

    return path.read_text(encoding="utf-8", errors="replace")


def write_code(path: Path, content: str) -> str:
    if path.is_dir():
        raise WorkspaceError(f"Это директория, а не файл: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Файл записан: {path.name} ({len(content)} символов)."


def edit_code(path: Path, old_string: str, new_string: str, *, replace_all: bool = False) -> str:
    """Точечная правка: заменяет old_string на new_string.

    По умолчанию old_string должен встречаться ровно один раз (защита от случайной
    правки не того места). Если совпадений нет или больше одного — ошибка, файл не меняется.
    """
    if not path.exists():
        raise WorkspaceError(f"Файл не найден: {path.name}")
    if path.stat().st_size > MAX_EDIT_FILE_SIZE:
        raise WorkspaceError("Файл слишком большой для точечного редактирования.")

    content = path.read_text(encoding="utf-8", errors="replace")
    occurrences = content.count(old_string)

    if occurrences == 0:
        raise EditNotFoundError("Текст для замены не найден в файле. Проверьте точное совпадение (пробелы, регистр).")
    if occurrences > 1 and not replace_all:
        raise EditAmbiguousError(
            f"Найдено {occurrences} совпадений — уточните фрагмент или используйте replace_all=true."
        )

    if replace_all:
        updated = content.replace(old_string, new_string)
    else:
        updated = content.replace(old_string, new_string, 1)

    path.write_text(updated, encoding="utf-8")
    replaced = occurrences if replace_all else 1
    return f"Заменено вхождений: {replaced}."


def delete_code(path: Path) -> str:
    if not path.exists():
        raise WorkspaceError(f"Файл не найден: {path.name}")
    if path.is_dir():
        raise WorkspaceError("Это директория. Удаление директорий проектов — через отдельную операцию с подтверждением.")
    path.unlink()
    return "Файл удалён."


def create_directory(path: Path) -> str:
    if path.exists() and not path.is_dir():
        raise WorkspaceError(f"Путь уже занят файлом: {path.name}")
    path.mkdir(parents=True, exist_ok=True)
    return "Директория создана."


def search_code(root: Path, query: str, file_pattern: str = "*") -> list[str]:
    """Подстрочный поиск (без учёта регистра) по файлам проекта. Возвращает file:line: текст."""
    matches: list[str] = []
    needle = query.lower()

    for path in _iter_files(root):
        if not fnmatch.fnmatch(path.name, file_pattern):
            continue
        try:
            if path.stat().st_size > MAX_EDIT_FILE_SIZE:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            if needle in line.lower():
                rel = path.relative_to(root).as_posix()
                matches.append(f"{rel}:{line_no}: {line.strip()[:200]}")
                if len(matches) >= MAX_SEARCH_MATCHES:
                    matches.append(f"[... обрезано на {MAX_SEARCH_MATCHES} совпадениях]")
                    return matches
    return matches


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path
