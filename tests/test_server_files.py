import pytest

from app.config import settings
from security.permissions import PathNotAllowedError
from server.files import FileTooLargeError, NotAFileError, find_file, list_directory, read_file


@pytest.fixture(autouse=True)
def _set_allowed_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allowed_paths_raw", str(tmp_path))
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
