from typing import Any, Dict, List, Tuple

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from src.database.redis_client import redis_client
from src.presentation.task_list import group_tasks, build_header, build_list_keyboard
from src.presentation.task_card import build_task_text, build_task_keyboard
from src.services.tasks_api import TasksAPI
from src.services.categories_api import CategoriesAPI
from src.keyboards.list_filters import (
    filters_menu, priorities_selector, statuses_selector, categories_selector
)

router = Router()

DEFAULT_LIMIT = 10
GROUP_LIMIT = 8


class ListStates(StatesGroup):
    search = State()


def _default_prof() -> Dict[str, Any]:
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
        "skip": 0, "limit": DEFAULT_LIMIT,
        "grp_offsets": {"urgent": 0, "overdue": 0, "today": 0, "rest": 0},
        "grp_limit": GROUP_LIMIT,
        "cat_page": 0,
    }


async def _ensure_auth(message: Message) -> bool:
    if not await redis_client.is_authenticated(message.from_user.id):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return False
    return True


def _params_from_prof(p: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "skip": p["skip"], "limit": p["limit"],
        "sort_by": p.get("sort_by", "due_date"),
        "sort_order": p.get("sort_order", "asc"),
        "include_deleted": False,
    }
    if p.get("view") == "archived":
        params["status"] = ["archived"]
    else:
        if p.get("status"):
            params["status"] = p["status"]
    if p.get("priority"):
        params["priority"] = p["priority"]
    if p.get("category_id") is not None:
        params["category_id"] = p["category_id"]
    if p.get("due_date_from"):
        params["due_date_from"] = p["due_date_from"]
    if p.get("due_date_to"):
        params["due_date_to"] = p["due_date_to"]
    if p.get("is_overdue") is not None:
        params["is_overdue"] = p["is_overdue"]
    if p.get("search"):
        params["search"] = p["search"]
    return params


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


async def _render_list(message_or_cb, prof: Dict[str, Any]):
    user_id = message_or_cb.from_user.id
    params = _params_from_prof(prof)
    resp = await TasksAPI.list(user_id, params)
    if resp.status_code != 200:
        await _safe_edit(message_or_cb, "❌ Не удалось загрузить задачи.", kb=None)
        return

    data = resp.json() or {}
    tasks = data.get("tasks", data if isinstance(data, list) else [])
    total = data.get("total", len(tasks))
    skip = prof["skip"]; limit = prof["limit"]
    page = (skip // limit) + 1 if limit else 1
    pages = max(1, (total + limit - 1) // limit) if limit else 1
    has_prev = skip > 0
    has_next = (skip + len(tasks)) < total

    groups = group_tasks(tasks)
    header = build_header(prof, total, page, pages)
    text = f"🗂 <b>Мои задачи</b>\n{header}\n\n" \
           f"🔥 Срочные • ⏰ Просрочено • 🎯 Сегодня • Остальные\n" \
           f"Выберите задачу или откройте 🎛 фильтры."

    kb = build_list_keyboard(groups, prof, has_prev, has_next)
    await _safe_edit(message_or_cb, text, kb)


# Entry ----------------------------------------------------

@router.message(Command("tasks"))
async def tasks_entry(message: Message, state: FSMContext):
    if not await _ensure_auth(message):
        return
    data = await state.get_data()
    prof = data.get("list_prof") or _default_prof()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(message, prof)


# Navigation ------------------------------------------------

@router.callback_query(lambda c: c.data and c.data == "tl:refresh")
async def tl_refresh(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    await _render_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:page:"))
async def tl_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data(); prof = data.get("list_prof") or _default_prof()
    limit = prof["limit"]
    if callback.data.endswith(":prev"):
        prof["skip"] = max(0, prof["skip"] - limit)
    else:
        prof["skip"] = prof["skip"] + limit
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:grp:"))
async def tl_group_more(callback: CallbackQuery, state: FSMContext):
    # увеличиваем оффсет внутри секции и просто перерисовываем клавиатуру (весь список)
    _, _, group, _ = callback.data.split(":")
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    off = prof["grp_offsets"].get(group, 0)
    prof["grp_offsets"][group] = off + prof["grp_limit"]
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Ещё…" )


@router.callback_query(lambda c: c.data and c.data == "tl:back_to_list")
async def tl_back_to_list(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    await _render_list(callback, prof)
    await callback.answer()


# Open card -------------------------------------------------

@router.callback_query(lambda c: c.data and c.data.startswith("tl:open:"))
async def tl_open(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    resp = await TasksAPI.get(user_id, task_id)
    if resp.status_code != 200:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    task = resp.json()
    await callback.message.edit_text(build_task_text(task), reply_markup=build_task_keyboard(task))
    await callback.answer()


# View toggle -----------------------------------------------

@router.callback_query(lambda c: c.data and c.data == "tl:view:toggle")
async def tl_view_toggle(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    if prof.get("view") == "archived":
        prof["view"] = "active"
        prof["status"] = ["todo", "in_progress"]
    else:
        prof["view"] = "archived"
        prof["status"] = []
        prof["sort_by"] = "updated_at"; prof["sort_order"] = "desc"
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Режим: Архив" if prof["view"] == "archived" else "Режим: Активные")


# Filters panel --------------------------------------------

@router.callback_query(lambda c: c.data and c.data == "tl:filters")
async def tl_filters_open(callback: CallbackQuery):
    await callback.message.edit_text("Фильтры:", reply_markup=filters_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:back")
async def tl_filters_back(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    await _render_list(callback, prof)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:reset")
async def tl_filters_reset(callback: CallbackQuery, state: FSMContext):
    prof = _default_prof()
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Фильтры сброшены")


# Quick flags
@router.callback_query(lambda c: c.data and c.data in {"tl:f:urgent", "tl:f:overdue", "tl:f:today"})
async def tl_filters_flags(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()

    if callback.data.endswith("urgent"):
        prof["priority"] = [] if set(prof.get("priority") or []) == {"high", "urgent"} else ["high", "urgent"]
    elif callback.data.endswith("overdue"):
        prof["is_overdue"] = None if prof.get("is_overdue") else True
    elif callback.data.endswith("today"):
        if prof.get("due_date_from") and prof.get("due_date_to"):
            prof["due_date_from"] = None; prof["due_date_to"] = None
        else:
            from datetime import datetime, date
            d = date.today()
            prof["due_date_from"] = datetime(d.year, d.month, d.day, 0, 0, 0).isoformat()
            prof["due_date_to"] = datetime(d.year, d.month, d.day, 23, 59, 59).isoformat()

    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# Priorities
@router.callback_query(lambda c: c.data and c.data == "tl:f:prio")
async def tl_prio_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof.get("priority") or []))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:f:prio:toggle:"))
async def tl_prio_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    cur = set(prof.get("priority") or [])
    if key in cur: cur.remove(key)
    else: cur.add(key)
    prof["priority"] = sorted(cur)
    await state.update_data(list_prof=prof)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof["priority"]))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:f:prio:clear")
async def tl_prio_clear(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["priority"] = []
    await state.update_data(list_prof=prof)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof["priority"]))
    await callback.answer("Очищено")


@router.callback_query(lambda c: c.data and c.data == "tl:f:prio:apply")
async def tl_prio_apply(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# Statuses
@router.callback_query(lambda c: c.data and c.data == "tl:f:status")
async def tl_st_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof.get("status") or []))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:f:st:toggle:"))
async def tl_st_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    cur = set(prof.get("status") or [])
    if key in cur: cur.remove(key)
    else: cur.add(key)
    prof["status"] = sorted(cur)
    await state.update_data(list_prof=prof)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof["status"]))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "tl:f:st:clear")
