"""Тесты VPN-инструментов Алисы: форматирование, уровни безопасности, обработка ошибок."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import ai.tools.vpn_tools as vpn_tools_module
from ai.tools.registry import ExecutionContext
from ai.tools.vpn_tools import (
    VPN_DECIDE_REQUEST,
    VPN_GRANT,
    VPN_LIST_REQUESTS,
    VPN_REVOKE,
    VpnDecideRequestParams,
    VpnGrantParams,
    VpnListRequestsParams,
    VpnListUsersParams,
    VpnRevokeParams,
    VpnStatsParams,
    VpnUserParams,
    _vpn_request,
    all_vpn_tools,
    handle_vpn_decide_request,
    handle_vpn_grant,
    handle_vpn_list_requests,
    handle_vpn_list_users,
    handle_vpn_revoke,
    handle_vpn_stats,
)
from security.levels import SecurityLevel

CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


def _resp(status: int, json_data=None):
    request = httpx.Request("GET", "http://test")
    return httpx.Response(status, json=json_data, request=request)


# ---------- уровни безопасности ----------


def test_security_levels():
    """Чтение — SAFE, изменения доступа — MODERATE/CRITICAL."""
    assert VPN_LIST_REQUESTS.security_level == SecurityLevel.SAFE
    assert VPN_GRANT.security_level == SecurityLevel.MODERATE
    assert VPN_DECIDE_REQUEST.security_level == SecurityLevel.MODERATE
    assert VPN_REVOKE.security_level == SecurityLevel.CRITICAL


def test_all_vpn_tools_disabled_without_token(monkeypatch):
    """Без токена инструменты НЕ регистрируются (fail closed)."""
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "")
    assert all_vpn_tools() == ()


def test_all_vpn_tools_enabled_with_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")
    tools = all_vpn_tools()
    names = {t.name for t in tools}
    assert "vpn_stats" in names
    assert "vpn_list_users" in names
    assert "vpn_revoke_user" in names
    assert len(tools) == 9


# ---------- _vpn_request ----------


async def test_request_without_token_raises(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "")
    with pytest.raises(vpn_tools_module.VpnApiError, match="VPN_ADMIN_API_TOKEN не настроен"):
        await _vpn_request("GET", "/api/vpn/stats")


async def test_request_403(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")
    mock_post = AsyncMock(return_value=_resp(403, {"ok": False, "error": "Forbidden"}))
    with patch.object(httpx.AsyncClient, "request", mock_post):
        with pytest.raises(vpn_tools_module.VpnApiError, match="403"):
            await _vpn_request("GET", "/api/vpn/stats")


async def test_request_503_fail_closed(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")
    mock = AsyncMock(return_value=_resp(503, {"ok": False, "error": "not configured"}))
    with patch.object(httpx.AsyncClient, "request", mock):
        with pytest.raises(vpn_tools_module.VpnApiError, match="503"):
            await _vpn_request("GET", "/api/vpn/stats")


async def test_request_business_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")
    mock = AsyncMock(return_value=_resp(404, {"ok": False, "error": "Пользователь не найден"}))
    with patch.object(httpx.AsyncClient, "request", mock):
        with pytest.raises(vpn_tools_module.VpnApiError, match="Пользователь не найден"):
            await _vpn_request("GET", "/api/vpn/users/999")


async def test_request_network_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")
    mock = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with patch.object(httpx.AsyncClient, "request", mock):
        with pytest.raises(vpn_tools_module.VpnApiError, match="недоступен"):
            await _vpn_request("GET", "/api/vpn/stats")


async def test_request_sends_token_header(monkeypatch):
    """Токен обязан уходить в заголовке X-Admin-Token."""
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret-token-123")
    mock = AsyncMock(return_value=_resp(200, {"ok": True}))
    with patch.object(httpx.AsyncClient, "request", mock):
        await _vpn_request("GET", "/api/vpn/stats")

    headers = mock.await_args.kwargs["headers"]
    assert headers["X-Admin-Token"] == "secret-token-123"


# ---------- handle_vpn_stats ----------


async def test_stats_formatting():
    payload = {
        "ok": True,
        "bot_users": 5,
        "active_users": 3,
        "total_stars_earned": 900,
        "panel": {"inbounds": 1, "panel_clients": 4, "online_last_5min": 2},
        "prices": {"month_stars": 300, "quarter_stars": 800},
    }
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_stats(VpnStatsParams(), CTX)

    assert "5" in text and "900" in text
    assert "online" in text.lower() or "онлайн" in text.lower()
    assert "300" in text and "800" in text


async def test_stats_shows_panel_error():
    payload = {"ok": True, "bot_users": 0, "active_users": 0, "total_stars_earned": 0,
               "panel": {"error": "панель лежит"}}
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_stats(VpnStatsParams(), CTX)
    assert "панель лежит" in text


# ---------- handle_vpn_list_users ----------


async def test_list_users_formatting():
    payload = {
        "ok": True,
        "count": 2,
        "users": [
            {
                "telegram_id": 111, "username": "ivan", "first_name": "Ivan",
                "status": "paid", "expires_at": "2026-10-01T12:00:00+00:00",
                "panel": {"enabled": True, "expired": False, "used_gb": 12.5},
            },
            {
                "telegram_id": 222, "username": None, "first_name": "Ann",
                "status": "revoked", "expires_at": None,
                "panel": {"enabled": False, "expired": False, "used_gb": 1.0},
            },
        ],
    }
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_list_users(VpnListUsersParams(), CTX)

    assert "@ivan" in text
    assert "tg111" in text
    assert "2026-10-01" in text
    assert "12.5" in text
    assert "⛔" in text  # отключённый пользователь


async def test_list_users_empty():
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value={"ok": True, "count": 0, "users": []})):
        text = await handle_vpn_list_users(VpnListUsersParams(), CTX)
    assert "нет" in text.lower()


# ---------- handle_vpn_grant ----------


async def test_grant_sends_actor_id():
    """Алиса передаёт telegram_id оператора для аудита."""
    mock = AsyncMock(return_value={"ok": True, "expires_at": "2026-10-01T00:00:00+00:00"})
    with patch.object(vpn_tools_module, "_vpn_request", mock):
        text = await handle_vpn_grant(VpnGrantParams(telegram_id=111, days=7), CTX)

    assert "продлён" in text.lower()
    body = mock.await_args.kwargs["json_body"]
    assert body["days"] == 7
    assert body["actor_telegram_id"] == 42


# ---------- handle_vpn_revoke ----------


async def test_revoke_calls_api():
    mock = AsyncMock(return_value={"ok": True, "result": "revoked"})
    with patch.object(vpn_tools_module, "_vpn_request", mock):
        text = await handle_vpn_revoke(VpnRevokeParams(telegram_id=111), CTX)

    assert "отключён" in text.lower()
    assert mock.await_args.args[0] == "POST"
    assert "/revoke" in mock.await_args.args[1]


# ---------- handle_vpn_list_requests ----------


async def test_list_requests_formatting():
    payload = {
        "ok": True, "count": 1,
        "requests": [{
            "id": 7, "telegram_id": 333, "username": "petr",
            "first_name": "Petr", "comment": "нужен vpn",
            "created_at": "2026-09-09T10:00:00+00:00",
        }],
    }
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_list_requests(VpnListRequestsParams(), CTX)

    assert "#7" in text
    assert "@petr" in text
    assert "нужен vpn" in text
    # Подсказка обязана называть РЕАЛЬНОЕ имя инструмента, иначе Claude вызовет несуществующий
    assert "vpn_decide_request" in text
    assert "approve_vpn_request" not in text


async def test_list_requests_empty():
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value={"ok": True, "count": 0, "requests": []})):
        text = await handle_vpn_list_requests(VpnListRequestsParams(), CTX)
    assert "нет" in text.lower()


# ---------- handle_vpn_decide_request ----------


async def test_decide_approve():
    payload = {"ok": True, "result": "approved", "panel_email": "ivanabc",
               "expires_at": "2026-09-12T00:00:00+00:00"}
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_decide_request(
            VpnDecideRequestParams(request_id=7, action="approve"), CTX
        )

    assert "одобрена" in text.lower()
    assert "ivanabc" in text


async def test_decide_reject():
    payload = {"ok": True, "result": "rejected"}
    with patch.object(vpn_tools_module, "_vpn_request", AsyncMock(return_value=payload)):
        text = await handle_vpn_decide_request(
            VpnDecideRequestParams(request_id=7, action="reject"), CTX
        )

    assert "отклонена" in text.lower()


async def test_decide_action_validated_by_pydantic():
    """Только approve/reject — защита от произвольных значений."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VpnDecideRequestParams(request_id=1, action="delete")


async def test_grant_days_bounds_validated():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VpnGrantParams(telegram_id=1, days=0)
    with pytest.raises(ValidationError):
        VpnGrantParams(telegram_id=1, days=10000)


# ---------- регистрация в DI ----------


def test_vpn_tools_in_di_registry(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "secret")

    from app.di import build_tool_registry

    registry = build_tool_registry()
    names = {t["name"] for t in registry.to_anthropic_tools()}
    assert "vpn_stats" in names
    assert "vpn_revoke_user" in names


def test_vpn_tools_absent_in_di_registry_without_token(monkeypatch):
    """Без токена Алиса не должна видеть VPN-инструменты вообще."""
    from app.config import settings

    monkeypatch.setattr(settings, "vpn_admin_api_token", "")

    from app.di import build_tool_registry

    registry = build_tool_registry()
    names = {t["name"] for t in registry.to_anthropic_tools()}
    assert "vpn_stats" not in names
    assert "vpn_revoke_user" not in names
