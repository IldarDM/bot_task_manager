from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def task_actions_keyboard(task_id: int, status: str | None, archived: bool) -> InlineKeyboardMarkup:
    rows = []

    rows.append([
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"task_update:{task_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task_delete:{task_id}"),
    ])

    if archived:
        rows.append([
            InlineKeyboardButton(text="♻️ Восстановить", callback_data=f"task_restore:{task_id}"),
        ])
    else:
        if (status or "").lower() == "done":
            rows.append([
                InlineKeyboardButton(text="↩️ В работу", callback_data=f"task_reopen:{task_id}"),
                InlineKeyboardButton(text="📦 Архив", callback_data=f"task_archive:{task_id}"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="✅ Готово", callback_data=f"task_done:{task_id}"),
            ])

    rows.append([
        InlineKeyboardButton(text="⬅️ К списку", callback_data="tl:back_to_list"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
