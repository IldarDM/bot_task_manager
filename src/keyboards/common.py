from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопкой Отмена для FSM."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Введите данные или нажмите «Отмена»",
    )


def auth_retry_keyboard() -> InlineKeyboardMarkup:
    """Кнопки при ошибке авторизации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Повторить пароль", callback_data="auth:retry_pwd"),
                InlineKeyboardButton(text="✉️ Изменить email", callback_data="auth:change_email"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]
    )


def inline_back_to_menu(task_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit:menu:{task_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit:cancel:{task_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)