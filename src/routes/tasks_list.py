from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from src.database.redis_client import redis_client
from src.services.http_client import client
from src.utils.dates import format_due
from src.utils.translations import tr_status, tr_priority
from src.keyboards.tasks_list import (
    list_panel_keyboard,
    priorities_selector,
    statuses_selector,
    sort_selector,
    categories_selector,
)

router = Router()

DEFAULT_LIMIT = 10


class TasksListStates(StatesGroup):
    search = State()


# ---------- helpers ----------

def _today_range() -> Tuple[str, str]:
    today = date.today()
    start = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat()
    end = datetime(today.year, today.month, today.day, 23, 59, 59).isoformat()
    return start, end


def _default_profile() -> Dict[str, Any]:
    return {
        "status": ["todo", "in_progress"],
        "priority": [],
        "category_id": None,
        "due_date_from": None,
        "due_date_to": None,
        "is_overdue": None,
        "search": None,
        "sort_by": "due_date",
        "sort_order": "asc",
        "view": "active",
        "skip": 0,
        "limit": DEFAULT_LIMIT,
        "cat_page": 0,
    }


async def _ensure_auth_or_warn(message: Message) -> bool:
    if not await redis_client.is_authenticated(message.from_user.id):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return False
    return True


async def _fetch_categories(user_id: int) -> List[Dict]:
    resp = await client.request(user_id, "GET", "/categories/")
    if resp.status_code != 200:
        return []
    data = resp.json() or []
    items = data if isinstance(data, list) else []
    return [c for c in items if str(c.get("name", "")).strip().lower() != "uncategorized"]


def _params_from_profile(prof: Dict) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "skip": prof.get("skip", 0),
        "limit": prof.get("limit", DEFAULT_LIMIT),
        "sort_by": prof.get("sort_by", "due_date"),
        "sort_order": prof.get("sort_order", "asc"),
        "include_deleted": False,
    }
    status = prof.get("status")
    if status:
        params["status"] = status
    prio = prof.get("priority")
    if prio:
        params["priority"] = prio
    if prof.get("category_id") is not None:
        params["category_id"] = prof["category_id"]
    if prof.get("due_date_from"):
        params["due_date_from"] = prof["due_date_from"]
    if prof.get("due_date_to"):
        params["due_date_to"] = prof["due_date_to"]
    if prof.get("is_overdue") is not None:
        params["is_overdue"] = prof["is_overdue"]
    if prof.get("search"):
        params["search"] = prof["search"]

    if prof.get("view") == "archived":
        params["status"] = ["archived"]
        if prof.get("sort_by") == "due_date":
            params["sort_by"] = "updated_at"
            params["sort_order"] = "desc"
    return params


def _badge_list(prof: Dict, total: int, page: int, pages: int) -> str:
    parts: List[str] = []
    st = prof.get("status") or []
    if st:
        parts.append("Статус: " + ",".join(st))
    pr = prof.get("priority") or []
    if pr:
        parts.append("Приор: " + ",".join(pr))
    if prof.get("category_id") is not None:
        parts.append(f"Категория: id={prof['category_id']}")
    if prof.get("is_overdue"):
        parts.append("Просрочено")
    if prof.get("due_date_from") and prof.get("due_date_to"):
        parts.append("Сегодня")
    if prof.get("search"):
        parts.append(f"Поиск: “{prof['search']}”")
    parts.append(f"Сорт: {prof.get('sort_by')} {prof.get('sort_order')}")
    parts.append(f"Стр. {page}/{pages} • всего {total}")
    if prof.get("view") == "archived":
        parts.append("Режим: Архив")
    return " · ".join(parts)


