from app.config import settings
from security.permissions import ensure_path_allowed

MAX_FIND_RESULTS = 100


class FileTooLargeError(Exception):
    pass


class NotAFileError(Exception):
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
