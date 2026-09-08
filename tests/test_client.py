import pytest

import ai.client as client_module
from ai.client import get_client, reset_client


@pytest.fixture(autouse=True)
def _fresh_client():
    reset_client()
    yield
    reset_client()


def test_default_points_to_official_api(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_base_url", "")

    client = get_client()

    assert "api.anthropic.com" in str(client.base_url)


def test_custom_base_url_is_applied(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_base_url", "https://proxy.example.com")

    client = get_client()

    assert str(client.base_url).startswith("https://proxy.example.com")


def test_base_url_trailing_slash_stripped(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_base_url", "https://proxy.example.com/")

    client = get_client()

    assert "proxy.example.com" in str(client.base_url)
    assert not str(client.base_url).endswith("//v1")


def test_client_is_cached(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_base_url", "")

    assert get_client() is get_client()

    reset_client()
    assert get_client() is not None


def test_http_base_url_logs_warning(monkeypatch, caplog) -> None:
    import logging

    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_base_url", "http://insecure.example.com:4100")

    with caplog.at_level(logging.WARNING):
        client = get_client()

    assert "insecure.example.com" in str(client.base_url)
    assert "незащищённый HTTP" in caplog.text
