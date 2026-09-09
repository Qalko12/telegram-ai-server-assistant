"""Инструмент для отправки файлов из Code Workspace в Telegram-чат как вложений.

Когда Алиса создаёт/редактирует код, она может сразу отправить готовый файл
пользователю — не текстом, а как файл (можно скачать, открыть в редакторе).
"""

import io
import logging
from pathlib import Path

from aiogram.types import BufferedInputFile
from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from coding.workspace import project_root, resolve_inside
from security.levels import SecurityLevel

logger = logging.getLogger(__name__)


class SendFileParams(BaseModel):
    project: str = Field(description="Имя проекта в Code Workspace")
    path: str = Field(description="Относительный путь к файлу внутри проекта (например, 'app/main.py')")
    caption: str = Field(default="", description="Подпись к файлу (необязательно)")


async def handle_send_file_to_chat(params: SendFileParams, ctx: ExecutionContext) -> str:
    """Отправляет файл из проекта в Telegram-чат как вложение."""
    if ctx.bot is None:
        return "⚠️ Ошибка: нет доступа к bot instance. Файл не отправлен."

    try:
        root = project_root(params.project)
        file_path = resolve_inside(root, params.path)

        if not file_path.exists():
            return f"❌ Файл не найден: {params.project}/{params.path}"
        if not file_path.is_file():
            return f"❌ Это директория, а не файл: {params.project}/{params.path}"

        # Читаем содержимое
        content = file_path.read_bytes()

        # Проверяем размер (Telegram ограничивает до 50 МБ для ботов)
        if len(content) > 50 * 1024 * 1024:
            return f"❌ Файл слишком большой: {len(content)} байт (максимум 50 МБ для Telegram)"

        # Отправляем как документ
        filename = file_path.name
        caption = params.caption or f"{params.project}/{params.path}"

        await ctx.bot.send_document(
            chat_id=ctx.chat_id,
            document=BufferedInputFile(content, filename=filename),
            caption=caption,
        )

        logger.info("Файл отправлен в чат: %s/%s → chat %s", params.project, params.path, ctx.chat_id)
        return f"✅ Файл отправлен в чат: {filename}"

    except Exception as exc:
        logger.exception("Ошибка отправки файла %s/%s", params.project, params.path)
        return f"❌ Ошибка отправки файла: {exc}"


SEND_FILE_TO_CHAT = ToolSpec(
    name="send_file_to_chat",
    description=(
        "Отправить файл из Code Workspace в Telegram-чат как вложение (документ). "
        "Используй когда пользователь просит 'скинь файл', 'пришли код файлом' или когда "
        "ты создал/изменил код и хочешь сразу дать готовый файл. "
        "Файл придёт как вложение (можно скачать), а не текстом."
    ),
    input_model=SendFileParams,
    handler=handle_send_file_to_chat,
    security_level=SecurityLevel.SAFE,
)


def all_file_send_tools() -> tuple[ToolSpec, ...]:
    return (SEND_FILE_TO_CHAT,)
