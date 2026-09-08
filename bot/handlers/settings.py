import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ai.memory import clear_history
from app.runtime_settings import RUNTIME_SETTINGS, RuntimeSettingError, SettingsService
from database.engine import async_session_factory

logger = logging.getLogger(__name__)

router = Router(name="settings")

HELP_TEXT = """📖 Алиса — что я умею

Сервер и Docker (просто пиши по-русски):
• «Проверь сервер» — полная диагностика
• «Почему сайт не работает?» — сам разберусь по цепочке
• «Перезапусти nginx» — спрошу подтверждение
• «Покажи логи backend» — контейнер или сервис
• «Что занимает место на диске?»

Файлы:
• «Найди config.json», «Прочитай /var/www/...»
• Правка файлов — с бэкапом и откатом при неудачной валидации

Код:
• «Создай FastAPI API для X» — проект в Code Workspace
• Фото/скриншоты — анализирую через Claude Vision
• Документы TXT/LOG/JSON/YAML/XML/PDF — разбираю содержимое

Опасные действия всегда через подтверждение кнопкой.

Команды:
/settings — показать и менять настройки
/clear — очистить память диалога
"""


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("settings"))
async def handle_settings(message: Message) -> None:
    """Без аргументов — список; `/settings ключ значение` — изменить; `/settings ключ reset` — сбросить."""
    parts = (message.text or "").split(maxsplit=2)

    if len(parts) == 1:
        async with async_session_factory() as session:
            service = SettingsService(session)
            values = await service.all_raw()

        lines = ["⚙️ Настройки\n"]
        for key, value in values.items():
            spec = RUNTIME_SETTINGS[key]
            lines.append(f"• {key} = {value}\n  {spec.description}")
        lines.append("\nИзменить: /settings <ключ> <значение>")
        lines.append("Сбросить: /settings <ключ> reset")
        await message.answer("\n".join(lines))
        return

    if len(parts) == 2:
        await message.answer(
            f"Использование:\n/settings {parts[1]} <значение>\n/settings {parts[1]} reset"
        )
        return

    key, raw_value = parts[1], parts[2]

    async with async_session_factory() as session:
        service = SettingsService(session)
        try:
            if raw_value.strip().lower() == "reset":
                default_value = await service.reset(key)
                await message.answer(f"✅ {key} сброшена в значение по умолчанию: {default_value}")
            else:
                parsed = await service.set(key, raw_value)
                await message.answer(f"✅ {key} = {parsed}")
        except RuntimeSettingError as exc:
            await message.answer(f"⚠️ {exc}")
            return

    logger.info("Настройка %s изменена пользователем %s", key, message.from_user.id)


@router.message(Command("clear"))
async def handle_clear(message: Message) -> None:
    async with async_session_factory() as session:
        deleted = await clear_history(session, message.chat.id)
    await message.answer(f"🧹 Память диалога очищена (удалено сообщений: {deleted}).")
