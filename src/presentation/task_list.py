from typing import Dict, List, Tuple
from textwrap import shorten

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.translations import tr_priority, tr_status


GROUPS = ("urgent", "overdue", "today", "rest")


def _title_btn(task: Dict) -> InlineKeyboardButton:
    t = task.get("title", "Без названия")
    task_id = task.get("id")
    label = f"📝 {shorten(t, width=36, placeholder='…')} (#{task_id})"
    return InlineKeyboardButton(text=label, callback_data=f"tl:open:{task_id}")


def group_tasks(tasks: List[Dict]) -> Dict[str, List[Dict]]:
    urgent, overdue, today, rest = [], [], [], []
    for t in tasks:
        pr = (t.get("priority") or "").lower()
        due = t.get("due_date")
        st = (t.get("status") or "").lower()

        if st == "archived":
            continue

        if pr in {"urgent", "high"}:
            urgent.append(t)
            continue

        if due:
            pass

        rest.append(t)

    return {"urgent": urgent, "overdue": overdue, "today": today, "rest": rest}


def build_header(prof: Dict, total: int, page: int, pages: int) -> str:
    badges: List[str] = []
    if prof.get("view") == "archived":
        badges.append("Режим: Архив")
    pr = prof.get("priority") or []
    if pr:
        prs = [tr_priority(p) for p in pr]
        badges.append("Приор: " + ", ".join(prs))
    st = prof.get("status") or []
    if st:
        sts = [tr_status(s) for s in st]
        badges.append("Статус: " + ", ".join(sts))
    if prof.get("is_overdue"):
        badges.append("Просрочено")
    if prof.get("due_date_from") and prof.get("due_date_to"):
        badges.append("Сегодня")
    if prof.get("search"):
        badges.append(f"Поиск: «{prof['search']}»")

    badges.append(f"Сорт: {prof.get('sort_by', 'due_date')} {prof.get('sort_order', 'asc')}")
    badges.append(f"Стр. {page}/{pages} • всего {total}")
    return " · ".join(badges)


def build_list_keyboard(
    groups: Dict[str, List[Dict]],
    prof: Dict,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    grp_limit = int(prof.get("grp_limit", 8))
    offsets = prof.get("grp_offsets", {g: 0 for g in GROUPS})

    def section(title: str, key: str):
        items = groups.get(key, [])
        if not items:
            return
        start = offsets.get(key, 0)
        chunk = items[start : start + grp_limit]

        for i in range(0, len(chunk), 2):
            row = []
            row.append(_title_btn(chunk[i]))
            if i + 1 < len(chunk):
                row.append(_title_btn(chunk[i + 1]))
            rows.append(row)

        if start + grp_limit < len(items):
            rows.append([InlineKeyboardButton(text="Ещё…", callback_data=f"tl:grp:{key}:more")])

    section("🔥 Срочные", "urgent")
    section("⏰ Просрочено", "overdue")
    section("🎯 Сегодня", "today")
    section("Остальные", "rest")

    # панель управления
    control = [
        InlineKeyboardButton(text="🎛 Фильтры", callback_data="tl:filters"),
        InlineKeyboardButton(
            text="📦 Архив" if prof.get("view") != "archived" else "📋 Активные",
            callback_data="tl:view:toggle",
        ),
        InlineKeyboardButton(text="⇅ Сортировка", callback_data="tl:sort"),
        InlineKeyboardButton(text="🔎 Поиск", callback_data="tl:search"),
    ]
    rows.append(control)

    nav: List[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data="tl:page:prev"))
    nav.append(InlineKeyboardButton(text="🔄 Обновить", callback_data="tl:refresh"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data="tl:page:next"))
    rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)
