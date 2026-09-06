from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from ai.agent_loop import AgentLoop
from ai.memory import append_message, load_recent_messages
from ai.tools.registry import ExecutionContext
from app.di import build_tool_registry
from database.engine import async_session_factory

router = Router(name="start")

_agent_loop = AgentLoop(build_tool_registry())


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
    reply_text = await _agent_loop.run(conversation, ctx)

    async with async_session_factory() as session:
        await append_message(session, chat_id, "assistant", reply_text)

    await message.answer(reply_text)
