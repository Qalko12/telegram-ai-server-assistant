"""Доставка длинных ответов (ТЗ §39).

Telegram ограничивает сообщение 4096 символами. Короткие ответы отправляем как есть;
длинные — режем на части по границам строк. Совсем большой вывод (логи, диффы)
дополнительно дублируем текстовым файлом, чтобы его было удобно переслать/сохранить.
"""

import io
import logging
from collections.abc import Awaitable, Callable

from aiogram.types import Message

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
# Ответы длиннее этого — отправляем и кусками, и файлом.
ATTACH_FILE_THRESHOLD = 3 * TELEGRAM_MESSAGE_LIMIT
SAFE_CHUNK_LIMIT = 3800  # запас под HTML-разметку и склейку


def split_text(text: str, limit: int = SAFE_CHUNK_LIMIT) -> list[str]:
    """Режет текст на куски не длиннее limit, предпочитая границы строк."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def deliver_long_text(
    text: str,
    message: Message | None,
    *,
    answer: Callable[..., Awaitable[None]],
    filename: str = "output.txt",
) -> None:
    """Отправляет длинный текст: кусками в чат, при очень большом размере — плюс файлом."""
    if not text:
        text = "(пустой ответ)"

    # Отключаем HTML parse_mode для кусков: текст инструментов может содержать
    # угловые скобки, которые Telegram попытался бы разобрать как теги.
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        await answer(text, parse_mode=None)
        return

    if len(text) > ATTACH_FILE_THRESHOLD and message is not None:
        head = text[:TELEGRAM_MESSAGE_LIMIT]
        await answer(head + "\n[...полный вывод во вложенном файле...]", parse_mode=None)
        try:
            buffer = io.BytesIO(text.encode("utf-8"))
            from aiogram.types import BufferedInputFile

            await message.answer_document(
                BufferedInputFile(buffer.read(), filename=filename),
                caption=f"Полный вывод ({len(text)} символов)",
            )
            return
        except Exception:
            logger.exception("Не удалось прикрепить файл с полным выводом — отправляю кусками")
            # Фолбэк: файл не прикрепился, отправляем остаток частями.
            for chunk in split_text(text[TELEGRAM_MESSAGE_LIMIT:]):
                await answer(chunk, parse_mode=None)
            return

    for chunk in split_text(text):
        await answer(chunk, parse_mode=None)
