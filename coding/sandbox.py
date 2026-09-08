"""Запуск кода в изолированном Docker-контейнере (Code Sandbox).

Гарантии изоляции (см. PLAN.md):
- лимиты памяти и CPU (SANDBOX_MEMORY_LIMIT / SANDBOX_CPU_LIMIT);
- network=none по умолчанию; сеть включается только явно (install_dependency);
- cap-drop ALL + no-new-privileges;
- non-root пользователь внутри образа (uid 1000);
- --rm + принудительное удаление контейнера по таймауту (защита от зависших процессов);
- таймаут и лимит вывода через CommandExecutor.
"""

import asyncio
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from server.executor import CommandExecutor, CommandResult

SANDBOX_UID = 1000
SANDBOX_GID = 1000
CONTAINER_NAME_PREFIX = "ai-sbx-"
EXECUTOR_TIMEOUT_SLACK_SECONDS = 15


class SandboxImageMissingError(Exception):
    pass


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def sandbox_image(language: str) -> str:
    if language == "python":
        return settings.sandbox_image_python
    if language == "node":
        return settings.sandbox_image_node
    raise ValueError(f"Неизвестный язык sandbox: {language!r}")


async def image_exists(image: str, executor: CommandExecutor | None = None) -> bool:
    executor = executor or CommandExecutor(timeout=15)
    result = await executor.run("docker", ["image", "inspect", image])
    return result.success


def _chown_tree_for_sandbox(root: Path) -> None:
    """Передаёт владение файлами проекта sandbox-пользователю (uid 1000).

    Нужно, потому что бот работает от root, а контейнер — от непривилегированного
    пользователя: без chown тесты/форматтеры не смогут писать в смонтированный проект.
    Вне root-окружения (например, dev на Windows) — no-op.
    """
    if not hasattr(os, "getuid") or os.getuid() != 0:
        return
    try:
        os.chown(root, SANDBOX_UID, SANDBOX_GID)
        for path in root.rglob("*"):
            try:
                os.chown(path, SANDBOX_UID, SANDBOX_GID, follow_symlinks=False)
            except OSError:
                continue
    except OSError:
        # Не критично: запуск продолжится, а проблемы с записью покажет вывод теста.
        pass


async def run_in_sandbox(
    project_path: Path,
    script: str,
    *,
    language: str,
    network: bool = False,
    timeout: int | None = None,
    executor: CommandExecutor | None = None,
) -> SandboxResult:
    """Выполняет shell-скрипт внутри временного контейнера с монтированным проектом."""
    image = sandbox_image(language)
    timeout = timeout if timeout is not None else settings.sandbox_timeout_seconds

    executor = executor or CommandExecutor(
        timeout=timeout + EXECUTOR_TIMEOUT_SLACK_SECONDS,
        max_output_size=settings.max_output_size,
    )

    if not await image_exists(image, executor):
        raise SandboxImageMissingError(
            f"Sandbox-образ {image} не найден. Соберите его: "
            f"docker build -f sandbox/{language}.Dockerfile -t {image} sandbox/ (см. README)."
        )

    await asyncio.to_thread(_chown_tree_for_sandbox, project_path)

    container_name = f"{CONTAINER_NAME_PREFIX}{secrets.token_hex(8)}"
    args = [
        "run",
        "--rm",
        "--name", container_name,
        "--memory", settings.sandbox_memory_limit,
        "--cpus", settings.sandbox_cpu_limit,
        "--network", "bridge" if network else "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", f"{SANDBOX_UID}:{SANDBOX_GID}",
        "--volume", f"{project_path.resolve()}:/workspace",
        "--workdir", "/workspace",
        image,
        "/bin/sh", "-c", script,
    ]

    result: CommandResult = await executor.run("docker", args)

    if result.timed_out:
        # CLI docker убит по таймауту, но контейнер может ещё жить — снимаем принудительно.
        cleanup = CommandExecutor(timeout=30)
        await cleanup.run("docker", ["rm", "-f", container_name])

    return SandboxResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
        output_truncated=result.stdout_truncated or result.stderr_truncated,
    )


def format_sandbox_result(result: SandboxResult, *, context: str) -> str:
    parts = [f"{context}: exit_code={result.exit_code}"]
    if result.timed_out:
        parts.append("⏱ Превышен таймаут — контейнер уничтожен.")
    output = (result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")).strip()
    if output:
        parts.append(output)
    else:
        parts.append("(пустой вывод)")
    if result.output_truncated:
        parts.append("[вывод обрезан по лимиту]")
    return "\n".join(parts)
