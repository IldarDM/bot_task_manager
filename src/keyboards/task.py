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


def priority_keyboard() -> InlineKeyboardMarkup:
    """Выбор приоритета задач (1..4)."""
    rows = [
        [
            InlineKeyboardButton(text="1 ⬇️ Низкий", callback_data="prio:low"),
            InlineKeyboardButton(text="2 ⚖️ Средний", callback_data="prio:medium"),
        ],
        [
            InlineKeyboardButton(text="3 ⬆️ Высокий", callback_data="prio:high"),
            InlineKeyboardButton(text="4 🔥 Срочный", callback_data="prio:urgent"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def due_quick_keyboard() -> InlineKeyboardMarkup:
    """Быстрый выбор дедлайна."""
    rows = [
        [
            InlineKeyboardButton(text="Сегодня", callback_data="due:today"),
            InlineKeyboardButton(text="Завтра", callback_data="due:tomorrow"),
            InlineKeyboardButton(text="+3 дня", callback_data="due:+3"),
        ],
        [
            InlineKeyboardButton(text="Без дедлайна", callback_data="due:none"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
