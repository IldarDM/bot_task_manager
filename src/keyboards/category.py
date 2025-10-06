from typing import Dict, List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

DEFAULT_PAGE_SIZE = 8


def categories_board(
    categories: List[Dict],
    page: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = categories[start : start + page_size]

    rows: List[List[InlineKeyboardButton]] = []
    for cat in chunk:
        name = cat.get("name") or "Без названия"
        if name.lower() == "uncategorized":
            name = "Без категории"
        rows.append([
            InlineKeyboardButton(
                text=f"📁 {name}",
                callback_data=f"category_open:{cat.get('id')}:{page}",
            )
        ])

    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"category_page:{page-1}"))
    if start + page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"category_page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(text="➕ Категория", callback_data="cat:new"),
            InlineKeyboardButton(text="🔄", callback_data="category_refresh"),
            InlineKeyboardButton(text="🏠", callback_data="tl:home"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_detail_keyboard(category_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Задачи", callback_data=f"tl:f:cat:set:{category_id}")],
            [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"category_update:{category_id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"category_delete:{category_id}:{page}")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data=f"category_back:{page}")],
        ]
    )
