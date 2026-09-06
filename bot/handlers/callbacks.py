import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from audit.logger import AuditLogger
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

    if new_status == "DENIED":
        await callback.answer("Отменено.")
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

    await callback.answer("Подтверждено, выполняю...")

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
