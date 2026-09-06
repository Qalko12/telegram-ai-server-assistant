from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Привет! Я на связи и вижу, что ты авторизован.\n\n"
        "Подключение к Claude AI ещё в разработке — пока я умею только проверять доступ."
    )


@router.message(F.text)
async def handle_text_placeholder(message: Message) -> None:
    await message.answer(
        "Получил сообщение. ИИ-ядро ещё не подключено (следующий этап разработки) — "
        "пока бот только проверяет авторизацию."
    )
