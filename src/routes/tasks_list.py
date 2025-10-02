from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from aiogram import Router, F
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
    filters_menu, priorities_selector, statuses_selector, categories_selector, sort_keyboard
)


router = Router()


# ---------------------------- Профиль списка ----------------------------

DEFAULT_LIMIT = 10
GROUP_LIMIT = 8


@dataclass
class ListProfile:
    status: List[str] = field(default_factory=lambda: ["todo", "in_progress"])
    priority: List[str] = field(default_factory=list)
    category_id: Optional[int] = None
    due_date_from: Optional[str] = None
    due_date_to: Optional[str] = None
    is_overdue: Optional[bool] = None
    search: Optional[str] = None
    sort_by: str = "due_date"
    sort_order: str = "asc"
    view: str = "active"  # "active" | "archived"
    skip: int = 0
    limit: int = DEFAULT_LIMIT
    grp_offsets: Dict[str, int] = field(default_factory=lambda: {"urgent": 0, "overdue": 0, "today": 0, "rest": 0})
    grp_limit: int = GROUP_LIMIT
    cat_page: int = 0

    def to_params(self) -> Dict[str, Any]:
        p: Dict[str, Any] = {
            "skip": self.skip,
            "limit": self.limit,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "include_deleted": False,
        }
        if self.view == "archived":
            p["status"] = ["archived"]
        elif self.status:
            p["status"] = self.status
        if self.priority:
            p["priority"] = self.priority
        if self.category_id is not None:
            p["category_id"] = self.category_id
        if self.due_date_from:
            p["due_date_from"] = self.due_date_from
        if self.due_date_to:
            p["due_date_to"] = self.due_date_to
        if self.is_overdue is not None:
            p["is_overdue"] = self.is_overdue
        if self.search:
            p["search"] = self.search
        return p


class ListStates(StatesGroup):
    search = State()


# ---------------------------- Хелперы ----------------------------

async def _authed(message: Message) -> bool:
    if not await redis_client.is_authenticated(message.from_user.id):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return False
    return True


async def _get_prof(state: FSMContext) -> ListProfile:
    data = await state.get_data()
    raw = data.get("list_prof")
    if not raw:
        prof = ListProfile()
    elif isinstance(raw, ListProfile):
        prof = raw
    else:
        prof = ListProfile(**raw)
    return prof


async def _save_prof(state: FSMContext, prof: ListProfile) -> None:
    await state.update_data(list_prof=asdict(prof))


async def _safe_edit(message_or_cb: Message | CallbackQuery, text: str, kb):
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


