import io

from aiogram import F, Router
from aiogram.types import Message

from ai.memory import append_message, build_context
from ai.tools.registry import ExecutionContext
from ai.vision import build_image_content_block, build_text_content_block
from app.di import agent_loop
from bot.agent_dispatch import deliver_outcome
from database.engine import async_session_factory

router = Router(name="photo")


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    chat_id = message.chat.id
    caption = message.caption or "Проанализируй это изображение."

    buffer = io.BytesIO()
    await message.bot.download(message.photo[-1], destination=buffer)
    image_bytes = buffer.getvalue()

    async with async_session_factory() as session:
        await append_message(session, chat_id, "user", f"[фото] {caption}")
        conversation = await build_context(session, chat_id)

    # Последнее сообщение — только что записанный placeholder. В текущем ходе
    # заменяем его на мультимодальный контент: фото + оригинальная подпись.
    conversation[-1] = {
        "role": "user",
        "content": [build_image_content_block(image_bytes), build_text_content_block(caption)],
    }

    ctx = ExecutionContext(telegram_user_id=message.from_user.id, chat_id=chat_id)

    await message.bot.send_chat_action(chat_id, "typing")
    outcome = await agent_loop.run(conversation, ctx)

    await deliver_outcome(outcome, chat_id=chat_id, telegram_user_id=message.from_user.id, answer=message.answer)
