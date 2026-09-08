import io

from aiogram import F, Router
from aiogram.types import Message

from ai.memory import append_message, load_recent_messages
from ai.prompts import wrap_untrusted
from ai.tools.registry import ExecutionContext
from app.di import agent_loop
from bot.agent_dispatch import deliver_outcome
from database.engine import async_session_factory
from media.documents import UnsupportedDocumentTypeError, parse_document

router = Router(name="document")


@router.message(F.document)
async def handle_document(message: Message) -> None:
    chat_id = message.chat.id
    filename = message.document.file_name or "file"
    caption = message.caption or f"Проанализируй этот файл: {filename}"

    buffer = io.BytesIO()
    await message.bot.download(message.document, destination=buffer)
    content_bytes = buffer.getvalue()

    try:
        parsed_text = parse_document(filename, content_bytes)
    except UnsupportedDocumentTypeError:
        await message.answer(f"Формат файла «{filename}» пока не поддерживается.")
        return

    wrapped = wrap_untrusted(f"document:{filename}", parsed_text)

    async with async_session_factory() as session:
        history = await load_recent_messages(session, chat_id)
        await append_message(session, chat_id, "user", f"[документ {filename}] {caption}")

    user_text = f"{caption}\n\n{wrapped}"
    conversation = [*history, {"role": "user", "content": user_text}]
    ctx = ExecutionContext(telegram_user_id=message.from_user.id, chat_id=chat_id)

    await message.bot.send_chat_action(chat_id, "typing")
    outcome = await agent_loop.run(conversation, ctx)

    await deliver_outcome(outcome, chat_id=chat_id, telegram_user_id=message.from_user.id, answer=message.answer)