async def tl_st_clear(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["status"] = []
    await state.update_data(list_prof=prof)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof["status"]))
    await callback.answer("Очищено")


@router.callback_query(lambda c: c.data and c.data == "tl:f:st:apply")
async def tl_st_apply(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# Categories
@router.callback_query(lambda c: c.data and c.data == "tl:f:cat")
async def tl_cat_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_text("Категория:", reply_markup=categories_selector(cats, page=prof.get("cat_page", 0)))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("tl:f:cat:page:"))
async def tl_cat_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[-1])
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["cat_page"] = page
    await state.update_data(list_prof=prof)
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=categories_selector(cats, page=page))
    await callback.answer()


@router.callback_query(lambda c: c.data and (c.data.startswith("tl:f:cat:set:") or c.data == "tl:f:cat:none"))
async def tl_cat_apply(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    if callback.data.endswith(":none"):
        prof["category_id"] = None
    else:
        prof["category_id"] = int(callback.data.split(":")[-1])
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# Sort ------------------------------------------------------

@router.callback_query(lambda c: c.data and c.data == "tl:sort")
async def tl_sort_open(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    order = prof.get("sort_order", "asc")
    arrow = "↑" if order == "asc" else "↓"
    await callback.message.edit_text(
        f"Сортировка:\n"
        f"1) Дедлайн\n"
        f"2) Приоритет\n"
        f"3) Обновлено\n"
        f"4) Название\n\n"
        f"Текущая: {prof.get('sort_by', 'due_date')} {arrow}",
        reply_markup=_sort_kb(),
    )
    await callback.answer()


def _sort_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Дедлайн", callback_data="tl:sort:set:due_date"),
            InlineKeyboardButton(text="Приоритет", callback_data="tl:sort:set:priority"),
        ],
        [
            InlineKeyboardButton(text="Обновлено", callback_data="tl:sort:set:updated_at"),
            InlineKeyboardButton(text="Название", callback_data="tl:sort:set:title"),
        ],
        [
            InlineKeyboardButton(text="↕️ Направление", callback_data="tl:sort:dir"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="tl:back"),
        ]
    ])


@router.callback_query(lambda c: c.data and c.data.startswith("tl:sort:set:"))
async def tl_sort_set(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["sort_by"] = key; prof["sort_order"] = "asc"; prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Сортировка применена")


@router.callback_query(lambda c: c.data and c.data == "tl:sort:dir")
async def tl_sort_dir(callback: CallbackQuery, state: FSMContext):
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["sort_order"] = "desc" if prof.get("sort_order") == "asc" else "asc"
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await _render_list(callback, prof)
    await callback.answer("Направление изменено")


# Search ----------------------------------------------------

@router.callback_query(lambda c: c.data and c.data == "tl:search")
async def tl_search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ListStates.search)
    await callback.message.edit_text("Введите строку поиска (или «-» чтобы очистить):")
    await callback.answer()


@router.message(ListStates.search)
async def tl_search_apply(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    prof = (await state.get_data()).get("list_prof") or _default_prof()
    prof["search"] = None if text == "-" else text
    prof["skip"] = 0
    await state.update_data(list_prof=prof)
    await state.clear()
    await _render_list(message, prof)
