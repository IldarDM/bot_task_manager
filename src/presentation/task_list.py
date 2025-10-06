from datetime import date, datetime
from textwrap import shorten
from typing import Dict, List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GROUPS = ("urgent", "overdue", "today", "done", "rest", "archived")

GROUP_LABELS = {
    "urgent": "🔥 Срочные",
    "overdue": "⏰ Просрочено",
    "today": "🎯 Сегодня",
    "done": "✅ Выполненные",
    "rest": "📄 Остальные",
    "archived": "📦 Архив",
}


def _title_btn(task: Dict) -> InlineKeyboardButton:
    title = task.get("title") or "Без названия"
    task_id = task.get("id")
    label = f"• {shorten(title, width=34, placeholder='…')}"
    return InlineKeyboardButton(text=label, callback_data=f"tl:open:{task_id}")


def _as_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def group_tasks(tasks: List[Dict]) -> Dict[str, List[Dict]]:
    today = date.today()
    groups: Dict[str, List[Dict]] = {name: [] for name in GROUPS}

    for task in tasks:
        status = (task.get("status") or "").lower()
        if status == "archived":
            groups["archived"].append(task)
            continue
        if status == "done":
            groups["done"].append(task)
            continue

        priority = (task.get("priority") or "").lower()
        if priority in {"urgent", "high"}:
            groups["urgent"].append(task)
            continue

        due = _as_date(task.get("due_date"))
        if due:
            if due < today:
                groups["overdue"].append(task)
                continue
            if due == today:
                groups["today"].append(task)
                continue

        groups["rest"].append(task)

    return groups


def filters_active(profile: Dict) -> bool:
    status_default = {"todo", "in_progress"}
    statuses = set(profile.get("status") or [])
    view = profile.get("view", "active")
    return any(
        [
            profile.get("priority"),
            profile.get("category_id") is not None,
            profile.get("is_overdue"),
            profile.get("due_date_from") and profile.get("due_date_to"),
            profile.get("search"),
            view != "archived" and statuses and statuses != status_default,
        ]
    )


def build_header(profile: Dict, total: int, page: int, pages: int) -> str:
    chips: List[str] = []
    view = profile.get("view", "active")
    chips.append("📦 Архив" if view == "archived" else "📋 Активные")

    if profile.get("is_overdue"):
        chips.append("⏰ Просрочено")
    if profile.get("due_date_from") and profile.get("due_date_to"):
        chips.append("🎯 Диапазон")
    if profile.get("priority"):
        priority_marks = ",".join(p[:1].upper() for p in profile["priority"])
        chips.append(f"⚡ {priority_marks}")

    statuses = profile.get("status") or []
    if view != "archived" and statuses:
        em: List[str] = []
        for status in statuses:
            status = status.lower()
            if status == "todo":
                em.append("📝")
            elif status == "in_progress":
                em.append("⏳")
            elif status == "done":
                em.append("✅")
            elif status == "archived":
                em.append("📦")
        if em:
            chips.append("".join(em))

    if profile.get("search"):
        chips.append("🔎")

    arrow = "↑" if profile.get("sort_order", "asc") == "asc" else "↓"
    chips.append(f"⇅{arrow}")
    chips.append(f"{page}/{pages} · {total}")

    return " · ".join(chips)


def build_list_keyboard(
    groups: Dict[str, List[Dict]],
    profile: Dict,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    limit = int(profile.get("grp_limit", 8))
    offsets = profile.get("grp_offsets", {g: 0 for g in GROUPS})

    def section(title: str, key: str) -> None:
        items = groups.get(key, [])
        if not items:
            return
        rows.append([InlineKeyboardButton(text=title, callback_data=f"tl:grp:info:{key}")])

        start = int(offsets.get(key, 0))
        chunk = items[start : start + limit]
        for task in chunk:
            rows.append([_title_btn(task)])

        if start + limit < len(items):
            rows.append([InlineKeyboardButton(text="Ещё…", callback_data=f"tl:grp:{key}:more")])

    for key in GROUPS:
        title = GROUP_LABELS.get(key)
        if title:
            section(title, key)

    filters_icon = "🎛*" if filters_active(profile) else "🎛"
    search_icon = "🔎*" if profile.get("search") else "🔎"
    view_icon = "📦" if profile.get("view") != "archived" else "📋"

    rows.append(
        [
            InlineKeyboardButton(text=filters_icon, callback_data="tl:filters"),
            InlineKeyboardButton(text=view_icon, callback_data="tl:view:toggle"),
            InlineKeyboardButton(text="⇅", callback_data="tl:sort"),
            InlineKeyboardButton(text=search_icon, callback_data="tl:search"),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(text="➕ Задача", callback_data="task:new"),
            InlineKeyboardButton(text="➕ Категория", callback_data="cat:new"),
            InlineKeyboardButton(text="🏠", callback_data="tl:home"),
        ]
    )

    nav_row: List[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data="tl:page:prev"))
    nav_row.append(InlineKeyboardButton(text="🔄", callback_data="tl:refresh"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data="tl:page:next"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_group_summary(groups: Dict[str, List[Dict]]) -> str:
    lines: List[str] = []
    for key in GROUPS:
        items = groups.get(key, [])
        if not items:
            continue
        label = GROUP_LABELS.get(key, key.title())
        lines.append(f"{label} — {len(items)}")
    return "\n".join(lines)
