from typing import Dict, List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def creation_priority_keyboard(selected: Optional[str]) -> InlineKeyboardMarkup:
    def btn(value: str, label: str) -> InlineKeyboardButton:
        mark = "☑️" if selected == value else "⬜️"
        return InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"task:create:prio:{value}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("low", "1 ⬇️ Низкий"),
            btn("medium", "2 ⚖️ Средний"),
        ],
        [
            btn("high", "3 ⬆️ Высокий"),
            btn("urgent", "4 🔥 Срочный"),
        ],
        [InlineKeyboardButton(text="Без приоритета", callback_data="task:create:prio:skip")],
    ])


def creation_category_keyboard(
    categories: List[Dict],
    *,
    page: int = 0,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = categories[start : start + page_size]

    rows: List[List[InlineKeyboardButton]] = []
    for idx, cat in enumerate(chunk, start=start + 1):
        name = (cat.get("name") or "Без названия").strip()
        rows.append([
            InlineKeyboardButton(
                text=f"{idx}. {name}",
                callback_data=f"task:create:cat:set:{cat.get('id')}",
            )
        ])

    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"task:create:cat:page:{page-1}"))
    if start + page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"task:create:cat:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Без категории", callback_data="task:create:cat:none"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def creation_due_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня", callback_data="task:create:due:today"),
            InlineKeyboardButton(text="Завтра", callback_data="task:create:due:tomorrow"),
        ],
        [
            InlineKeyboardButton(text="+3 дня", callback_data="task:create:due:+3"),
            InlineKeyboardButton(text="+7 дней", callback_data="task:create:due:+7"),
        ],
        [
            InlineKeyboardButton(text="🗓 Ввести дату", callback_data="task:create:due:manual"),
            InlineKeyboardButton(text="Без дедлайна", callback_data="task:create:due:skip"),
        ],
    ])
