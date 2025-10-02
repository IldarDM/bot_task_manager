from typing import Dict, List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.translations import tr_priority, tr_status


def filters_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Срочные", callback_data="tl:f:urgent"),
            InlineKeyboardButton(text="⏰ Просрочено", callback_data="tl:f:overdue"),
            InlineKeyboardButton(text="🎯 Сегодня", callback_data="tl:f:today"),
        ],
        [
            InlineKeyboardButton(text="⚡ Приоритет", callback_data="tl:f:prio"),
            InlineKeyboardButton(text="📌 Статус", callback_data="tl:f:status"),
            InlineKeyboardButton(text="🗂 Категория", callback_data="tl:f:cat"),
        ],
        [
            InlineKeyboardButton(text="🧹 Сброс", callback_data="tl:reset"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
        ],
    ])


def priorities_selector(selected: List[str]) -> InlineKeyboardMarkup:
    s = set(selected or [])
    def mark(k: str, label: str) -> str:
        return f"{'☑️' if k in s else '⬜️'} {label}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=mark("low", tr_priority("low")), callback_data="tl:f:prio:toggle:low"),
            InlineKeyboardButton(text=mark("medium", tr_priority("medium")), callback_data="tl:f:prio:toggle:medium"),
        ],
        [
            InlineKeyboardButton(text=mark("high", tr_priority("high")), callback_data="tl:f:prio:toggle:high"),
            InlineKeyboardButton(text=mark("urgent", tr_priority("urgent")), callback_data="tl:f:prio:toggle:urgent"),
        ],
        [
            InlineKeyboardButton(text="Применить", callback_data="tl:f:prio:apply"),
            InlineKeyboardButton(text="Сброс", callback_data="tl:f:prio:clear"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:filters"),
        ],
    ])


def statuses_selector(selected: List[str]) -> InlineKeyboardMarkup:
    s = set(selected or [])
    def mark(k: str, label: str) -> str:
        return f"{'☑️' if k in s else '⬜️'} {label}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=mark("todo", tr_status("todo")), callback_data="tl:f:st:toggle:todo"),
            InlineKeyboardButton(text=mark("in_progress", tr_status("in_progress")), callback_data="tl:f:st:toggle:in_progress"),
        ],
        [
            InlineKeyboardButton(text=mark("done", tr_status("done")), callback_data="tl:f:st:toggle:done"),
            InlineKeyboardButton(text=mark("archived", tr_status("archived")), callback_data="tl:f:st:toggle:archived"),
        ],
        [
            InlineKeyboardButton(text="Применить", callback_data="tl:f:st:apply"),
            InlineKeyboardButton(text="Сброс", callback_data="tl:f:st:clear"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:filters"),
        ],
    ])


def categories_selector(categories: List[dict], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    start = page * page_size
    chunk = categories[start: start + page_size]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=(c.get("name") or "—"), callback_data=f"tl:f:cat:set:{c.get('id')}")]
        for c in chunk
    ]

    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"tl:f:cat:page:{page-1}"))
    if start + page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️ След", callback_data=f"tl:f:cat:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Без категории", callback_data="tl:f:cat:none"),
        InlineKeyboardButton(text="↩️ Назад", callback_data="tl:filters"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
