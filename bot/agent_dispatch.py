from collections.abc import Awaitable, Callable

from aiogram.types import InlineKeyboardMarkup, Message

from ai.agent_loop import AgentConfirmationNeeded, AgentFinalAnswer, AgentOutcome
from ai.memory import append_message, record_user_and_build_context
from ai.tools.registry import ExecutionContext
from app.di import agent_loop
from bot.keyboards.confirmation import build_confirmation_keyboard
from database.engine import async_session_factory
from security.confirmations import ConfirmationRequest, ConfirmationService

Answer = Callable[..., Awaitable[None]]


async def process_user_message(message: Message, user_text: str) -> None:
    """Полный цикл текстового хода: запись в память → контекст → агент → доставка ответа."""
    chat_id = message.chat.id

    async with async_session_factory() as session:
        conversation = await record_user_and_build_context(session, chat_id, user_text)

    ctx = ExecutionContext(telegram_user_id=message.from_user.id, chat_id=chat_id)

    await message.bot.send_chat_action(chat_id, "typing")
    outcome = await agent_loop.run(conversation, ctx)

    await deliver_outcome(outcome, chat_id=chat_id, telegram_user_id=message.from_user.id, answer=message.answer)


async def deliver_outcome(outcome: AgentOutcome, *, chat_id: int, telegram_user_id: int, answer: Answer) -> None:
    if isinstance(outcome, AgentFinalAnswer):
        async with async_session_factory() as session:
            await append_message(session, chat_id, "assistant", outcome.text)
        await answer(outcome.text)
        return

    await _request_confirmation(outcome, chat_id=chat_id, telegram_user_id=telegram_user_id, answer=answer)


async def _request_confirmation(
    outcome: AgentConfirmationNeeded, *, chat_id: int, telegram_user_id: int, answer: Answer
) -> None:
    async with async_session_factory() as session:
        confirmation = await ConfirmationService(session).create(
            ConfirmationRequest(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                tool_name=outcome.tool_name,
                arguments=outcome.arguments,
                reason=outcome.reason,
                agent_session_snapshot={
                    "snapshot": outcome.snapshot,
                    "pending_tool_results": outcome.pending_tool_results,
                    "tool_use_id": outcome.tool_use_id,
                },
            )
        )

    text = (
        "⚠️ ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ\n\n"
        f"Действие:\n{confirmation.tool_name}({confirmation.arguments})\n\n"
        f"Причина:\n{confirmation.reason}\n\nВыполнить?"
    )
    keyboard: InlineKeyboardMarkup = build_confirmation_keyboard(confirmation.action_id)
    await answer(text, reply_markup=keyboard)
