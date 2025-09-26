from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def task_actions(task_id: int, is_archived: bool = False) -> InlineKeyboardMarkup:
    """Inline-кнопки для действий с задачами."""
    buttons = [
        InlineKeyboardButton(text="✏️ Обновить", callback_data=f"task_update:{task_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task_delete:{task_id}")
    ]
    if is_archived:
        buttons.append(InlineKeyboardButton(text="♻️ Восстановить", callback_data=f"task_restore:{task_id}"))
    else:
        buttons.append(InlineKeyboardButton(text="📦 Архивировать", callback_data=f"task_archive:{task_id}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])
