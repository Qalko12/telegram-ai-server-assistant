from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.agent_dispatch import process_user_message

router = Router(name="start")

# Команды-шорткаты из ТЗ: переводятся в естественный запрос к агенту.
# Основной способ взаимодействия — обычный чат; команды не обязательны.
COMMAND_PROMPTS = {
    "server": "Проведи полную диагностику сервера и покажи краткий отчёт.",
    "docker": "Покажи состояние Docker: контейнеры, статистику и проблемы.",
    "logs": "Покажи последние ошибки в системных логах.",
    "processes": "Покажи процессы, потребляющие больше всего CPU и RAM.",
    "disk": "Покажи использование диска и что занимает больше всего места.",
    "services": "Покажи состояние важных системных сервисов (systemd).",
    "projects": "Покажи список проектов в Code Workspace и их статусы.",
    "coding": (
        "Режим разработки активен. Я опишу задачу по коду — работай в Code Workspace: "
        "создавай/правь проекты, запускай тесты и исправляй ошибки."
    ),
}


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Привет! Я Алиса — технический помощник по серверу и коду.\n\n"
        "Пиши обычным языком — что нужно сделать?\n"
        "/help — что я умею, /settings — настройки."
    )


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    await process_user_message(message, "Кратко: статус сервера — CPU, RAM, диск, load, uptime, Docker.")


@router.message(Command(*COMMAND_PROMPTS.keys()))
async def handle_command_shortcut(message: Message) -> None:
    command = message.text.split(maxsplit=1)[0].lstrip("/").split("@")[0].lower()
    prompt = COMMAND_PROMPTS.get(command)
    if prompt is None:
        return
    await process_user_message(message, prompt)


@router.message(F.text)
async def handle_text(message: Message) -> None:
    await process_user_message(message, message.text)
