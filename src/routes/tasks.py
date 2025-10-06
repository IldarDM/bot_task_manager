from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.database.redis_client import redis_client
from src.keyboards.list_filters import (
    categories_selector,
    filters_menu,
    priorities_selector,
    sort_keyboard,
    statuses_selector,
)
from src.keyboards.task_actions import back_to_list_keyboard
from src.keyboards.task_editor import (
    task_edit_categories as task_edit_categories_keyboard,
    task_edit_menu as task_edit_menu_markup,
    task_edit_priority as task_edit_priority_keyboard,
)
from src.presentation.task_card import build_task_keyboard, build_task_text
from src.presentation.task_list import GROUPS, build_header, build_list_keyboard, group_tasks
from src.services.categories_api import CategoriesAPI
from src.services.tasks_api import TasksAPI
from src.utils.dates import parse_due

router = Router()

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
    view: str = "active"
    skip: int = 0
    limit: int = DEFAULT_LIMIT
    grp_offsets: Dict[str, int] = field(default_factory=lambda: {key: 0 for key in GROUPS})
    grp_limit: int = GROUP_LIMIT
    cat_page: int = 0

    def to_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "skip": self.skip,
            "limit": self.limit,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "include_deleted": False,
        }
        if self.view == "archived":
            params["status"] = ["archived"]
        elif self.status:
            params["status"] = self.status
        if self.priority:
            params["priority"] = self.priority
        if self.category_id is not None:
            params["category_id"] = self.category_id
        if self.due_date_from:
            params["due_date_from"] = self.due_date_from
        if self.due_date_to:
            params["due_date_to"] = self.due_date_to
        if self.is_overdue is not None:
            params["is_overdue"] = self.is_overdue
        if self.search:
            params["search"] = self.search
        return params

    def reset_paging(self) -> None:
        self.skip = 0
        self.grp_offsets = {key: 0 for key in GROUPS}


class ListStates(StatesGroup):
    search = State()


class EditStates(StatesGroup):
    waiting_value = State()


async def _ensure_authenticated(message: Message) -> bool:
    if not await redis_client.is_authenticated(message.from_user.id):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return False
    return True


async def _load_profile(state: FSMContext) -> ListProfile:
    data = await state.get_data()
    raw = data.get("list_prof")
    if isinstance(raw, ListProfile):
        profile = raw
    elif raw:
        profile = ListProfile(**raw)
    else:
        profile = ListProfile()

    profile.grp_offsets = {key: profile.grp_offsets.get(key, 0) for key in GROUPS}
    return profile


async def _store_profile(state: FSMContext, profile: ListProfile) -> None:
    await state.update_data(list_prof=asdict(profile))


