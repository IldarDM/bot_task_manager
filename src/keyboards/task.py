from __future__ import annotations
from typing import List, Dict, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# -------- Общие действия над задачей --------
def task_actions(task_id: int, is_archived: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="✏️ Обновить", callback_data=f"task_update:{task_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task_delete:{task_id}"),
    ]
    if is_archived:
        buttons.append(InlineKeyboardButton(text="♻️ Восстановить", callback_data=f"task_restore:{task_id}"))
    else:
        buttons.append(InlineKeyboardButton(text="📦 Архивировать", callback_data=f"task_archive:{task_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# -------- Клавиатуры для создания --------
def priority_keyboard() -> InlineKeyboardMarkup:
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
    rows = [
        [
            InlineKeyboardButton(text="Сегодня", callback_data="due:today"),
            InlineKeyboardButton(text="Завтра", callback_data="due:tomorrow"),
            InlineKeyboardButton(text="+3 дня", callback_data="due:+3"),
        ],
        [InlineKeyboardButton(text="Без дедлайна", callback_data="due:none")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------- Меню быстрого редактирования --------
def edit_menu_keyboard(
    task_id: int,
    title: Optional[str] = None,
    priority_human: Optional[str] = None,
    due_human: Optional[str] = None,
    category_name: Optional[str] = None,
) -> InlineKeyboardMarkup:
    t_title = f"📝 Заголовок{f': {title}' if title else ''}"
    t_desc = "✍️ Описание"
    t_prio = f"⚡ Приоритет{f': {priority_human}' if priority_human else ''}"
    t_due = f"⏰ Дедлайн{f': {due_human}' if due_human else ''}"
    t_cat = f"📁 Категория{f': {category_name}' if category_name else ''}"

    rows = [
        [
            InlineKeyboardButton(text=t_title, callback_data=f"edit:title:{task_id}"),
            InlineKeyboardButton(text=t_desc, callback_data=f"edit:desc:{task_id}"),
        ],
        [
            InlineKeyboardButton(text=t_prio, callback_data=f"edit:prio:{task_id}"),
            InlineKeyboardButton(text=t_due, callback_data=f"edit:due:{task_id}"),
        ],
        [
            InlineKeyboardButton(text=t_cat, callback_data=f"edit:cat:{task_id}"),
        ],
        [
            InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit:back:{task_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit:cancel:{task_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def priority_keyboard_for_task(task_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="1 ⬇️ Низкий", callback_data=f"eprio:{task_id}:low"),
            InlineKeyboardButton(text="2 ⚖️ Средний", callback_data=f"eprio:{task_id}:medium"),
        ],
        [
            InlineKeyboardButton(text="3 ⬆️ Высокий", callback_data=f"eprio:{task_id}:high"),
            InlineKeyboardButton(text="4 🔥 Срочный", callback_data=f"eprio:{task_id}:urgent"),
        ],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit:menu:{task_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def due_quick_keyboard_for_task(task_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Сегодня", callback_data=f"edue:{task_id}:today"),
            InlineKeyboardButton(text="Завтра", callback_data=f"edue:{task_id}:tomorrow"),
            InlineKeyboardButton(text="+3 дня", callback_data=f"edue:{task_id}:+3"),
        ],
        [
            InlineKeyboardButton(text="Без дедлайна", callback_data=f"edue:{task_id}:none"),
            InlineKeyboardButton(text="🗓 Ввести дату", callback_data=f"edue:{task_id}:manual"),
        ],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit:menu:{task_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------- Выбор категории --------
def _paginate(items: List[Dict], page: int, size: int) -> List[Dict]:
    start = page * size
    end = start + size
    return items[start:end]


def categories_keyboard_for_task(
    task_id: int,
    categories: List[Dict],
    page: int = 0,
    page_size: int = 6,
) -> InlineKeyboardMarkup:
    page_items = _paginate(categories, page, page_size)
    rows = []
    for c in page_items:
        rows.append(
            [InlineKeyboardButton(text=c.get("name", "—"), callback_data=f"ecat:{task_id}:set:{c.get('id')}")]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"ecat:{task_id}:page:{page-1}"))
    if (page + 1) * page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️ След", callback_data=f"ecat:{task_id}:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(text="Без категории", callback_data=f"ecat:{task_id}:none"),
            InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit:menu:{task_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_keyboard_for_create(
    categories: List[Dict],
    page: int = 0,
    page_size: int = 6,
) -> InlineKeyboardMarkup:
    page_items = _paginate(categories, page, page_size)
    rows = []
    for c in page_items:
        rows.append([InlineKeyboardButton(text=c.get("name", "—"), callback_data=f"ccat:set:{c.get('id')}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"ccat:page:{page-1}"))
    if (page + 1) * page_size < len(categories):
        nav.append(InlineKeyboardButton(text="➡️ След", callback_data=f"ccat:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(text="Пропустить", callback_data="ccat:skip"),
            InlineKeyboardButton(text="Без категории", callback_data="ccat:none"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
