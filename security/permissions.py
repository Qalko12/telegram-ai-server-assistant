from pathlib import Path

from app.config import settings

_BLOCKED_SUBSTRINGS = ("/.ssh", "/etc/shadow", "/etc/gshadow")


class PathNotAllowedError(Exception):
    pass


def ensure_path_allowed(path: str) -> Path:
    resolved = Path(path).resolve()
    normalized = str(resolved).replace("\\", "/")

    for blocked in _BLOCKED_SUBSTRINGS:
        if blocked in normalized:
            raise PathNotAllowedError(f"Path is explicitly blocked: {resolved}")

    for allowed_root in settings.allowed_paths:
        allowed_resolved = Path(allowed_root).resolve()
        if resolved == allowed_resolved or allowed_resolved in resolved.parents:
            return resolved

    raise PathNotAllowedError(f"Path is outside ALLOWED_PATHS: {resolved}")
