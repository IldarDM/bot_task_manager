from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.database.redis_client import redis_client
from src.keyboards.common import cancel_keyboard
from src.keyboards.list_filters import (
    categories_selector,
    filters_menu,
    priorities_selector,
    sort_keyboard,
    statuses_selector,
)
from src.keyboards.main_menu import (
    NEW_TASK_BUTTON,
    REFRESH_BUTTON,
    TASKS_BUTTON,
    main_menu_keyboard,
)
from src.keyboards.task_actions import back_to_list_keyboard
from src.keyboards.task_creation import (
    creation_category_keyboard,
    creation_due_keyboard,
    creation_priority_keyboard,
)
from src.keyboards.task_editor import (
    task_edit_categories as task_edit_categories_keyboard,
    task_edit_menu as task_edit_menu_markup,
    task_edit_priority as task_edit_priority_keyboard,
)
from src.presentation.task_card import build_task_keyboard, build_task_text
from src.presentation.task_list import (
    GROUPS,
    GROUP_LABELS,
    build_group_summary,
    build_header,
    build_list_keyboard,
    group_tasks,
)
from src.routes.states import TaskStates
from src.services.categories_api import CategoriesAPI
from src.services.tasks_api import TasksAPI
from src.utils.dates import parse_due

router = Router()

DEFAULT_LIMIT = 10
GROUP_LIMIT = 8

