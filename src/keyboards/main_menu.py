from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

TASKS_BUTTON = "📋 Мои задачи"
CATEGORIES_BUTTON = "📂 Категории"
NEW_TASK_BUTTON = "➕ Задача"
NEW_CATEGORY_BUTTON = "➕ Категория"
HELP_BUTTON = "❓ Помощь"
PROFILE_BUTTON = "⚙️ Профиль"
REFRESH_BUTTON = "🔄 Обновить"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TASKS_BUTTON), KeyboardButton(text=CATEGORIES_BUTTON)],
            [KeyboardButton(text=NEW_TASK_BUTTON), KeyboardButton(text=NEW_CATEGORY_BUTTON)],
            [KeyboardButton(text=HELP_BUTTON), KeyboardButton(text=PROFILE_BUTTON)],
            [KeyboardButton(text=REFRESH_BUTTON)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
