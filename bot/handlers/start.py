from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from ai.memory import append_message, load_recent_messages
from ai.tools.registry import ExecutionContext
from app.di import agent_loop
from bot.agent_dispatch import deliver_outcome
from database.engine import async_session_factory

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Привет! Авторизация пройдена, я подключён к Claude AI.\n\nПиши обычным языком — что нужно сделать?"
    )


@router.message(F.text)
async def handle_text(message: Message) -> None:
    chat_id = message.chat.id
    user_text = message.text

    async with async_session_factory() as session:
        history = await load_recent_messages(session, chat_id)
        await append_message(session, chat_id, "user", user_text)

    conversation = [*history, {"role": "user", "content": user_text}]
    ctx = ExecutionContext(telegram_user_id=message.from_user.id, chat_id=chat_id)

    await message.bot.send_chat_action(chat_id, "typing")
    outcome = await agent_loop.run(conversation, ctx)

    await deliver_outcome(outcome, chat_id=chat_id, telegram_user_id=message.from_user.id, answer=message.answer)
