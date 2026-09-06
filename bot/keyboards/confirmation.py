from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_confirmation_keyboard(action_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнить", callback_data=f"confirm:{action_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel:{action_id}"),
            ]
        ]
    )
