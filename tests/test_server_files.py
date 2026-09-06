import sys

import pytest

from app.config import settings
from security.permissions import PathNotAllowedError
from server.files import (
    FileTooLargeError,
    NotAFileError,
    ValidationFailedError,
    create_directory,
    delete_file,
    find_file,
    list_directory,
    read_file,
    write_file,
)


@pytest.fixture(autouse=True)
def _set_allowed_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allowed_paths_raw", str(tmp_path))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "_backups"))
    return tmp_path


def test_list_directory_returns_entries(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()

    entries = list_directory(str(tmp_path))
    names = {e["name"] for e in entries}

    assert names == {"a.txt", "subdir"}


def test_list_directory_rejects_path_outside_allowed(tmp_path) -> None:
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)

    with pytest.raises(PathNotAllowedError):
        list_directory(str(outside))


def test_find_file_matches_glob(tmp_path) -> None:
    (tmp_path / "app.log").write_text("x")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "other.log").write_text("x")
    (tmp_path / "readme.txt").write_text("x")

    matches = find_file("*.log", str(tmp_path))

    assert len(matches) == 2
    assert all(m.endswith(".log") for m in matches)


def test_read_file_returns_content(tmp_path) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"key": "value"}', encoding="utf-8")

    content = read_file(str(target))

    assert content == '{"key": "value"}'


def test_read_file_rejects_directory(tmp_path) -> None:
    with pytest.raises(NotAFileError):
        read_file(str(tmp_path))


def test_read_file_rejects_too_large_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_file_size", 10)
    target = tmp_path / "big.txt"
    target.write_text("x" * 100)

    with pytest.raises(FileTooLargeError):
        read_file(str(target))


async def test_write_file_creates_new_file_without_backup(tmp_path) -> None:
    target = tmp_path / "new.txt"

    result = await write_file(str(target), "hello")

    assert target.read_text() == "hello"
    assert "не требовался" in result


async def test_write_file_backs_up_existing_file(tmp_path) -> None:
    target = tmp_path / "config.txt"
    target.write_text("old content")

    await write_file(str(target), "new content")

    assert target.read_text() == "new content"
    backups = list((tmp_path / "_backups").glob("config.txt.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "old content"


async def test_write_file_rolls_back_on_failed_validation(tmp_path) -> None:
    target = tmp_path / "config.txt"
    target.write_text("old content")

    with pytest.raises(ValidationFailedError):
        await write_file(str(target), "broken content", validate_command=[sys.executable, "-c", "import sys; sys.exit(1)"])

    assert target.read_text() == "old content"


async def test_write_file_keeps_change_on_successful_validation(tmp_path) -> None:
    target = tmp_path / "config.txt"
    target.write_text("old content")

    await write_file(str(target), "new content", validate_command=[sys.executable, "-c", "import sys; sys.exit(0)"])

    assert target.read_text() == "new content"


def test_delete_file_backs_up_before_removing(tmp_path) -> None:
    target = tmp_path / "todelete.txt"
    target.write_text("bye")

    delete_file(str(target))

    assert not target.exists()
    backups = list((tmp_path / "_backups").glob("todelete.txt.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "bye"


def test_delete_file_missing_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        delete_file(str(tmp_path / "does_not_exist.txt"))


def test_create_directory_creates_nested_path(tmp_path) -> None:
    target = tmp_path / "a" / "b" / "c"

    create_directory(str(target))

    assert target.is_dir()
