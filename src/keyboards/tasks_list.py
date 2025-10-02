from typing import Dict, List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def list_panel_keyboard(
    prof: Dict,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    """
    Главное меню управления листингом задач.
    prof — профиль фильтров/сортировки/пагинации.
    """
    rows: List[List[InlineKeyboardButton]] = []

    rows.append([
        InlineKeyboardButton(text="🔥 Срочные", callback_data="tl:urgent"),
        InlineKeyboardButton(text="⏰ Просрочено", callback_data="tl:overdue"),
        InlineKeyboardButton(text="🎯 Сегодня", callback_data="tl:today"),
    ])

    rows.append([
        InlineKeyboardButton(text="🗂 Категория", callback_data="tl:cat"),
        InlineKeyboardButton(text="⚡ Приоритет", callback_data="tl:prio"),
        InlineKeyboardButton(text="📌 Статус", callback_data="tl:st"),
    ])

    rows.append([
        InlineKeyboardButton(text="⇅ Сортировка", callback_data="tl:sort"),
        InlineKeyboardButton(
            text="📦 Архив" if prof.get("view") != "archived" else "📋 Активные",
            callback_data="tl:view:toggle",
        ),
        InlineKeyboardButton(text="🧹 Сброс", callback_data="tl:reset"),
    ])

    rows.append([
        InlineKeyboardButton(text="🔎 Поиск", callback_data="tl:search"),
    ])

    nav_row: List[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data="tl:page:prev"))
    nav_row.append(InlineKeyboardButton(text="🔄 Обновить", callback_data="tl:refresh"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data="tl:page:next"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def priorities_selector(prof: Dict) -> InlineKeyboardMarkup:
    """
    Мультивыбор приоритетов. Кнопки-переключатели.
    """
    selected = set(prof.get("priority") or [])
    def mark(k: str, label: str) -> str:
        return f"{'☑️' if k in selected else '⬜️'} {label}"

    rows = [
        [
            InlineKeyboardButton(text=mark("low", "Низкий"), callback_data="tl:prio:toggle:low"),
            InlineKeyboardButton(text=mark("medium", "Средний"), callback_data="tl:prio:toggle:medium"),
        ],
        [
            InlineKeyboardButton(text=mark("high", "Высокий"), callback_data="tl:prio:toggle:high"),
            InlineKeyboardButton(text=mark("urgent", "Срочный"), callback_data="tl:prio:toggle:urgent"),
        ],
        [
            InlineKeyboardButton(text="Готово", callback_data="tl:prio:apply"),
            InlineKeyboardButton(text="Сброс", callback_data="tl:prio:clear"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def statuses_selector(prof: Dict) -> InlineKeyboardMarkup:
    """
    Мультивыбор статусов.
    """
    selected = set(prof.get("status") or [])
    def mark(k: str, label: str) -> str:
        return f"{'☑️' if k in selected else '⬜️'} {label}"

    rows = [
        [
            InlineKeyboardButton(text=mark("todo", "В планах"), callback_data="tl:st:toggle:todo"),
            InlineKeyboardButton(text=mark("in_progress", "В работе"), callback_data="tl:st:toggle:in_progress"),
        ],
        [
            InlineKeyboardButton(text=mark("done", "Выполнено"), callback_data="tl:st:toggle:done"),
            InlineKeyboardButton(text=mark("archived", "Архив"), callback_data="tl:st:toggle:archived"),
        ],
        [
            InlineKeyboardButton(text="Готово", callback_data="tl:st:apply"),
            InlineKeyboardButton(text="Сброс", callback_data="tl:st:clear"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sort_selector(prof: Dict) -> InlineKeyboardMarkup:
    """
    Сортировка по полям API. Переключение направления для выбранного поля.
    """
    sb = prof.get("sort_by", "due_date")
    so = prof.get("sort_order", "asc")

    def item(label: str, key: str) -> InlineKeyboardButton:
        if sb == key:
            arrow = "↑" if so == "asc" else "↓"
            return InlineKeyboardButton(text=f"{label} {arrow}", callback_data=f"tl:sort:toggle_dir")
        return InlineKeyboardButton(text=label, callback_data=f"tl:sort:set:{key}")

    rows = [
        [
            item("Дедлайн", "due_date"),
            item("Приоритет", "priority"),
        ],
        [
            item("Обновлено", "updated_at"),
            item("Название", "title"),
        ],
        [
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_selector(categories: List[Dict], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    """
    Список категорий с пагинацией.
    """
    start = page * page_size
    page_items = categories[start:start + page_size]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=c.get("name", "—"), callback_data=f"tl:cat:set:{c.get('id')}")]
        for c in page_items
    ]

    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"tl:cat:page:{page-1}"))
    if start + page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️ След", callback_data=f"tl:cat:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Без категории", callback_data="tl:cat:none"),
        InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
