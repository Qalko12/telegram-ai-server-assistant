import sys

from server.executor import CommandExecutor

PYTHON = sys.executable


async def test_successful_command_captures_stdout() -> None:
    executor = CommandExecutor(timeout=5, max_output_size=10_000)
    result = await executor.run(PYTHON, ["-c", "print('hello')"])

    assert result.success is True
    assert result.exit_code == 0
    assert "hello" in result.stdout


async def test_nonzero_exit_code_is_reported() -> None:
    executor = CommandExecutor(timeout=5, max_output_size=10_000)
    result = await executor.run(PYTHON, ["-c", "import sys; sys.exit(3)"])

    assert result.success is False
    assert result.exit_code == 3


async def test_timeout_kills_process() -> None:
    executor = CommandExecutor(timeout=0.3, max_output_size=10_000)
    result = await executor.run(PYTHON, ["-c", "import time; time.sleep(5)"])

    assert result.timed_out is True
    assert result.success is False


async def test_output_is_truncated_to_max_size() -> None:
    executor = CommandExecutor(timeout=5, max_output_size=10)
    result = await executor.run(PYTHON, ["-c", "print('x' * 1000)"])

    assert result.stdout_truncated is True
    assert len(result.stdout) == 10


async def test_missing_program_does_not_raise() -> None:
    executor = CommandExecutor(timeout=5, max_output_size=10_000)
    result = await executor.run("this_binary_does_not_exist_xyz")

    assert result.exit_code == -1
    assert result.stderr != ""
