import pytest

from security.validator import CommandDeniedError, validate_command


def test_safe_command_passes() -> None:
    validate_command("systemctl", ["restart", "nginx"])


@pytest.mark.parametrize(
    ("program", "args"),
    [
        ("rm", ["-rf", "/"]),
        ("rm", ["-fr", "/"]),
        ("mkfs.ext4", ["/dev/sda1"]),
        ("dd", ["if=/dev/zero", "of=/dev/sda"]),
        ("docker", ["system", "prune", "-a"]),
    ],
)
def test_destructive_commands_are_denied(program: str, args: list[str]) -> None:
    with pytest.raises(CommandDeniedError):
        validate_command(program, args)


def test_rm_rf_on_subdirectory_is_allowed() -> None:
    validate_command("rm", ["-rf", "/opt/ai-workspace/project1"])
