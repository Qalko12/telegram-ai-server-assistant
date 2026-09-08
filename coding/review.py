"""Сбор материалов для code review (ТЗ §34).

Сам анализ делает Claude в основном agent-цикле: инструмент review_project собирает
компактный снимок проекта (структура + содержимое ключевых файлов), а системный
промпт предписывает формат вывода по severity (Critical/High/Medium/Low) и чек-лист
проверок: баги, безопасность, архитектура, производительность, обработка ошибок,
зависимости, захардкоженные секреты.
"""

from pathlib import Path

from coding.editor import _SKIP_DIRS
from coding.workspace import MAX_LIST_ENTRIES

REVIEW_MAX_FILE_CHARS = 12_000
REVIEW_MAX_TOTAL_CHARS = 90_000

# Файлы, наиболее релевантные для ревью (в порядке приоритета).
_PRIORITY_NAMES = {
    "requirements.txt", "package.json", "pyproject.toml", "Dockerfile", "docker-compose.yml",
    ".env.example", "settings.py", "config.py", "main.py", "app.py", "manage.py",
}
_PRIORITY_SUFFIXES = (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php")
_IGNORE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".lock", ".min.js", ".map", ".woff", ".woff2", ".ttf")


def collect_review_material(root: Path, max_files: int = 25) -> str:
    """Возвращает текст: дерево проекта + содержимое приоритетных файлов."""
    files = _gather_files(root)
    if not files:
        return "Проект пуст — ревьюить нечего."

    selected = _select_files(files, max_files)

    parts = ["STRUCTURE:"]
    for path in files[:MAX_LIST_ENTRIES]:
        parts.append(f"  {path.relative_to(root).as_posix()}")

    parts.append("\nFILE CONTENTS:")
    budget = REVIEW_MAX_TOTAL_CHARS
    for path in selected:
        if budget <= 0:
            parts.append("\n[остальные файлы не вошли в снимок из-за лимита размера]")
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunk = text[:REVIEW_MAX_FILE_CHARS]
        chunk = chunk[: min(len(chunk), budget)]
        budget -= len(chunk)
        rel = path.relative_to(root).as_posix()
        truncated = "\n[...файл обрезан...]" if len(text) > len(chunk) else ""
        parts.append(f"\n=== {rel} ===\n{chunk}{truncated}")

    return "\n".join(parts)


def _gather_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS or part.startswith(".") for part in relative_parts):
            continue
        if path.suffix.lower() in _IGNORE_SUFFIXES:
            continue
        files.append(path)
    return files


def _select_files(files: list[Path], max_files: int) -> list[Path]:
    def score(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if name in _PRIORITY_NAMES:
            return (0, name)
        if name.startswith(("main", "app", "server", "index")):
            return (1, name)
        if path.suffix.lower() in _PRIORITY_SUFFIXES:
            return (2, path.name.lower())
        return (3, path.name.lower())

    return sorted(files, key=score)[:max_files]
