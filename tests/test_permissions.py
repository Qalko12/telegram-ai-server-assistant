import pytest

from app.config import settings
from security.permissions import PathNotAllowedError, ensure_path_allowed


@pytest.fixture(autouse=True)
def _set_allowed_paths(tmp_path, monkeypatch):
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    monkeypatch.setattr(settings, "allowed_paths_raw", str(allowed))
    return allowed


def test_path_inside_allowed_root_is_ok(_set_allowed_paths) -> None:
    target = _set_allowed_paths / "project" / "file.py"
    resolved = ensure_path_allowed(str(target))
    assert resolved == target.resolve()


def test_allowed_root_itself_is_ok(_set_allowed_paths) -> None:
    ensure_path_allowed(str(_set_allowed_paths))


def test_path_outside_allowed_root_is_denied(tmp_path, _set_allowed_paths) -> None:
    outside = tmp_path / "elsewhere" / "file.py"
    with pytest.raises(PathNotAllowedError):
        ensure_path_allowed(str(outside))


def test_path_traversal_escaping_allowed_root_is_denied(_set_allowed_paths) -> None:
    escaping = _set_allowed_paths / ".." / "outside.py"
    with pytest.raises(PathNotAllowedError):
        ensure_path_allowed(str(escaping))


def test_blocked_ssh_path_is_denied_even_inside_allowed_root(_set_allowed_paths) -> None:
    ssh_path = _set_allowed_paths / ".ssh" / "id_rsa"
    with pytest.raises(PathNotAllowedError):
        ensure_path_allowed(str(ssh_path))