def _render_tasks_lines(tasks: List[Dict]) -> str:
    lines: List[str] = []
    for t in tasks:
        task_id = t.get("id")
        title = t.get("title", "Без названия")
        status = tr_status(t.get("status"))
        prio = tr_priority(t.get("priority"))
        due = t.get("due_date")
        due_s = f" • ⏰ {format_due(due)}" if due else ""
        lines.append(f"{task_id}. {title} — {status} • {prio}{due_s}")
    return "\n".join(lines) if lines else "Нет задач по текущим фильтрам."


async def _safe_edit(message_or_cb, text: str, kb):
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=kb)
        return
    msg = message_or_cb.message
    try:
        if (msg.text or "") == text:
            await msg.edit_reply_markup(reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def _reload_list(message_or_cb, prof: Dict):
    user_id = message_or_cb.from_user.id
    params = _params_from_profile(prof)
    resp = await client.request(user_id, "GET", "/tasks/", params=params)
    if resp.status_code != 200:
        await _safe_edit(message_or_cb, "❌ Не удалось загрузить список задач.", kb=list_panel_keyboard(prof, False, False))
        return

    data = resp.json() or {}
    tasks = data.get("tasks", data if isinstance(data, list) else [])
    total = data.get("total", len(tasks))
    skip = prof.get("skip", 0)
    limit = prof.get("limit", DEFAULT_LIMIT)
    page = (skip // limit) + 1 if limit else 1
    pages = max(1, (total + limit - 1) // limit) if limit else 1

    has_prev = skip > 0
    has_next = (skip + len(tasks)) < total

    header = _badge_list(prof, total, page, pages)
    body = _render_tasks_lines(tasks)
    text = f"🗂 Список задач\n{header}\n\n{body}"

    await _safe_edit(message_or_cb, text, kb=list_panel_keyboard(prof, has_prev, has_next))


# ---------- entry ----------

@router.message(Command("tasks"))
async def tasks_entry(message: Message, state: FSMContext):
    if not await _ensure_auth_or_warn(message):
        return
    data = await state.get_data()
    prof = data.get("list_prof") or _default_profile()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(message, prof)


# ---------- main controls ----------

@router.callback_query(lambda c: c.data and c.data.startswith("tl:refresh"))
async def tl_refresh(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    await _reload_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:page:"))
async def tl_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prof = data.get("list_prof") or _default_profile()
    limit = prof.get("limit", DEFAULT_LIMIT)
    if callback.data.endswith(":prev"):
        prof["skip"] = max(0, prof.get("skip", 0) - limit)
    else:
        prof["skip"] = prof.get("skip", 0) + limit
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:urgent")
async def tl_urgent(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    cur = set(prof.get("priority") or [])
    target = {"high", "urgent"}
    if cur == target:
        prof["priority"] = []
    else:
        prof["priority"] = ["high", "urgent"]
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Фильтр: срочные" if prof["priority"] else "Фильтр приоритета снят")


@router.callback_query(lambda c: c.data and c.data == "tl:overdue")
async def tl_overdue(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["is_overdue"] = None if prof.get("is_overdue") else True
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Просрочка вкл" if prof.get("is_overdue") else "Просрочка выкл")


@router.callback_query(lambda c: c.data and c.data == "tl:today")
async def tl_today(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    if prof.get("due_date_from") and prof.get("due_date_to"):
        # выключить
        prof["due_date_from"] = None
        prof["due_date_to"] = None
    else:
        frm, to = _today_range()
        prof["due_date_from"] = frm
        prof["due_date_to"] = to
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:reset")
async def tl_reset(callback: CallbackQuery, state: FSMContext):
    prof = _default_profile()
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Фильтры сброшены")


@router.callback_query(lambda c: c.data and c.data.startswith("tl:view:toggle"))
async def tl_view_toggle(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["view"] = "archived" if prof.get("view") != "archived" else "active"
    # для архива сбрасываем статусы, так как view управляет им сам
    if prof["view"] == "archived":
        prof["status"] = []
    else:
        prof["status"] = ["todo", "in_progress"]
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Режим: Архив" if prof["view"] == "archived" else "Режим: Активные")


# ---------- priorities ----------

@router.callback_query(lambda c: c.data and c.data == "tl:prio")
async def tl_prio_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    await _safe_edit(callback, "Выберите приоритет(ы):", priorities_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:prio:toggle:"))
async def tl_prio_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    data = await state.get_data()
    prof = data.get("list_prof") or _default_profile()
    cur = set(prof.get("priority") or [])
    if key in cur:
        cur.remove(key)
    else:
        cur.add(key)
    prof["priority"] = sorted(cur)
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите приоритет(ы):", priorities_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:prio:clear")
async def tl_prio_clear(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["priority"] = []
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите приоритет(ы):", priorities_selector(prof))
    await callback.answer("Приоритеты очищены")


@router.callback_query(lambda c: c.data and c.data == "tl:prio:apply")
async def tl_prio_apply(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Применено")


# ---------- statuses ----------

@router.callback_query(lambda c: c.data and c.data == "tl:st")
async def tl_st_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    await _safe_edit(callback, "Выберите статус(ы):", statuses_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:st:toggle:"))
async def tl_st_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    cur = set(prof.get("status") or [])
    if key in cur:
        cur.remove(key)
    else:
        cur.add(key)
    prof["status"] = sorted(cur)
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите статус(ы):", statuses_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:st:clear")
async def tl_st_clear(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["status"] = []
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите статус(ы):", statuses_selector(prof))
    await callback.answer("Статусы очищены")


@router.callback_query(lambda c: c.data and c.data == "tl:st:apply")
async def tl_st_apply(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Применено")


# ---------- sort ----------

@router.callback_query(lambda c: c.data and c.data == "tl:sort")
async def tl_sort_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    await _safe_edit(callback, "Выберите сортировку:", sort_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:sort:set:"))
async def tl_sort_set(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["sort_by"] = key
    prof["sort_order"] = "asc"
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите сортировку:", sort_selector(prof))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:sort:toggle_dir")
async def tl_sort_toggle_dir(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["sort_order"] = "desc" if prof.get("sort_order") == "asc" else "asc"
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _safe_edit(callback, "Выберите сортировку:", sort_selector(prof))
    await callback.answer()


# ---------- categories ----------

@router.callback_query(lambda c: c.data and c.data == "tl:cat")
async def tl_cat_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    cats = await _fetch_categories(callback.from_user.id)
    await _safe_edit(callback, "Выберите категорию:", categories_selector(cats, page=prof.get("cat_page", 0)))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:cat:page:"))
async def tl_cat_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[-1])
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    prof["cat_page"] = page
    await state.update_data(list_prof=prof)
    cats = await _fetch_categories(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=categories_selector(cats, page=page))
    await callback.answer()


@router.callback_query(lambda c: c.data and (c.data == "tl:back" or c.data.startswith("tl:cat:set:") or c.data == "tl:cat:none"))
async def tl_cat_set_or_back(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()

    if callback.data == "tl:back":
        await _reload_list(callback, prof)
        await callback.answer()
        return

    if callback.data == "tl:cat:none":
        prof["category_id"] = None
    else:
        category_id = int(callback.data.split(":")[-1])
        prof["category_id"] = category_id

    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _reload_list(callback, prof)
    await callback.answer("Категория применена" if prof["category_id"] else "Без категории")


# ---------- search ----------

@router.callback_query(lambda c: c.data and c.data == "tl:search")
async def tl_search_start(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_profile()
    await state.set_state(TasksListStates.search)
    await callback.message.edit_text("Введите строку поиска (или «-» чтобы очистить):")
    await callback.answer()


@router.message(TasksListStates.search)
async def tl_search_apply(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    prof = data.get("list_prof") or _default_profile()

    if text == "-":
        prof["search"] = None
    else:
        prof["search"] = text

    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await state.clear()
    await _reload_list(message, prof)
