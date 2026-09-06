import datetime
import shutil
from pathlib import Path

from app.config import settings
from security.permissions import ensure_path_allowed
from server.executor import CommandExecutor

MAX_FIND_RESULTS = 100


class FileTooLargeError(Exception):
    pass


class NotAFileError(Exception):
    pass


class ValidationFailedError(Exception):
    pass


def list_directory(path: str) -> list[dict[str, object]]:
    resolved = ensure_path_allowed(path)
    entries = []
    for entry in sorted(resolved.iterdir()):
        stat = entry.stat()
        entries.append({"name": entry.name, "is_dir": entry.is_dir(), "size": stat.st_size})
    return entries


def find_file(name: str, path: str) -> list[str]:
    resolved = ensure_path_allowed(path)
    matches = [str(p) for p in resolved.rglob(name)]
    return matches[:MAX_FIND_RESULTS]


def read_file(path: str) -> str:
    resolved = ensure_path_allowed(path)

    if resolved.is_dir():
        raise NotAFileError(f"Path is a directory, not a file: {resolved}")

    size = resolved.stat().st_size
    if size > settings.max_file_size:
        raise FileTooLargeError(f"File too large: {size} bytes (limit {settings.max_file_size})")

    return resolved.read_text(encoding="utf-8", errors="replace")


def backup_file(resolved: Path) -> Path | None:
    if not resolved.exists():
        return None

    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = backup_dir / f"{resolved.name}.{timestamp}.bak"
    shutil.copy2(resolved, backup_path)
    return backup_path


async def write_file(path: str, content: str, validate_command: list[str] | None = None) -> str:
    resolved = ensure_path_allowed(path)

    if resolved.is_dir():
        raise NotAFileError(f"Path is a directory, not a file: {resolved}")

    backup_path = backup_file(resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")

    if validate_command:
        result = await CommandExecutor().run(validate_command[0], validate_command[1:])
        if not result.success:
            if backup_path is not None:
                shutil.copy2(backup_path, resolved)
            else:
                resolved.unlink(missing_ok=True)
            raise ValidationFailedError(
                f"Validation failed (exit_code={result.exit_code}): {result.stderr or result.stdout}. "
                "Change rolled back."
            )
        return f"Файл записан и прошёл проверку ({' '.join(validate_command)}). Бэкап: {backup_path or 'не требовался'}."

    return f"Файл записан: {resolved}. Бэкап: {backup_path or 'не требовался (файл был новым)'}."


def delete_file(path: str) -> str:
    resolved = ensure_path_allowed(path)

    if not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {resolved}")
    if resolved.is_dir():
        raise NotAFileError(f"Path is a directory, not a file: {resolved}")

    backup_path = backup_file(resolved)
    resolved.unlink()
    return f"Файл удалён: {resolved}. Бэкап сохранён: {backup_path}."


def create_directory(path: str) -> str:
    resolved = ensure_path_allowed(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return f"Директория создана: {resolved}"