async def _render_list(message_or_cb: Message | CallbackQuery, prof: ListProfile):
    user_id = message_or_cb.from_user.id
    resp = await TasksAPI.list(user_id, prof.to_params())
    if resp.status_code != 200:
        await _safe_edit(message_or_cb, "❌ Не удалось загрузить задачи.", kb=None)
        return

    data = resp.json() or {}
    tasks = data.get("tasks", data if isinstance(data, list) else [])
    total = data.get("total", len(tasks))
    page = (prof.skip // prof.limit) + 1 if prof.limit else 1
    pages = max(1, (total + prof.limit - 1) // prof.limit) if prof.limit else 1
    has_prev = prof.skip > 0
    has_next = (prof.skip + len(tasks)) < total

    groups = group_tasks(tasks)
    header = build_header(asdict(prof), total, page, pages)
    text = (
        "🗂 <b>Мои задачи</b>\n"
        f"{header}\n\n"
        "🔥 Срочные • ⏰ Просрочено • 🎯 Сегодня • Остальные\n"
        "Выберите задачу или откройте 🎛 фильтры."
    )
    kb = build_list_keyboard(groups, asdict(prof), has_prev, has_next)
    await _safe_edit(message_or_cb, text, kb)


# ---------------------------- Вход ----------------------------

@router.message(Command("tasks"))
async def tasks_entry(message: Message, state: FSMContext):
    if not await _authed(message):
        return
    prof = await _get_prof(state)
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(message, prof)


# ---------------------------- Навигация списка ----------------------------

@router.callback_query(F.data == "tl:refresh")
async def tl_refresh(callback: CallbackQuery, state: FSMContext):
    await _render_list(callback, await _get_prof(state))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:page:"))
async def tl_page(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    if callback.data.endswith(":prev"):
        prof.skip = max(0, prof.skip - prof.limit)
    else:
        prof.skip += prof.limit
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer()


@router.callback_query(F.data.startswith("tl:grp:"))
async def tl_group_more(callback: CallbackQuery, state: FSMContext):
    _, _, group, _ = callback.data.split(":")
    prof = await _get_prof(state)
    prof.grp_offsets[group] = prof.grp_offsets.get(group, 0) + prof.grp_limit
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Ещё…")


@router.callback_query(F.data == "tl:back_to_list")
async def tl_back_to_list(callback: CallbackQuery, state: FSMContext):
    await _render_list(callback, await _get_prof(state))
    await callback.answer()


# ---------------------------- Открыть карточку ----------------------------

@router.callback_query(F.data.startswith("tl:open:"))
async def tl_open(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[-1])
    resp = await TasksAPI.get(callback.from_user.id, task_id)
    if resp.status_code != 200:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    task = resp.json()
    await callback.message.edit_text(build_task_text(task), reply_markup=build_task_keyboard(task))
    await callback.answer()


# ---------------------------- Режим: активные / архив ----------------------------

@router.callback_query(F.data == "tl:view:toggle")
async def tl_view_toggle(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    if prof.view == "archived":
        prof.view = "active"
        prof.status = ["todo", "in_progress"]
        prof.sort_by, prof.sort_order = "due_date", "asc"
    else:
        prof.view = "archived"
        prof.status = []
        prof.sort_by, prof.sort_order = "updated_at", "desc"
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Режим: Архив" if prof.view == "archived" else "Режим: Активные")


# ---------------------------- Фильтры: панель/сброс/назад ----------------------------

@router.callback_query(F.data == "tl:filters")
async def tl_filters_open(callback: CallbackQuery):
    await callback.message.edit_text("Фильтры:", reply_markup=filters_menu())
    await callback.answer()


@router.callback_query(F.data == "tl:back")
async def tl_filters_back(callback: CallbackQuery, state: FSMContext):
    await _render_list(callback, await _get_prof(state))
    await callback.answer()


@router.callback_query(F.data == "tl:reset")
async def tl_filters_reset(callback: CallbackQuery, state: FSMContext):
    prof = ListProfile()
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Фильтры сброшены")


# ---------------------------- Флаги: срочно/просрочено/сегодня ----------------------------

@router.callback_query(F.data.in_({"tl:f:urgent", "tl:f:overdue", "tl:f:today"}))
async def tl_filters_flags(callback: CallbackQuery, state: FSMContext):
    from datetime import datetime, date
    prof = await _get_prof(state)

    if callback.data.endswith("urgent"):
        prof.priority = [] if set(prof.priority) == {"high", "urgent"} else ["high", "urgent"]

    elif callback.data.endswith("overdue"):
        prof.is_overdue = None if prof.is_overdue else True

    elif callback.data.endswith("today"):
        if prof.due_date_from and prof.due_date_to:
            prof.due_date_from = prof.due_date_to = None
        else:
            d = date.today()
            prof.due_date_from = datetime(d.year, d.month, d.day, 0, 0, 0).isoformat()
            prof.due_date_to = datetime(d.year, d.month, d.day, 23, 59, 59).isoformat()

    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# ---------------------------- Приоритеты ----------------------------

@router.callback_query(F.data == "tl:f:prio")
async def tl_prio_open(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof.priority))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:prio:toggle:"))
async def tl_prio_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = await _get_prof(state)
    s = set(prof.priority)
    s.remove(key) if key in s else s.add(key)
    prof.priority = sorted(s)
    await _save_prof(state, prof)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof.priority))
    await callback.answer()


@router.callback_query(F.data == "tl:f:prio:clear")
async def tl_prio_clear(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    prof.priority = []
    await _save_prof(state, prof)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(prof.priority))
    await callback.answer("Очищено")


@router.callback_query(F.data == "tl:f:prio:apply")
async def tl_prio_apply(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# ---------------------------- Статусы ----------------------------

@router.callback_query(F.data == "tl:f:status")
async def tl_st_open(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof.status))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:st:toggle:"))
async def tl_st_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = await _get_prof(state)
    s = set(prof.status)
    s.remove(key) if key in s else s.add(key)
    prof.status = sorted(s)
    await _save_prof(state, prof)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof.status))
    await callback.answer()


@router.callback_query(F.data == "tl:f:st:clear")
async def tl_st_clear(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    prof.status = []
    await _save_prof(state, prof)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(prof.status))
    await callback.answer("Очищено")


@router.callback_query(F.data == "tl:f:st:apply")
async def tl_st_apply(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# ---------------------------- Категории ----------------------------

@router.callback_query(F.data == "tl:f:cat")
async def tl_cat_open(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_text("Категория:", reply_markup=categories_selector(cats, page=prof.cat_page))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:cat:page:"))
async def tl_cat_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[-1])
    prof = await _get_prof(state)
    prof.cat_page = page
    await _save_prof(state, prof)
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=categories_selector(cats, page=page))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:cat:set:") | (F.data == "tl:f:cat:none"))
async def tl_cat_apply(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    if callback.data.endswith(":none"):
        prof.category_id = None
    else:
        prof.category_id = int(callback.data.split(":")[-1])
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Применено")


# ---------------------------- Сортировка ----------------------------

@router.callback_query(F.data == "tl:sort")
async def tl_sort_open(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    arrow = "↑" if prof.sort_order == "asc" else "↓"
    await callback.message.edit_text(
        "Сортировка:\n"
        "1) Дедлайн\n"
        "2) Приоритет\n"
        "3) Обновлено\n"
        "4) Название\n\n"
        f"Текущая: {prof.sort_by} {arrow}",
        reply_markup=sort_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tl:sort:set:"))
async def tl_sort_set(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    prof = await _get_prof(state)
    prof.sort_by, prof.sort_order, prof.skip = key, "asc", 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Сортировка применена")


@router.callback_query(F.data == "tl:sort:dir")
async def tl_sort_dir(callback: CallbackQuery, state: FSMContext):
    prof = await _get_prof(state)
    prof.sort_order = "desc" if prof.sort_order == "asc" else "asc"
    prof.skip = 0
    await _save_prof(state, prof)
    await _render_list(callback, prof)
    await callback.answer("Направление изменено")


# ---------------------------- Поиск ----------------------------

@router.callback_query(F.data == "tl:search")
async def tl_search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ListStates.search)
    await callback.message.edit_text("Введите строку поиска (или «-» чтобы очистить):")
    await callback.answer()


@router.message(ListStates.search)
async def tl_search_apply(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    prof = await _get_prof(state)
    prof.search = None if text == "-" else text
    prof.skip = 0
    await _save_prof(state, prof)
    await state.clear()
    await _render_list(message, prof)
