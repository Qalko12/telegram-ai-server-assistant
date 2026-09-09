"""AI-инструменты управления VPN через внутренний admin API vpn-bot.

Алиса управляет VPN-ботом: показывает пользователей, одобряет заявки,
продлевает/отключает доступ, сбрасывает трафик.

Безопасность:
  - запросы идут на http://172.17.0.1:8090 (docker-мост), порт закрыт iptables
    для внешнего мира;
  - каждый запрос требует X-Admin-Token (shared secret из .env);
  - все действия уровня MODERATE/CRITICAL — через confirmation оператору;
  - ответы API оборачиваются в untrusted общим механизмом agent_loop.
"""

import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from app.config import settings
from security.levels import SecurityLevel

logger = logging.getLogger(__name__)

VPN_API_TIMEOUT = 20.0


class VpnApiError(Exception):
    pass


async def _vpn_request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Запрос к admin API vpn-bot с shared-secret токеном."""
    base = settings.vpn_admin_api_url.rstrip("/")
    token = settings.vpn_admin_api_token
    if not token:
        raise VpnApiError(
            "VPN_ADMIN_API_TOKEN не настроен в .env — управление VPN недоступно."
        )

    headers = {"X-Admin-Token": token}
    try:
        async with httpx.AsyncClient(timeout=VPN_API_TIMEOUT) as client:
            response = await client.request(
                method, f"{base}{path}", headers=headers, json=json_body, params=params
            )
    except httpx.HTTPError as exc:
        raise VpnApiError(f"VPN API недоступен: {exc}") from exc

    if response.status_code == 403:
        raise VpnApiError("VPN API отклонил токен (403). Проверь VPN_ADMIN_API_TOKEN.")
    if response.status_code == 503:
        raise VpnApiError("VPN API не настроен (503): у vpn-bot пуст ADMIN_API_TOKEN.")

    try:
        data = response.json()
    except Exception:
        raise VpnApiError(f"VPN API вернул не-JSON (HTTP {response.status_code})")

    if isinstance(data, dict) and data.get("ok") is False:
        raise VpnApiError(f"VPN API: {data.get('error') or f'HTTP {response.status_code}'}")
    return data if isinstance(data, dict) else {"result": data}


# ---------------- параметры ----------------


class VpnStatsParams(BaseModel):
    pass


class VpnListUsersParams(BaseModel):
    with_panel: bool = Field(
        default=True, description="Подтянуть данные о трафике из панели 3x-ui (медленнее, но полнее)."
    )


class VpnUserParams(BaseModel):
    telegram_id: int = Field(description="Telegram ID пользователя VPN-бота.")


class VpnGrantParams(BaseModel):
    telegram_id: int = Field(description="Telegram ID пользователя.")
    days: int = Field(description="Сколько дней добавить к сроку доступа (1..3650).", ge=1, le=3650)


class VpnRevokeParams(BaseModel):
    telegram_id: int = Field(description="Telegram ID пользователя, которому отключить доступ.")


class VpnResetTrafficParams(BaseModel):
    telegram_id: int = Field(description="Telegram ID пользователя, которому сбросить счётчик трафика.")


class VpnListRequestsParams(BaseModel):
    pass


class VpnDecideRequestParams(BaseModel):
    request_id: int = Field(description="ID заявки (из list_vpn_requests).")
    action: Literal["approve", "reject"] = Field(description="approve — одобрить, reject — отклонить.")


class VpnAuditParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Сколько последних записей аудита показать.")


# ---------------- handlers ----------------


async def handle_vpn_stats(params: VpnStatsParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request("GET", "/api/vpn/stats")
    panel = data.get("panel") or {}

    lines = [
        "📊 Статистика VPN:",
        f"• пользователей бота: {data.get('bot_users', 0)}",
        f"• активных: {data.get('active_users', 0)}",
        f"• заработано Stars: {data.get('total_stars_earned', 0)}⭐",
        f"• клиентов в панели: {panel.get('panel_clients', '?')}",
        f"• онлайн за 5 мин: {panel.get('online_last_5min', '?')}",
        f"• inbound'ов: {panel.get('inbounds', '?')}",
    ]
    prices = data.get("prices") or {}
    if prices:
        lines.append(
            f"• тарифы: 1 мес = {prices.get('month_stars')}⭐, "
            f"3 мес = {prices.get('quarter_stars')}⭐"
        )
    if panel.get("error"):
        lines.append(f"⚠️ панель: {panel['error']}")
    return "\n".join(lines)


async def handle_vpn_list_users(params: VpnListUsersParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request(
        "GET", "/api/vpn/users", params={"panel": "1" if params.with_panel else "0"}
    )
    users = data.get("users") or []
    if not users:
        return f"Пользователей нет (всего: {data.get('count', 0)})."

    lines = [f"👥 Пользователи VPN ({data.get('count', len(users))}):"]
    for user in users[:40]:
        name = user.get("first_name") or user.get("username") or "—"
        handle = f"@{user.get('username')}" if user.get("username") else ""
        status = user.get("status", "?")
        expires = (user.get("expires_at") or "—")[:10]

        panel = user.get("panel") or {}
        if panel:
            mark = "⛔" if not panel.get("enabled") else ("⌛" if panel.get("expired") else "🟢")
            traffic = f" | {panel.get('used_gb', 0)} ГБ"
        else:
            mark = "⚪"
            traffic = ""

        lines.append(
            f"{mark} {name} {handle} | tg{user.get('telegram_id')} | {status} | до {expires}{traffic}"
        )
    if len(users) > 40:
        lines.append(f"…и ещё {len(users) - 40}")
    return "\n".join(lines)


async def handle_vpn_get_user(params: VpnUserParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request("GET", f"/api/vpn/users/{params.telegram_id}")
    user = data.get("user") or {}
    panel = user.get("panel") or {}

    lines = [
        f"👤 Пользователь tg{user.get('telegram_id')}",
        f"• имя: {user.get('first_name') or '—'}",
        f"• username: {user.get('username') or '—'}",
        f"• статус: {user.get('status')}",
        f"• клиент панели: {user.get('panel_email') or 'нет'}",
        f"• действует до: {user.get('expires_at') or '—'}",
        f"• лимит трафика: {'безлимит' if not user.get('traffic_limit_gb') else str(user.get('traffic_limit_gb')) + ' ГБ'}",
    ]
    if panel:
        lines.extend(
            [
                f"• включён в панели: {'да' if panel.get('enabled') else 'НЕТ'}",
                f"• истёк: {'да' if panel.get('expired') else 'нет'}",
                f"• трафик: ⬆️{panel.get('uploaded_gb', 0)} / ⬇️{panel.get('downloaded_gb', 0)} ГБ",
                f"• последняя активность: {panel.get('last_online') or '—'}",
            ]
        )
    payments = data.get("payments") or []
    if payments:
        lines.append("• платежи:")
        for payment in payments[:5]:
            lines.append(
                f"   - {payment.get('stars')}⭐ за {payment.get('plan')} "
                f"(+{payment.get('days_granted')} дн.) {(payment.get('created_at') or '')[:10]}"
            )
    return "\n".join(lines)


async def handle_vpn_grant(params: VpnGrantParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request(
        "POST",
        f"/api/vpn/users/{params.telegram_id}/grant",
        json_body={"days": params.days, "actor_telegram_id": ctx.telegram_user_id},
    )
    return (
        f"✅ Доступ tg{params.telegram_id} продлён на {params.days} дн.\n"
        f"Действует до: {data.get('expires_at') or '—'}"
    )


async def handle_vpn_revoke(params: VpnRevokeParams, ctx: ExecutionContext) -> str:
    await _vpn_request(
        "POST",
        f"/api/vpn/users/{params.telegram_id}/revoke",
        json_body={"actor_telegram_id": ctx.telegram_user_id},
    )
    return f"⛔ Доступ tg{params.telegram_id} отключён."


async def handle_vpn_reset_traffic(params: VpnResetTrafficParams, ctx: ExecutionContext) -> str:
    await _vpn_request(
        "POST",
        f"/api/vpn/users/{params.telegram_id}/reset-traffic",
        json_body={"actor_telegram_id": ctx.telegram_user_id},
    )
    return f"🔄 Трафик tg{params.telegram_id} сброшен."


async def handle_vpn_list_requests(params: VpnListRequestsParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request("GET", "/api/vpn/requests")
    requests = data.get("requests") or []
    if not requests:
        return "📥 Заявок на доступ нет."

    lines = [f"📥 Заявки на доступ ({data.get('count', len(requests))}):"]
    for req in requests[:20]:
        name = req.get("first_name") or req.get("username") or "—"
        handle = f"@{req.get('username')}" if req.get("username") else ""
        lines.append(
            f"• #{req.get('id')} {name} {handle} | tg{req.get('telegram_id')} "
            f"| {(req.get('created_at') or '')[:16]}"
        )
        if req.get("comment"):
            lines.append(f"   «{req['comment'][:80]}»")
    lines.append(
        "\nЧтобы одобрить: vpn_decide_request(request_id=<ID>, action='approve'). "
        "Чтобы отклонить: action='reject'."
    )
    return "\n".join(lines)


async def handle_vpn_decide_request(params: VpnDecideRequestParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request(
        "POST",
        f"/api/vpn/requests/{params.request_id}",
        json_body={"action": params.action, "actor_telegram_id": ctx.telegram_user_id},
    )
    if params.action == "approve":
        email = data.get("panel_email") or "?"
        return (
            f"✅ Заявка #{params.request_id} одобрена.\n"
            f"Создан клиент: {email}\n"
            f"Действует до: {data.get('expires_at') or '—'}\n"
            "Пользователь получил ссылку для подключения."
        )
    return f"❌ Заявка #{params.request_id} отклонена."


async def handle_vpn_audit(params: VpnAuditParams, ctx: ExecutionContext) -> str:
    data = await _vpn_request("GET", "/api/vpn/audit", params={"limit": params.limit})
    entries = data.get("entries") or []
    if not entries:
        return "📜 Аудит VPN пуст."

    lines = [f"📜 Аудит VPN ({data.get('count', len(entries))}):"]
    for entry in entries[:params.limit]:
        mark = "✅" if entry.get("success") else "❌"
        target = f" → tg{entry['target']}" if entry.get("target") else ""
        lines.append(f"{mark} {(entry.get('at') or '')[:16]} {entry.get('action')}{target}")
        if entry.get("detail"):
            lines.append(f"   {entry['detail'][:120]}")
    return "\n".join(lines)


# ---------------- ToolSpec'и ----------------
# Чтение — SAFE; изменения доступа — MODERATE/CRITICAL (через confirmation).

VPN_STATS = ToolSpec(
    name="vpn_stats",
    description="Статистика VPN-сервиса: пользователи, активные, заработанные Stars, клиенты в панели, онлайн.",
    input_model=VpnStatsParams,
    handler=handle_vpn_stats,
    security_level=SecurityLevel.SAFE,
)

VPN_LIST_USERS = ToolSpec(
    name="vpn_list_users",
    description="Список пользователей VPN-бота со статусом, сроком действия и трафиком.",
    input_model=VpnListUsersParams,
    handler=handle_vpn_list_users,
    security_level=SecurityLevel.SAFE,
)

VPN_GET_USER = ToolSpec(
    name="vpn_get_user",
    description="Подробная информация о пользователе VPN по Telegram ID: статус, трафик, платежи.",
    input_model=VpnUserParams,
    handler=handle_vpn_get_user,
    security_level=SecurityLevel.SAFE,
)

VPN_LIST_REQUESTS = ToolSpec(
    name="vpn_list_requests",
    description="Список заявок на доступ к VPN, ожидающих одобрения.",
    input_model=VpnListRequestsParams,
    handler=handle_vpn_list_requests,
    security_level=SecurityLevel.SAFE,
)

VPN_AUDIT = ToolSpec(
    name="vpn_audit_log",
    description="Журнал действий VPN-бота: кто и что менял в доступе пользователей.",
    input_model=VpnAuditParams,
    handler=handle_vpn_audit,
    security_level=SecurityLevel.SAFE,
)

VPN_GRANT = ToolSpec(
    name="vpn_grant_days",
    description=(
        "Продлить доступ пользователю VPN на N дней. Меняет срок в панели 3x-ui. "
        "Требует подтверждения оператора."
    ),
    input_model=VpnGrantParams,
    handler=handle_vpn_grant,
    security_level=SecurityLevel.MODERATE,
)

VPN_RESET_TRAFFIC = ToolSpec(
    name="vpn_reset_traffic",
    description="Сбросить счётчик трафика пользователя VPN в панели 3x-ui. Требует подтверждения.",
    input_model=VpnResetTrafficParams,
    handler=handle_vpn_reset_traffic,
    security_level=SecurityLevel.MODERATE,
)

VPN_DECIDE_REQUEST = ToolSpec(
    name="vpn_decide_request",
    description=(
        "Одобрить или отклонить заявку на доступ к VPN. При approve создаётся клиент "
        "в панели с пробным периодом, пользователь получает ссылку. Требует подтверждения."
    ),
    input_model=VpnDecideRequestParams,
    handler=handle_vpn_decide_request,
    security_level=SecurityLevel.MODERATE,
)

VPN_REVOKE = ToolSpec(
    name="vpn_revoke_user",
    description=(
        "ОТКЛЮЧИТЬ доступ пользователю VPN (клиент остаётся в панели, но выключается). "
        "Необратимое для пользователя действие — требует подтверждения."
    ),
    input_model=VpnRevokeParams,
    handler=handle_vpn_revoke,
    security_level=SecurityLevel.CRITICAL,
)


def all_vpn_tools() -> tuple[ToolSpec, ...]:
    """Возвращает инструменты только если VPN API настроен.

    Без VPN_ADMIN_API_TOKEN инструменты не регистрируются — Алиса не будет
    предлагать то, что заведомо не работает.
    """
    if not settings.vpn_admin_api_token:
        return ()
    return (
        VPN_STATS,
        VPN_LIST_USERS,
        VPN_GET_USER,
        VPN_LIST_REQUESTS,
        VPN_AUDIT,
        VPN_GRANT,
        VPN_RESET_TRAFFIC,
        VPN_DECIDE_REQUEST,
        VPN_REVOKE,
    )
