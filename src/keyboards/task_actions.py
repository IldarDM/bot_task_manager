from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def task_actions_keyboard(task_id: int, status: str | None, archived: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏️", callback_data=f"task_update:{task_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"task_delete:{task_id}"),
        ]
    ]

    st = (status or "").lower()
    if archived:
        rows.append([InlineKeyboardButton(text="♻️", callback_data=f"task_restore:{task_id}")])
    else:
        if st == "done":
            rows.append([
                InlineKeyboardButton(text="↩️", callback_data=f"task_reopen:{task_id}"),
                InlineKeyboardButton(text="📦", callback_data=f"task_archive:{task_id}"),
            ])
        else:
            rows.append([InlineKeyboardButton(text="✅", callback_data=f"task_done:{task_id}")])

    rows.append([InlineKeyboardButton(text="⬅️", callback_data="tl:back_to_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="tl:back_to_list")]
    ])
