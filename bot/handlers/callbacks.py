import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ai.agent_loop import AgentConfirmationNeeded
from ai.prompts import wrap_untrusted
from ai.tools.registry import ExecutionContext
from app.di import agent_loop
from audit.logger import AuditLogger
from bot.agent_dispatch import deliver_outcome
from database.engine import async_session_factory
from security.confirmations import ConfirmationError, ConfirmationService

logger = logging.getLogger(__name__)

router = Router(name="confirmations")

ActionExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]

_action_executors: dict[str, ActionExecutor] = {}

_ERROR_MESSAGES = {
    "not_found": "Действие не найдено.",
    "wrong_user": "Это не твоё подтверждение.",
    "not_pending": "Подтверждение уже обработано или истекло.",
    "race_lost": "Кто-то уже нажал раньше.",
}


def register_action_executor(tool_name: str, executor: ActionExecutor) -> None:
    _action_executors[tool_name] = executor


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm(callback: CallbackQuery) -> None:
    action_id = callback.data.split(":", 1)[1]
    await _resolve(callback, action_id, "APPROVED")


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel(callback: CallbackQuery) -> None:
    action_id = callback.data.split(":", 1)[1]
    await _resolve(callback, action_id, "DENIED")


async def _resolve(callback: CallbackQuery, action_id: str, new_status: str) -> None:
    async with async_session_factory() as session:
        service = ConfirmationService(session)
        try:
            confirmation = await service.resolve(action_id, callback.from_user.id, new_status)
        except ConfirmationError as exc:
            await callback.answer(_ERROR_MESSAGES.get(str(exc), "Ошибка подтверждения."), show_alert=True)
            return

    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)

    approved = new_status == "APPROVED"
    await callback.answer("Подтверждено, выполняю..." if approved else "Отменено.")

    if isinstance(confirmation.agent_session_snapshot, dict) and "snapshot" in confirmation.agent_session_snapshot:
        await _resolve_agent_loop_confirmation(callback, confirmation, approved=approved)
        return

    if not approved:
        if callback.message is not None:
            await callback.message.answer("❌ Действие отменено.")
        await _audit(
            confirmation.telegram_user_id,
            confirmation.tool_name,
            confirmation.arguments,
            success=False,
            error="denied_by_user",
        )
        return

    executor = _action_executors.get(confirmation.tool_name)
    if executor is None:
        if callback.message is not None:
            await callback.message.answer(
                f"⚠️ Подтверждено, но для инструмента «{confirmation.tool_name}» ещё нет обработчика."
            )
        await _audit(
            confirmation.telegram_user_id,
            confirmation.tool_name,
            confirmation.arguments,
            success=False,
            error="no_executor_registered",
        )
        return

    started_at = time.monotonic()
    try:
        result_text = await executor(confirmation.action_id, confirmation.arguments)
    except Exception as exc:
        logger.exception("Action executor failed for %s", confirmation.tool_name)
        if callback.message is not None:
            await callback.message.answer(f"❌ Ошибка выполнения: {exc}")
        await _audit(
            confirmation.telegram_user_id,
            confirmation.tool_name,
            confirmation.arguments,
            success=False,
            error=str(exc),
            execution_time_ms=(time.monotonic() - started_at) * 1000,
        )
        return

    if callback.message is not None:
        await callback.message.answer(result_text)

    await _audit(
        confirmation.telegram_user_id,
        confirmation.tool_name,
        confirmation.arguments,
        success=True,
        result=result_text,
        execution_time_ms=(time.monotonic() - started_at) * 1000,
    )


async def _resolve_agent_loop_confirmation(callback: CallbackQuery, confirmation: Any, *, approved: bool) -> None:
    snap = confirmation.agent_session_snapshot
    pending = AgentConfirmationNeeded(
        tool_use_id=snap["tool_use_id"],
        tool_name=confirmation.tool_name,
        arguments=confirmation.arguments,
        reason=confirmation.reason,
        snapshot=snap["snapshot"],
        pending_tool_results=snap["pending_tool_results"],
    )
    ctx = ExecutionContext(telegram_user_id=confirmation.telegram_user_id, chat_id=confirmation.chat_id)

    started_at = time.monotonic()

    if not approved:
        outcome = await agent_loop.resume(pending, "Пользователь отклонил это действие.", is_error=True, ctx=ctx)
        await _audit(
            confirmation.telegram_user_id,
            confirmation.tool_name,
            confirmation.arguments,
            success=False,
            error="denied_by_user",
            execution_time_ms=(time.monotonic() - started_at) * 1000,
        )
    else:
        spec = agent_loop.registry.get(confirmation.tool_name)
        if spec is None:
            outcome = await agent_loop.resume(
                pending, f"Unknown tool: {confirmation.tool_name}", is_error=True, ctx=ctx
            )
            await _audit(
                confirmation.telegram_user_id,
                confirmation.tool_name,
                confirmation.arguments,
                success=False,
                error="unknown_tool",
            )
        else:
            try:
                params = spec.input_model.model_validate(confirmation.arguments)
                result_text = await spec.handler(params, ctx)
            except Exception as exc:
                logger.exception("Tool %s failed after confirmation", confirmation.tool_name)
                outcome = await agent_loop.resume(pending, str(exc), is_error=True, ctx=ctx)
                await _audit(
                    confirmation.telegram_user_id,
                    confirmation.tool_name,
                    confirmation.arguments,
                    success=False,
                    error=str(exc),
                    execution_time_ms=(time.monotonic() - started_at) * 1000,
                )
            else:
                wrapped = wrap_untrusted(confirmation.tool_name, result_text)
                outcome = await agent_loop.resume(pending, wrapped, is_error=False, ctx=ctx)
                await _audit(
                    confirmation.telegram_user_id,
                    confirmation.tool_name,
                    confirmation.arguments,
                    success=True,
                    result=result_text,
                    execution_time_ms=(time.monotonic() - started_at) * 1000,
                )

    if callback.message is not None:
        await deliver_outcome(
            outcome,
            chat_id=confirmation.chat_id,
            telegram_user_id=confirmation.telegram_user_id,
            answer=callback.message.answer,
            message=callback.message,
        )


async def _audit(
    telegram_user_id: int,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    success: bool,
    result: str | None = None,
    error: str | None = None,
    execution_time_ms: float | None = None,
) -> None:
    async with async_session_factory() as session:
        await AuditLogger(session).log(
            telegram_user_id=telegram_user_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            error=error,
            success=success,
            execution_time_ms=execution_time_ms,
        )
