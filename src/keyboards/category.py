from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def category_actions(category_id: int) -> InlineKeyboardMarkup:
    """Inline-кнопки для одной категории: обновить / удалить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Обновить", callback_data=f"category_update:{category_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"category_delete:{category_id}")
            ]
        ]
    )

def categories_menu() -> ReplyKeyboardMarkup:
    """Reply-клавиатура для пустого состояния категорий."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/newcategory")]
        ],
        resize_keyboard=True
    )