PRIORITY_ALIASES = {
    "1": "low",
    "низкий": "low",
    "низкий приоритет": "low",
    "low": "low",
    "2": "medium",
    "средний": "medium",
    "medium": "medium",
    "3": "high",
    "высокий": "high",
    "high": "high",
    "4": "urgent",
    "срочный": "urgent",
    "срочно": "urgent",
    "urgent": "urgent",
}


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
    summary = build_group_summary(groups)
    if summary:
        hint = "Выберите задачу или воспользуйтесь кнопками ниже."
        text = (
            "🗂 <b>Мои задачи</b>\n"
            f"{header}\n\n"
            f"{summary}\n\n"
            f"{hint}"
        )
    else:
        text = (
            "🗂 <b>Мои задачи</b>\n"
            f"{header}\n\n"
            "Пока задач нет. Нажмите «➕ Задача», чтобы добавить первую."
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


async def _start_task_creation(origin: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TaskStates.create_title)
    prompt_target: Message
    origin_info: Optional[Dict[str, int]] = None

    if isinstance(origin, CallbackQuery):
        prompt_target = origin.message
        origin_info = {
            "chat_id": origin.message.chat.id,
            "message_id": origin.message.message_id,
        }
    else:
        prompt_target = origin

    await state.update_data(
        task_create_origin=origin_info,
        new_task={},
    )
    await prompt_target.answer(
        "Введите название новой задачи:",
        reply_markup=cancel_keyboard(),
    )


async def _send_step_message(target: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _prompt_priority_step(target: Message | CallbackQuery, state: FSMContext, selected: Optional[str] = None) -> None:
    await state.set_state(TaskStates.create_priority)
    await _send_step_message(
        target,
        "Выберите приоритет для новой задачи:",
        creation_priority_keyboard(selected),
    )


async def _prompt_category_step(
    target: Message | CallbackQuery,
    state: FSMContext,
    user_id: int,
    page: int = 0,
) -> None:
    categories = await CategoriesAPI.list(user_id)
    await state.update_data(create_categories=categories, create_category_page=page)

    data = await state.get_data()
    new_task = data.get("new_task", {})
    if not categories:
        new_task["category_id"] = None
        await state.update_data(new_task=new_task, create_categories=None)
        await _prompt_due_step(target, state)
        return

    await state.update_data(new_task=new_task)
    await state.set_state(TaskStates.create_category)
    await _send_step_message(
        target,
        "Выберите категорию для задачи (или нажмите «Без категории»):",
        creation_category_keyboard(categories, page=page),
    )


async def _prompt_due_step(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TaskStates.create_due_date)
    await _send_step_message(
        target,
        "Выберите дедлайн или укажите дату вручную:",
        creation_due_keyboard(),
    )


async def _finalize_task_creation(source: Message | CallbackQuery, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    new_task = data.get("new_task") or {}

    payload = {
        key: value
        for key, value in {
            "title": new_task.get("title"),
            "description": new_task.get("description"),
            "priority": new_task.get("priority"),
            "category_id": new_task.get("category_id"),
            "due_date": new_task.get("due_date"),
        }.items()
        if value not in (None, "")
    }

    resp = await TasksAPI.create(user_id, payload)

    await state.update_data(new_task=None, create_categories=None, create_category_page=0)
    await state.set_state(None)

    if resp.status_code not in (200, 201):
        if isinstance(source, CallbackQuery):
            await source.message.answer(
                "❌ Не удалось создать задачу. Попробуйте позже.",
                reply_markup=main_menu_keyboard(),
            )
            await source.answer("Ошибка создания", show_alert=True)
        else:
            await source.answer(
                "❌ Не удалось создать задачу. Попробуйте позже.",
                reply_markup=main_menu_keyboard(),
            )
        return

    if isinstance(source, CallbackQuery):
        await source.message.answer("✅ Задача создана!", reply_markup=main_menu_keyboard())
        await tasks_entry(source.message, state)
        await source.answer("Готово")
    else:
        await source.answer("✅ Задача создана!", reply_markup=main_menu_keyboard())
        await tasks_entry(source, state)


@router.message(Command("tasks"))
async def tasks_entry(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        return
    profile = await _load_profile(state)
    profile.reset_paging()
    await _store_profile(state, profile)
    await _render_list(message, profile)


@router.message(F.text == TASKS_BUTTON)
async def tasks_from_menu(message: Message, state: FSMContext) -> None:
    await tasks_entry(message, state)


@router.message(F.text == REFRESH_BUTTON)
async def tasks_refresh_button(message: Message, state: FSMContext) -> None:
    await tasks_entry(message, state)


@router.message(F.text == NEW_TASK_BUTTON)
async def task_new_from_menu(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        return
    await _start_task_creation(message, state)


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


@router.callback_query(F.data.startswith("tl:grp:info:"))
async def tl_group_quick_filter(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[-1]
    profile = await _load_profile(state)
    changed = False

    if key == "urgent":
        profile.view = "active"
        profile.status = ["todo", "in_progress"]
        profile.priority = ["high", "urgent"]
        profile.is_overdue = None
        profile.due_date_from = profile.due_date_to = None
        profile.sort_by, profile.sort_order = "due_date", "asc"
        changed = True
    elif key == "overdue":
        profile.view = "active"
        profile.status = ["todo", "in_progress"]
        profile.priority = []
        profile.is_overdue = True
        profile.due_date_from = profile.due_date_to = None
        profile.sort_by, profile.sort_order = "due_date", "asc"
        changed = True
    elif key == "today":
        from datetime import datetime, date

        today = date.today()
        start = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat()
        end = datetime(today.year, today.month, today.day, 23, 59, 59).isoformat()
        profile.view = "active"
        profile.status = ["todo", "in_progress"]
        profile.priority = []
        profile.is_overdue = None
        profile.due_date_from, profile.due_date_to = start, end
        profile.sort_by, profile.sort_order = "due_date", "asc"
        changed = True
    elif key == "done":
        profile.view = "active"
        profile.status = ["done"]
        profile.priority = []
        profile.is_overdue = None
        profile.due_date_from = profile.due_date_to = None
        profile.sort_by, profile.sort_order = "updated_at", "desc"
        changed = True
    elif key == "archived":
        profile.view = "archived"
        profile.status = []
        profile.priority = []
        profile.is_overdue = None
        profile.due_date_from = profile.due_date_to = None
        profile.sort_by, profile.sort_order = "updated_at", "desc"
        changed = True
    elif key == "rest":
        profile.view = "active"
        profile.status = ["todo", "in_progress"]
        profile.priority = []
        profile.is_overdue = None
        profile.due_date_from = profile.due_date_to = None
        profile.sort_by, profile.sort_order = "due_date", "asc"
        changed = True

    if changed:
        profile.reset_paging()
        await _store_profile(state, profile)
        await _render_list(callback, profile)
        await callback.answer(f"Фильтр «{GROUP_LABELS.get(key, key)}» активирован")
    else:
        await callback.answer("Здесь пока нечего переключать")


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


@router.callback_query(F.data == "tl:home")
async def tl_home(callback: CallbackQuery) -> None:
    await callback.message.answer("🏠 Главное меню доступно снизу.", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "task:new")
async def task_new_inline(callback: CallbackQuery, state: FSMContext) -> None:
    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return
    await _start_task_creation(callback, state)
    await callback.answer()


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


@router.message(TaskStates.create_title)
async def task_create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите название задачи:", reply_markup=cancel_keyboard())
        return

    if not await _ensure_authenticated(message):
        await state.set_state(None)
        return

    if not await redis_client.is_authenticated(message.from_user.id):
        await state.set_state(None)
        await message.answer("⚠️ Сначала войдите через /login.", reply_markup=main_menu_keyboard())
        return

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["title"] = title
    await state.update_data(new_task=new_task, create_categories=None)

    await state.set_state(TaskStates.create_description)
    await message.answer(
        "Введите описание задачи (или «-», чтобы пропустить):",
        reply_markup=cancel_keyboard(),
    )


@router.message(TaskStates.create_description)
async def task_create_description(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        await state.set_state(None)
        return

    text = (message.text or "").strip()
    description = None if text in {"", "-"} else text

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["description"] = description
    await state.update_data(new_task=new_task)

    await _prompt_priority_step(message, state)


@router.message(TaskStates.create_priority)
async def task_create_priority(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        await state.set_state(None)
        return

    raw = (message.text or "").strip().lower()
    priority: Optional[str]
    if raw in {"", "-"}:
        priority = None
    else:
        priority = PRIORITY_ALIASES.get(raw)
        if priority is None:
            await message.answer(
                "Не понял приоритет. Введите 1-4 или low/medium/high/urgent (можно по-русски).",
                reply_markup=cancel_keyboard(),
            )
            return

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["priority"] = priority
    await state.update_data(new_task=new_task)

    await _prompt_category_step(message, state, message.from_user.id)


@router.callback_query(F.data.startswith("task:create:prio:"))
async def task_create_priority_callback(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[-1]
    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["priority"] = None if value == "skip" else value
    await state.update_data(new_task=new_task)

    await callback.message.edit_reply_markup(reply_markup=None)
    await _prompt_category_step(callback, state, callback.from_user.id)


@router.message(TaskStates.create_category)
async def task_create_category(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        await state.set_state(None)
        return

    data = await state.get_data()
    categories: List[Dict] = data.get("create_categories") or []
    if not categories:
        categories = await CategoriesAPI.list(message.from_user.id)
        await state.update_data(create_categories=categories)

    mapping: Dict[str, Dict] = {
        str(idx + 1): cat for idx, cat in enumerate(categories)
    }

    new_task = data.get("new_task", {})
    raw = (message.text or "").strip().lower()
    if raw in {"", "-", "0", "без", "none"}:
        new_task["category_id"] = None
    elif raw in mapping:
        cat_id_value = mapping[raw].get("id")
        try:
            cat_id_value = int(cat_id_value)
        except (TypeError, ValueError):
            pass
        new_task["category_id"] = cat_id_value
    else:
        await message.answer(
            "Не удалось распознать категорию. Используйте кнопки или отправьте номер из списка:",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(new_task=new_task)
    await _prompt_due_step(message, state)


@router.callback_query(F.data.startswith("task:create:cat:page:"))
async def task_create_category_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    categories: List[Dict] = data.get("create_categories") or []
    if not categories:
        categories = await CategoriesAPI.list(callback.from_user.id)
        await state.update_data(create_categories=categories)

    kb = creation_category_keyboard(categories, page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await state.update_data(create_category_page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("task:create:cat:set:"))
async def task_create_category_select(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id_raw = callback.data.split(":")[-1]
    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    try:
        cat_id = int(cat_id_raw)
    except ValueError:
        cat_id = cat_id_raw

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["category_id"] = cat_id
    await state.update_data(new_task=new_task, create_categories=None)

    await callback.message.edit_reply_markup(reply_markup=None)
    await _prompt_due_step(callback, state)


@router.callback_query(F.data == "task:create:cat:none")
async def task_create_category_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["category_id"] = None
    await state.update_data(new_task=new_task, create_categories=None)

    await callback.message.edit_reply_markup(reply_markup=None)
    await _prompt_due_step(callback, state)


@router.message(TaskStates.create_due_date)
async def task_create_due_date(message: Message, state: FSMContext) -> None:
    if not await _ensure_authenticated(message):
        await state.set_state(None)
        return

    text = (message.text or "").strip()
    due: Optional[str]
    if text in {"", "-"}:
        due = None
    else:
        due = parse_due(text)
        if due is None:
            await message.answer(
                "Не похоже на дату. Примеры: «сегодня», «завтра», «+3», 15-10-2025, 15.10.2025, 2025-10-15 или «-».",
                reply_markup=cancel_keyboard(),
            )
            return

    data = await state.get_data()
    new_task = data.get("new_task", {})
    new_task["due_date"] = due
    await state.update_data(new_task=new_task)

    await _finalize_task_creation(message, state, message.from_user.id)


@router.callback_query(F.data.startswith("task:create:due:"))
async def task_create_due_callback(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[-1]
    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    data = await state.get_data()
    new_task = data.get("new_task", {})

    if action == "manual":
        await state.set_state(TaskStates.create_due_date)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Введите дату вручную (YYYY-MM-DD, DD.MM.YYYY, сегодня/завтра/+3) или «-», чтобы пропустить:",
            reply_markup=cancel_keyboard(),
        )
        await callback.answer()
        return

    if action == "skip":
        new_task["due_date"] = None
    else:
        mapping = {
            "today": "сегодня",
            "tomorrow": "завтра",
            "+3": "+3",
            "+7": "+7",
        }
        due_text = mapping.get(action)
        if due_text is None:
            await callback.answer("Неизвестный вариант", show_alert=True)
            return
        due_iso = parse_due(due_text)
        if due_iso is None:
            await callback.answer("Не удалось распознать дату", show_alert=True)
            return
        new_task["due_date"] = due_iso

    await state.update_data(new_task=new_task)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _finalize_task_creation(callback, state, callback.from_user.id)

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
