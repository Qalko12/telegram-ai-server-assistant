import asyncio
from dataclasses import dataclass

from app.config import settings
from security.validator import validate_command


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


async def _drain(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False

    collected = bytearray()
    truncated = False

    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if len(collected) < limit:
            collected.extend(chunk[: limit - len(collected)])
        if len(collected) >= limit:
            truncated = True

    return bytes(collected), truncated


class CommandExecutor:
    def __init__(self, timeout: float | None = None, max_output_size: int | None = None) -> None:
        self._timeout = timeout if timeout is not None else settings.max_command_timeout
        self._max_output_size = max_output_size if max_output_size is not None else settings.max_output_size

    async def run(self, program: str, args: list[str] | None = None, *, cwd: str | None = None) -> CommandResult:
        args = args or []

        # Deny-list проверка на КАЖДЫЙ вызов — внутри executor, а не снаружи.
        # Это гарантирует, что ни один модуль (git, docker, sandbox и т.д.) не обойдёт защиту.
        validate_command(program, args)

        try:
            process = await asyncio.create_subprocess_exec(
                program,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except (FileNotFoundError, PermissionError) as exc:
            return CommandResult(exit_code=-1, stdout="", stderr=str(exc), timed_out=False)

        async def _run() -> tuple[bytes, bool, bytes, bool]:
            stdout_task = asyncio.create_task(_drain(process.stdout, self._max_output_size))
            stderr_task = asyncio.create_task(_drain(process.stderr, self._max_output_size))
            stdout_bytes, stdout_trunc = await stdout_task
            stderr_bytes, stderr_trunc = await stderr_task
            await process.wait()
            return stdout_bytes, stdout_trunc, stderr_bytes, stderr_trunc

        try:
            stdout_bytes, stdout_trunc, stderr_bytes, stderr_trunc = await asyncio.wait_for(
                _run(), timeout=self._timeout
            )
            timed_out = False
        except asyncio.TimeoutError:
            # Сначала мягко просим завершиться (SIGTERM), потом принудительно (SIGKILL).
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

            # Читаем что успело напечататься перед таймаутом (не теряем диагностику).
            stdout_bytes = await process.stdout.read() if process.stdout else b""
            stderr_bytes = await process.stderr.read() if process.stderr else b""
            stdout_trunc = stderr_trunc = False
            timed_out = True

        return CommandResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            timed_out=timed_out,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
        )
