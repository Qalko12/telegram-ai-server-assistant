from unittest.mock import AsyncMock, patch

import httpx
import pytest

import ai.tools.web_tools as web_tools_module
from ai.tools.registry import ExecutionContext
from ai.tools.web_tools import (
    SearchParams,
    TavilyProvider,
    all_web_tools,
    get_provider,
    handle_web_search,
)


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "")


def test_provider_none_without_key() -> None:
    assert get_provider() is None


def test_tools_not_registered_without_key() -> None:
    assert all_web_tools() == ()


def test_provider_configured_with_key(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-key")
    provider = get_provider()
    assert isinstance(provider, TavilyProvider)
    assert all_web_tools() != ()


def _fake_response(payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", web_tools_module.TAVILY_SEARCH_URL)
    return httpx.Response(status, json=payload, request=request)


async def test_tavily_search_formats_results(monkeypatch) -> None:
    payload = {
        "answer": "Ошибка возникает из-за версии OpenSSL.",
        "results": [
            {"title": "Docker issue 123", "url": "https://github.com/x/y/issues/123", "content": "описание проблемы"},
            {"title": "StackOverflow", "url": "https://stackoverflow.com/q/1", "content": "решение"},
        ],
    }

    mock_post = AsyncMock(return_value=_fake_response(payload))
    with patch.object(httpx.AsyncClient, "post", mock_post):
        provider = TavilyProvider("tvly-key")
        text = await provider.search("docker openssl error", max_results=5)

    assert "Краткий ответ" in text
    assert "Docker issue 123" in text
    assert "https://github.com/x/y/issues/123" in text
    sent_payload = mock_post.await_args.kwargs["json"]
    assert sent_payload["api_key"] == "tvly-key"
    assert sent_payload["query"] == "docker openssl error"


async def test_tavily_search_no_results() -> None:
    mock_post = AsyncMock(return_value=_fake_response({"results": []}))
    with patch.object(httpx.AsyncClient, "post", mock_post):
        text = await TavilyProvider("k").search("ничего")
    assert "не дал результатов" in text


async def test_handle_web_search_without_provider() -> None:
    result = await handle_web_search(SearchParams(query="что-то"), CTX)
    assert "не сконфигурирован" in result


async def test_handle_web_search_http_error(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "tvly-key")
    request = httpx.Request("POST", web_tools_module.TAVILY_SEARCH_URL)
    response = httpx.Response(401, json={"error": "unauthorized"}, request=request)
    mock_post = AsyncMock(side_effect=httpx.HTTPStatusError("401", request=request, response=response))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await handle_web_search(SearchParams(query="q"), CTX)

    assert "HTTP 401" in result


async def test_handle_web_search_network_error(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "tvly-key")
    mock_post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch.object(httpx.AsyncClient, "post", mock_post):
        result = await handle_web_search(SearchParams(query="q"), CTX)

    assert "сетевая ошибка" in result
