from typing import Any, Dict, List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def task_edit_menu(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Заголовок", callback_data=f"task:edit:title:{task_id}"),
                InlineKeyboardButton(text="📝 Описание", callback_data=f"task:edit:desc:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="⚡ Приоритет", callback_data=f"task:edit:prio:{task_id}"),
                InlineKeyboardButton(text="📁 Категория", callback_data=f"task:edit:cat:{task_id}"),
            ],
            [InlineKeyboardButton(text="🎯 Дедлайн", callback_data=f"task:edit:due:{task_id}")],
            [
                InlineKeyboardButton(text="⬅️ К задаче", callback_data=f"tl:open:{task_id}"),
                InlineKeyboardButton(text="📋 К списку", callback_data="tl:back_to_list"),
            ],
        ]
    )


def task_edit_priority(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 ⬇️", callback_data=f"task:edit:prio:set:low:{task_id}"),
                InlineKeyboardButton(text="2 ⚖️", callback_data=f"task:edit:prio:set:medium:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="3 ⬆️", callback_data=f"task:edit:prio:set:high:{task_id}"),
                InlineKeyboardButton(text="4 🔥", callback_data=f"task:edit:prio:set:urgent:{task_id}"),
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data=f"task:edit:menu:{task_id}")],
        ]
    )


def task_edit_categories(task_id: int, categories: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=(category.get("name") or "—"),
                callback_data=f"task:edit:cat:set:{task_id}:{category.get('id')}",
            )
        ]
        for category in categories
    ]

    rows.append([InlineKeyboardButton(text="Без категории", callback_data=f"task:edit:cat:set:{task_id}:none")])
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"task:edit:menu:{task_id}")])

    return InlineKeyboardMarkup(inline_keyboard=rows)
