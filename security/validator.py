import re

_DENY_PATTERNS = [
    re.compile(r"rm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+/(\s|$)"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"docker\s+system\s+prune"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"),  # fork bomb
    re.compile(r">\s*/dev/sd[a-z]"),
]


class CommandDeniedError(Exception):
    pass


def validate_command(program: str, args: list[str]) -> None:
    full_command = " ".join([program, *args])
    for pattern in _DENY_PATTERNS:
        if pattern.search(full_command):
            raise CommandDeniedError(f"Command matches deny-list pattern: {full_command!r}")