async def _respond(target: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup | None) -> None:
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
        return

    msg = target.message
    try:
        if (msg.text or "") == text:
            await msg.edit_reply_markup(reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _render_list(target: Message | CallbackQuery, profile: ListProfile) -> None:
    resp = await TasksAPI.list(target.from_user.id, profile.to_params())
    if resp.status_code != 200:
        await _respond(target, "❌ Не удалось загрузить задачи.", kb=None)
        return

    data = resp.json() or {}
    tasks = data.get("tasks")
    if tasks is None and isinstance(data, list):
        tasks = data
    tasks = tasks or []

    total = data.get("total", len(tasks))
    page = (profile.skip // profile.limit) + 1 if profile.limit else 1
    pages = max(1, (total + profile.limit - 1) // profile.limit) if profile.limit else 1
    has_prev = profile.skip > 0
    has_next = (profile.skip + len(tasks)) < total

    groups = group_tasks(tasks)
    profile_dict = asdict(profile)
    header = build_header(profile_dict, total, page, pages)
    text = (
        "🗂 <b>Мои задачи</b>\n"
        f"{header}\n\n"
        "Выберите задачу или откройте 🎛 фильтры."
    )
    kb = build_list_keyboard(groups, profile_dict, has_prev, has_next)
    await _respond(target, text, kb)


async def _render_task_card(callback: CallbackQuery, task_id: int, task: Optional[Dict[str, Any]] = None) -> None:
    if task is None:
        resp = await TasksAPI.get(callback.from_user.id, task_id)
        if resp.status_code != 200:
            await callback.message.edit_text("Задача не найдена", reply_markup=back_to_list_keyboard())
            await callback.answer()
            return
        task = resp.json()

    await callback.message.edit_text(build_task_text(task), reply_markup=build_task_keyboard(task))
    await callback.answer()



async def _apply_patch(callback: CallbackQuery, task_id: int, payload: Dict[str, Any], error_text: str) -> None:
    resp = await TasksAPI.patch(callback.from_user.id, task_id, payload)
    if resp.status_code in (200, 204):
        task = None
        if resp.status_code == 200:
            try:
                task = resp.json()
            except Exception:
                task = None
        await _render_task_card(callback, task_id, task)
        return
    await callback.answer(error_text, show_alert=True)


@router.message(Command("tasks"))
async def tasks_entry(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        return
    profile = await _load_profile(state)
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(message, profile)


@router.callback_query(F.data == "tl:refresh")
async def tl_refresh(callback: CallbackQuery, state: FSMContext) -> None:
    await _render_list(callback, await _load_profile(state))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:page:"))
async def tl_page(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    if callback.data.endswith(":prev"):
        profile.skip = max(0, profile.skip - profile.limit)
    else:
        profile.skip += profile.limit
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer()


@router.callback_query(F.data.startswith("tl:grp:"))
async def tl_group_more(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, group, _ = callback.data.split(":")
    profile = await _load_profile(state)
    profile.grp_offsets[group] = profile.grp_offsets.get(group, 0) + profile.grp_limit
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Ещё…")


@router.callback_query(F.data == "tl:back_to_list")
async def tl_back(callback: CallbackQuery, state: FSMContext) -> None:
    await _render_list(callback, await _load_profile(state))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:open:"))
async def tl_open(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[-1])
    await _render_task_card(callback, task_id)


@router.callback_query(F.data == "tl:view:toggle")
async def tl_view_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    if profile.view == "archived":
        profile.view = "active"
        profile.status = ["todo", "in_progress"]
        profile.sort_by, profile.sort_order = "due_date", "asc"
    else:
        profile.view = "archived"
        profile.status = []
        profile.sort_by, profile.sort_order = "updated_at", "desc"
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Режим: Архив" if profile.view == "archived" else "Режим: Активные")


@router.callback_query(F.data == "tl:filters")
async def tl_filters_open(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Фильтры:", reply_markup=filters_menu())
    await callback.answer()


@router.callback_query(F.data == "tl:back")
async def tl_filters_back(callback: CallbackQuery, state: FSMContext) -> None:
    await _render_list(callback, await _load_profile(state))
    await callback.answer()


@router.callback_query(F.data == "tl:reset")
async def tl_filters_reset(callback: CallbackQuery, state: FSMContext) -> None:
    profile = ListProfile()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Фильтры сброшены")


@router.callback_query(F.data.in_({"tl:f:urgent", "tl:f:overdue", "tl:f:today"}))
async def tl_flag_filters(callback: CallbackQuery, state: FSMContext) -> None:
    from datetime import datetime, date

    profile = await _load_profile(state)
    if callback.data.endswith("urgent"):
        if set(profile.priority) == {"high", "urgent"}:
            profile.priority = []
        else:
            profile.priority = ["high", "urgent"]
    elif callback.data.endswith("overdue"):
        profile.is_overdue = None if profile.is_overdue else True
    else:
        if profile.due_date_from and profile.due_date_to:
            profile.due_date_from = profile.due_date_to = None
        else:
            today = date.today()
            start = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat()
            end = datetime(today.year, today.month, today.day, 23, 59, 59).isoformat()
            profile.due_date_from, profile.due_date_to = start, end

    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Применено")


@router.callback_query(F.data == "tl:f:prio")
async def tl_prio_open(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(profile.priority))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:prio:toggle:"))
async def tl_prio_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[-1]
    profile = await _load_profile(state)
    current = set(profile.priority)
    if key in current:
        current.remove(key)
    else:
        current.add(key)
    profile.priority = sorted(current)
    await _store_profile(state, profile)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(profile.priority))
    await callback.answer()


@router.callback_query(F.data == "tl:f:prio:clear")
async def tl_prio_clear(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    profile.priority = []
    await _store_profile(state, profile)
    await callback.message.edit_text("Приоритет:", reply_markup=priorities_selector(profile.priority))
    await callback.answer("Очищено")


@router.callback_query(F.data == "tl:f:prio:apply")
async def tl_prio_apply(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Применено")


@router.callback_query(F.data == "tl:f:status")
async def tl_status_open(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(profile.status))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:st:toggle:"))
async def tl_status_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[-1]
    profile = await _load_profile(state)
    current = set(profile.status)
    if key in current:
        current.remove(key)
    else:
        current.add(key)
    profile.status = sorted(current)
    await _store_profile(state, profile)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(profile.status))
    await callback.answer()


@router.callback_query(F.data == "tl:f:st:clear")
async def tl_status_clear(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    profile.status = []
    await _store_profile(state, profile)
    await callback.message.edit_text("Статусы:", reply_markup=statuses_selector(profile.status))
    await callback.answer("Очищено")


@router.callback_query(F.data == "tl:f:st:apply")
async def tl_status_apply(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Применено")


@router.callback_query(F.data == "tl:f:cat")
async def tl_cat_open(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_text("Категория:", reply_markup=categories_selector(cats, page=profile.cat_page))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:cat:page:"))
async def tl_cat_page(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    page = int(callback.data.split(":")[-1])
    profile.cat_page = page
    await _store_profile(state, profile)
    cats = await CategoriesAPI.list(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=categories_selector(cats, page=page))
    await callback.answer()


@router.callback_query(F.data.startswith("tl:f:cat:set:") | (F.data == "tl:f:cat:none"))
async def tl_cat_apply(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    if callback.data.endswith(":none") or callback.data.endswith("tl:f:cat:none"):
        profile.category_id = None
    else:
        profile.category_id = int(callback.data.split(":")[-1])
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Применено")


@router.callback_query(F.data == "tl:sort")
async def tl_sort_open(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    arrow = "↑" if profile.sort_order == "asc" else "↓"
    await callback.message.edit_text(
        "Сортировка:\n"
        "1) Дедлайн\n"
        "2) Приоритет\n"
        "3) Обновлено\n"
        "4) Название\n\n"
        f"Текущая: {profile.sort_by} {arrow}",
        reply_markup=sort_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tl:sort:set:"))
async def tl_sort_set(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[-1]
    profile = await _load_profile(state)
    profile.sort_by, profile.sort_order = key, "asc"
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Сортировка применена")


@router.callback_query(F.data == "tl:sort:dir")
async def tl_sort_dir(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _load_profile(state)
    profile.sort_order = "desc" if profile.sort_order == "asc" else "asc"
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(callback, profile)
    await callback.answer("Направление изменено")


@router.callback_query(F.data == "tl:search")
async def tl_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ListStates.search)
    await callback.message.edit_text("Введите строку поиска (или «-» чтобы очистить):")
    await callback.answer()


@router.message(ListStates.search)
async def tl_search_apply(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    profile = await _load_profile(state)
    profile.search = None if text == "-" else text or None
    profile.reset_paging()
    await _store_profile(state, profile)
    await state.clear()
    await _render_list(message, profile)


@router.callback_query(F.data.startswith("task_done:"))
async def task_done(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    await _apply_patch(callback, task_id, {"status": "done"}, "Не удалось завершить")


@router.callback_query(F.data.startswith("task_reopen:"))
async def task_reopen(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    await _apply_patch(callback, task_id, {"status": "in_progress"}, "Не удалось вернуть в работу")


@router.callback_query(F.data.startswith("task_archive:"))
async def task_archive(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    resp = await TasksAPI.archive(callback.from_user.id, task_id)
    if resp.status_code in (200, 204):
        task = None
        if resp.status_code == 200:
            try:
                task = resp.json()
            except Exception:
                task = None
        await _render_task_card(callback, task_id, task)
    else:
        await callback.answer("Не удалось архивировать", show_alert=True)


@router.callback_query(F.data.startswith("task_restore:"))
async def task_restore(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    resp = await TasksAPI.restore(callback.from_user.id, task_id)
    if resp.status_code in (200, 204):
        task = None
        if resp.status_code == 200:
            try:
                task = resp.json()
            except Exception:
                task = None
        await _render_task_card(callback, task_id, task)
    else:
        await callback.answer("Не удалось восстановить", show_alert=True)


@router.callback_query(F.data.startswith("task_delete:"))
async def task_delete(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    resp = await TasksAPI.delete(callback.from_user.id, task_id)
    if resp.status_code in (200, 204):
        await callback.message.edit_text("🗑 Задача удалена", reply_markup=back_to_list_keyboard())
        await callback.answer()
    else:
        await callback.answer("Не удалось удалить", show_alert=True)


@router.callback_query(F.data.startswith("task_update:") | F.data.startswith("task:edit:menu:"))
async def task_edit_menu(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[-1])
    await callback.message.edit_text("Что изменить?", reply_markup=task_edit_menu_markup(task_id))
    await callback.answer()


@router.callback_query(F.data.startswith("task:edit:prio:set:"))
async def task_edit_prio_set(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    priority = parts[4]
    task_id = int(parts[5])
    if priority not in {"low", "medium", "high", "urgent"}:
        await callback.answer("Некорректный приоритет", show_alert=True)
        return
    await _apply_patch(callback, task_id, {"priority": priority}, "Не удалось обновить приоритет")


@router.callback_query(F.data.startswith("task:edit:prio:"))
async def task_edit_prio_menu(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[-1])
    await callback.message.edit_text("Выберите приоритет:", reply_markup=task_edit_priority_keyboard(task_id))
    await callback.answer()


@router.callback_query(F.data.startswith("task:edit:cat:set:"))
async def task_edit_cat_set(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    _, _, _, _, task_id_raw, value = parts
    task_id = int(task_id_raw)
    payload = {"category_id": None if value == "none" else int(value)}
    await _apply_patch(callback, task_id, payload, "Не удалось обновить категорию")


@router.callback_query(F.data.startswith("task:edit:cat"))
async def task_edit_cat_menu(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[-1])
    cats = await CategoriesAPI.list(callback.from_user.id)
    if not cats:
        await callback.message.edit_text(
            "Категорий пока нет.",
            reply_markup=task_edit_categories_keyboard(task_id, [], page=0),
        )
    else:
        await callback.message.edit_text(
            "Выберите категорию:",
            reply_markup=task_edit_categories_keyboard(task_id, cats, page=0),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("task:edit:cat:page:"))
async def task_edit_cat_page(callback: CallbackQuery) -> None:
    _, _, _, _, task_id_raw, page_raw = callback.data.split(":")
    task_id = int(task_id_raw)
    page = int(page_raw)
    cats = await CategoriesAPI.list(callback.from_user.id)
    kb = task_edit_categories_keyboard(task_id, cats, page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("task:edit:title:") | F.data.startswith("task:edit:desc:") | F.data.startswith("task:edit:due:"))
async def task_edit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    field = parts[2]
    task_id = int(parts[3])
    await state.set_state(EditStates.waiting_value)
    await state.update_data(
        edit_task_id=task_id,
        edit_field=field,
        edit_chat_id=callback.message.chat.id,
        edit_message_id=callback.message.message_id,
    )
    if field == "title":
        prompt = "Введите новый заголовок:"
    elif field == "desc":
        prompt = "Введите новое описание (или «-», чтобы очистить):"
    else:
        prompt = (
            "Введите новую дату (DD-MM-YYYY | 2025-10-15 | сегодня | завтра | +3 | «-» убрать):"
        )
    await callback.message.edit_text(prompt)
    await callback.answer()


@router.message(EditStates.waiting_value)
async def task_edit_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    task_id = int(data["edit_task_id"])
    field = data["edit_field"]
    user_input = (message.text or "").strip()

    payload: Dict[str, Any] = {}
    if field == "title":
        if not user_input:
            await message.answer("Заголовок не может быть пустым.")
            return
        payload["title"] = user_input
    elif field == "desc":
        payload["description"] = None if user_input == "-" else user_input
    elif field == "due":
        if user_input == "-":
            payload["due_date"] = None
        else:
            parsed = parse_due(user_input)
            if parsed is None:
                await message.answer(
                    "Не похоже на дату. Примеры: «сегодня», «завтра», «+3», 15-10-2025, 15.10.2025, 2025-10-15 или «-»."
                )
                return
            payload["due_date"] = parsed
    else:
        await message.answer("Неизвестное поле обновления.")
        await state.clear()
        return

    resp = await TasksAPI.patch(message.from_user.id, task_id, payload)
    if resp.status_code not in (200, 204):
        await message.answer("❌ Не удалось обновить задачу.")
        await state.clear()
        return

    task = None
    if resp.status_code == 200:
        try:
            task = resp.json()
        except Exception:
            task = None
    if task is None:
        task_resp = await TasksAPI.get(message.from_user.id, task_id)
        if task_resp.status_code == 200:
            task = task_resp.json()

    edit_chat_id = data.get("edit_chat_id")
    edit_message_id = data.get("edit_message_id")
    if task and edit_chat_id and edit_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=edit_chat_id,
                message_id=edit_message_id,
                text=build_task_text(task),
                reply_markup=build_task_keyboard(task),
            )
        except TelegramBadRequest:
            await message.answer(build_task_text(task), reply_markup=build_task_keyboard(task))
    else:
        await message.answer("Обновлено", reply_markup=back_to_list_keyboard())

    await state.clear()
