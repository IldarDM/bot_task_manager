from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from src.database.redis_client import redis_client
from src.keyboards.common import cancel_keyboard, inline_back_to_menu
from src.keyboards.task import (
    task_actions,
    priority_keyboard,
    due_quick_keyboard,
    edit_menu_keyboard,
    priority_keyboard_for_task,
    due_quick_keyboard_for_task,
    categories_keyboard_for_task,
    categories_keyboard_for_create,
)
from src.services.http_client import client
from src.utils.dates import parse_due, format_due
from src.utils.translations import tr_priority, tr_status
from .states import TaskStates

router = Router()

_ALLOWED_PRIORITIES = {"low", "medium", "high", "urgent"}
_NUM_TO_PRIORITY = {"1": "low", "2": "medium", "3": "high", "4": "urgent"}
_RU_PRIORITY_TO_EN = {
    "низкий": "low",
    "средний": "medium",
    "высокий": "high",
    "срочный": "urgent",
}

MSG_NEED_LOGIN = "⚠️ Вы не авторизованы. Используйте /login"
MSG_CREATE_HINT = (
    "Выберите быстрый вариант или введите дату в формате <b>DD-MM-YYYY</b>.\n"
    "Также принимается: «сегодня», «завтра», «+3», «15.10.2025», «YYYY-MM-DD», или «-» чтобы пропустить."
)
MSG_DATE_INVALID = (
    "Не похоже на дату. Примеры: «сегодня», «завтра», «+3», <b>15-10-2025</b>, 15.10.2025, 2025-10-15 или «-»."
)


# ----------------- Вспомогательные функции -----------------

def _iso_today() -> str:
    return date.today().isoformat()


def _iso_plus_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


async def _ensure_auth_or_warn(message: Message) -> bool:
    if not await redis_client.is_authenticated(message.from_user.id):
        await message.answer(MSG_NEED_LOGIN)
        return False
    return True


def _parse_priority(raw: str) -> Optional[str]:
    t = (raw or "").strip().lower()
    if t in _NUM_TO_PRIORITY:
        return _NUM_TO_PRIORITY[t]
    if t == "-":
        return "medium"
    mapped = _RU_PRIORITY_TO_EN.get(t, t)
    return mapped if mapped in _ALLOWED_PRIORITIES else None


def _build_create_payload(form: Dict[str, Any], due_iso: Optional[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "title": form.get("title"),
        "description": form.get("description"),
        "priority": form.get("priority", "medium"),
    }
    if form.get("category_id") is not None:
        payload["category_id"] = form["category_id"]
    if due_iso:
        payload["due_date"] = due_iso
    return payload


async def _fetch_categories(user_id: int) -> List[Dict]:
    resp = await client.request(user_id, "GET", "/categories/")
    if resp.status_code != 200:
        return []
    data = resp.json() or []
    items = data if isinstance(data, list) else []
    # исключаем служебную категорию
    filtered = [c for c in items if str(c.get("name", "")).strip().lower() != "uncategorized"]
    return filtered


async def _fetch_task(user_id: int, task_id: int) -> Optional[Dict[str, Any]]:
    resp = await client.request(user_id, "GET", f"/tasks/{task_id}")
    if resp.status_code != 200:
        return None
    return resp.json()


def _build_task_text(task: dict) -> str:
    title = task.get("title", "Без названия")
    status = tr_status(task.get("status"))
    priority = tr_priority(task.get("priority"))
    category = task.get("category", {}).get("name") if task.get("category") else "—"
    due_date = task.get("due_date")
    text = (
        f"📝 {title}\n"
        f"Статус: {status}\n"
        f"Приоритет: {priority}\n"
        f"Категория: {category}"
    )
    if due_date:
        text += f"\nДедлайн: {format_due(due_date)}"
    return text


async def _edit_message_safe_msg(msg: Message, text: str, reply_markup=None) -> None:
    try:
        if (msg.text or "") == text:
            await msg.edit_reply_markup(reply_markup=reply_markup)
        else:
            await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


async def _edit_message_by_id(bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            try:
                await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
            except TelegramBadRequest as ee:
                if "message is not modified" in str(ee).lower():
                    return
                raise
        else:
            raise


async def _show_task_card(message_or_cb: Message | CallbackQuery, task_id: int) -> None:
    user_id = message_or_cb.from_user.id
    task = await _fetch_task(user_id, task_id)
    if not task:
        text = "Задача не найдена."
        kb = None
    else:
        text = _build_task_text(task)
        status_raw = task.get("status")
        archived = bool(task.get("archived", False))
        kb = task_actions(task_id, archived, status_raw)

    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=kb)
    else:
        await _edit_message_safe_msg(message_or_cb.message, text, reply_markup=kb)


async def _show_edit_menu(message_or_cb: Message | CallbackQuery, task_id: int) -> None:
    text = "Выберите, что изменить:"
    kb = edit_menu_keyboard(task_id)

    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=kb)
        return

    await _edit_message_safe_msg(message_or_cb.message, text, reply_markup=kb)


# ----------------- Список задач -----------------

@router.message(Command("tasks"))
async def list_tasks(message: Message):
    if not await _ensure_auth_or_warn(message):
        return

    user_id = message.from_user.id
    resp = await client.request(user_id, "GET", "/tasks/")
    if resp.status_code != 200:
        await message.answer("❌ Ошибка получения задач. Попробуйте позже или /login")
        return

    data = resp.json() or {}
    tasks = data.get("tasks", data if isinstance(data, list) else [])
    if not tasks:
        await message.answer("У вас пока нет задач 📝\nСоздать — /newtask")
        return

    for t in tasks:
        if not isinstance(t, dict):
            await message.answer(f"📝 {t}")
            continue

        title = t.get("title", "Без названия")
        status_raw = t.get("status")
        status = tr_status(status_raw)
        priority = tr_priority(t.get("priority"))
        category = t.get("category", {}).get("name") if t.get("category") else "—"
        due_date = t.get("due_date")
        archived = bool(t.get("archived", False))
        task_id = t.get("id")

        text = (
            f"📝 {title}\n"
            f"Статус: {status}\n"
            f"Приоритет: {priority}\n"
            f"Категория: {category}"
        )
        if due_date:
            text += f"\nДедлайн: {format_due(due_date)}"

        await message.answer(text, reply_markup=task_actions(task_id, archived, status_raw))


# ----------------- Создание задачи (FSM) -----------------

@router.message(Command("newtask"))
async def newtask_start(message: Message, state: FSMContext):
    if not await _ensure_auth_or_warn(message):
        return
    await state.clear()
    await state.set_state(TaskStates.create_title)
    await message.answer("Введите заголовок задачи:", reply_markup=cancel_keyboard())


@router.message(TaskStates.create_title)
async def newtask_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Введите заголовок:", reply_markup=cancel_keyboard())
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.create_description)
    await message.answer(
        "Введите описание (или отправьте дефис `-`, чтобы пропустить):",
        reply_markup=cancel_keyboard(),
    )


@router.message(TaskStates.create_description)
async def newtask_description(message: Message, state: FSMContext):
    desc_raw = (message.text or "").strip()
    description = None if desc_raw == "-" else desc_raw
    await state.update_data(description=description)
    await state.set_state(TaskStates.create_priority)
    await message.answer("Выберите приоритет (кнопкой или цифрой)", reply_markup=priority_keyboard())


@router.message(TaskStates.create_priority)
async def newtask_priority_text(message: Message, state: FSMContext):
    priority = _parse_priority(message.text or "")
    if not priority:
        await message.answer("Некорректный приоритет. Допустимо: 1..4", reply_markup=priority_keyboard())
        return
    await state.update_data(priority=priority)
    await state.set_state(TaskStates.create_category)

    user_id = message.from_user.id
    cats = await _fetch_categories(user_id)
    if not cats:
        await message.answer("Категории не найдены. Можно продолжить без категории.", reply_markup=due_quick_keyboard())
        await state.set_state(TaskStates.create_due_date)
        return

    await message.answer("Выберите категорию (или «Пропустить»):", reply_markup=categories_keyboard_for_create(cats))


@router.callback_query(lambda c: c.data and c.data.startswith("prio:"))
async def newtask_priority_cb(callback: CallbackQuery, state: FSMContext):
    priority = callback.data.split(":", 1)[1]
    if priority not in _ALLOWED_PRIORITIES:
        await callback.answer("Некорректный приоритет", show_alert=True)
        return
    await state.update_data(priority=priority)
    await state.set_state(TaskStates.create_category)

    cats = await _fetch_categories(callback.from_user.id)
    if not cats:
        await callback.message.answer("Категории не найдены. Можно продолжить без категории.", reply_markup=due_quick_keyboard())
        await state.set_state(TaskStates.create_due_date)
        await callback.answer()
        return

    await callback.message.edit_text("Выберите категорию (или «Пропустить»):", reply_markup=categories_keyboard_for_create(cats))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ccat:"))
async def newtask_category_cb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data.split(":")
    action = data[1]

    if action == "page":
        page = int(data[2])
        cats = await _fetch_categories(user_id)
        await callback.message.edit_reply_markup(reply_markup=categories_keyboard_for_create(cats, page=page))
        await callback.answer()
        return

    if action == "set":
        category_id = int(data[2])
        await state.update_data(category_id=category_id)
    elif action == "none":
        await state.update_data(category_id=None)
    elif action == "skip":
        pass

    await state.set_state(TaskStates.create_due_date)
    await callback.message.edit_text(MSG_CREATE_HINT, reply_markup=due_quick_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("due:"))
async def newtask_due_quick(callback: CallbackQuery, state: FSMContext):
    tag = callback.data.split(":", 1)[1]

    due_iso: Optional[str] = None
    if tag == "today":
        due_iso = _iso_today()
    elif tag == "tomorrow":
        due_iso = _iso_plus_days(1)
    elif tag == "+3":
        due_iso = _iso_plus_days(3)
    elif tag == "none":
        due_iso = None

    form = await state.get_data()
    payload = _build_create_payload(form, due_iso)

    resp = await client.request(callback.from_user.id, "POST", "/tasks/", json=payload)
    if resp.status_code in (200, 201):
        await callback.message.answer("✅ Задача создана. Посмотреть список — /tasks")
    else:
        await callback.message.answer("❌ Не удалось создать задачу. Попробуйте позже.")
    await state.clear()
    await callback.answer()


@router.message(TaskStates.create_due_date)
async def newtask_due_date_text(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    due_iso = parse_due(raw)

    if due_iso is None and raw not in {"-", ""}:
        await message.answer(MSG_DATE_INVALID, reply_markup=due_quick_keyboard())
        return

    form = await state.get_data()
    payload = _build_create_payload(form, due_iso)

    resp = await client.request(message.from_user.id, "POST", "/tasks/", json=payload)
    if resp.status_code in (200, 201):
        await message.answer("✅ Задача создана. Посмотреть список — /tasks")
    else:
        await message.answer("❌ Не удалось создать задачу. Попробуйте позже.")
    await state.clear()


# ----------------- Быстрый редактор -----------------

@router.callback_query(lambda c: c.data and c.data.startswith("task_update:"))
async def task_update_open(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":", 1)[1])
    await state.update_data(
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
        task_id=task_id,
    )
    await _show_edit_menu(callback, task_id)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit:menu:"))
async def task_update_menu(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await state.update_data(
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
        task_id=task_id,
    )
    await _show_edit_menu(callback, task_id)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit:cancel:"))
async def task_update_cancel(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await _show_task_card(callback, task_id)
    await state.clear()
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit:back:"))
async def task_update_back(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await _show_task_card(callback, task_id)
    await callback.answer()


# --- Заголовок ---

@router.callback_query(lambda c: c.data and c.data.startswith("edit:title:"))
async def task_edit_title_start(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await state.set_state(TaskStates.update_title)
    await state.update_data(
        task_id=task_id,
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
    )
    await callback.message.edit_text("Введите новый заголовок:", reply_markup=inline_back_to_menu(task_id))
    await callback.answer()


@router.message(TaskStates.update_title)
async def task_edit_title_apply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task_id = int(data["task_id"])
    chat_id = int(data["origin_chat_id"])
    message_id = int(data["origin_message_id"])

    title = (message.text or "").strip()
    if not title:
        await _edit_message_by_id(
            message.bot, chat_id, message_id,
            "Заголовок не может быть пустым. Введите заголовок:",
            reply_markup=inline_back_to_menu(task_id),
        )
        return

    resp = await client.request(user_id, "PATCH", f"/tasks/{task_id}", json={"title": title})
    await state.clear()

    if resp.status_code == 200:
        await _edit_message_by_id(message.bot, chat_id, message_id, "Выберите, что изменить:", reply_markup=edit_menu_keyboard(task_id))
    else:
        await _edit_message_by_id(message.bot, chat_id, message_id, "❌ Не удалось обновить заголовок.", reply_markup=edit_menu_keyboard(task_id))


# --- Описание ---

@router.callback_query(lambda c: c.data and c.data.startswith("edit:desc:"))
async def task_edit_desc_start(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await state.set_state(TaskStates.update_desc)
    await state.update_data(
        task_id=task_id,
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
    )
    await callback.message.edit_text("Введите новое описание (или «-» чтобы очистить):", reply_markup=inline_back_to_menu(task_id))
    await callback.answer()


@router.message(TaskStates.update_desc)
async def task_edit_desc_apply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task_id = int(data["task_id"])
    chat_id = int(data["origin_chat_id"])
    message_id = int(data["origin_message_id"])

    raw = (message.text or "").strip()
    description = None if raw == "-" else raw

    resp = await client.request(user_id, "PATCH", f"/tasks/{task_id}", json={"description": description})
    await state.clear()

    if resp.status_code == 200:
        await _edit_message_by_id(message.bot, chat_id, message_id, "Выберите, что изменить:", reply_markup=edit_menu_keyboard(task_id))
    else:
        await _edit_message_by_id(message.bot, chat_id, message_id, "❌ Не удалось обновить описание.", reply_markup=edit_menu_keyboard(task_id))


# --- Приоритет (инлайн) ---

@router.callback_query(lambda c: c.data and c.data.startswith("edit:prio:"))
async def task_edit_prio_open(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await state.update_data(
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
        task_id=task_id,
    )
    await callback.message.edit_text("Выберите приоритет:", reply_markup=priority_keyboard_for_task(task_id))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("eprio:"))
async def task_edit_prio_apply(callback: CallbackQuery):
    _, task_id, value = callback.data.split(":")
    task_id = int(task_id)

    if value not in _ALLOWED_PRIORITIES:
        await callback.answer("Некорректный приоритет", show_alert=True)
        return

    resp = await client.request(callback.from_user.id, "PATCH", f"/tasks/{task_id}", json={"priority": value})
    if resp.status_code == 200:
        await callback.answer("✅ Обновлено")
        await _show_edit_menu(callback, task_id)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


# --- Дедлайн (инлайн + ручной ввод) ---

@router.callback_query(lambda c: c.data and c.data.startswith("edit:due:"))
async def task_edit_due_open(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    await state.update_data(
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
        task_id=task_id,
    )
    await callback.message.edit_text("Выберите дату или введите вручную:", reply_markup=due_quick_keyboard_for_task(task_id))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edue:") and c.data.split(":")[2] == "manual")
async def task_edit_due_manual_start(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[1])
    await state.set_state(TaskStates.update_due_manual)
    await state.update_data(
        task_id=task_id,
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
    )
    await callback.message.edit_text(
        "Введите дату в формате <b>DD-MM-YYYY</b> (или «-» чтобы снять дедлайн):",
        reply_markup=inline_back_to_menu(task_id),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edue:") and c.data.split(":")[2] != "manual")
async def task_edit_due_apply(callback: CallbackQuery):
    _, task_id, tag = callback.data.split(":")
    task_id = int(task_id)

    due_iso: Optional[str] = None
    if tag == "today":
        due_iso = _iso_today()
    elif tag == "tomorrow":
        due_iso = _iso_plus_days(1)
    elif tag == "+3":
        due_iso = _iso_plus_days(3)
    elif tag == "none":
        due_iso = None

    payload = {"due_date": due_iso}
    resp = await client.request(callback.from_user.id, "PATCH", f"/tasks/{task_id}", json=payload)
    if resp.status_code == 200:
        await callback.answer("✅ Обновлено")
        await _show_edit_menu(callback, task_id)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(TaskStates.update_due_manual)
async def task_edit_due_manual_apply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task_id = int(data["task_id"])
    chat_id = int(data["origin_chat_id"])
    message_id = int(data["origin_message_id"])

    raw = (message.text or "").strip()
    due_iso = parse_due(raw)

    if due_iso is None and raw != "-":
        await _edit_message_by_id(
            message.bot, chat_id, message_id,
            MSG_DATE_INVALID,
            reply_markup=inline_back_to_menu(task_id),
        )
        return

    payload = {"due_date": due_iso}
    resp = await client.request(user_id, "PATCH", f"/tasks/{task_id}", json=payload)
    await state.clear()

    if resp.status_code == 200:
        await _edit_message_by_id(message.bot, chat_id, message_id, "Выберите, что изменить:", reply_markup=edit_menu_keyboard(task_id))
    else:
        await _edit_message_by_id(message.bot, chat_id, message_id, "❌ Не удалось обновить дату.", reply_markup=edit_menu_keyboard(task_id))


# --- Категория (инлайн с пагинацией) ---

@router.callback_query(lambda c: c.data and c.data.startswith("edit:cat:"))
async def task_edit_cat_open(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[2])
    cats = await _fetch_categories(callback.from_user.id)
    if not cats:
        await callback.answer("Категорий нет", show_alert=True)
        return
    await state.update_data(
        origin_chat_id=callback.message.chat.id,
        origin_message_id=callback.message.message_id,
        task_id=task_id,
    )
    await callback.message.edit_text("Выберите категорию:", reply_markup=categories_keyboard_for_task(task_id, cats))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ecat:"))
async def task_edit_cat_apply(callback: CallbackQuery):
    _, task_id, action, param = callback.data.split(":")
    task_id = int(task_id)

    if action == "page":
        page = int(param)
        cats = await _fetch_categories(callback.from_user.id)
        await callback.message.edit_reply_markup(reply_markup=categories_keyboard_for_task(task_id, cats, page=page))
        await callback.answer()
        return

    if action == "set":
        category_id = int(param)
        payload = {"category_id": category_id}
    elif action == "none":
        payload = {"category_id": None}
    else:
        await callback.answer("Некорректное действие", show_alert=True)
        return

    resp = await client.request(callback.from_user.id, "PATCH", f"/tasks/{task_id}", json=payload)
    if resp.status_code == 200:
        await callback.answer("✅ Обновлено")
        await _show_edit_menu(callback, task_id)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


# ----------------- Статусы, удаление, архив -----------------

@router.callback_query(lambda c: c.data and c.data.startswith("task_done:"))
async def task_mark_done(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    resp = await client.request(user_id, "PATCH", f"/tasks/{task_id}", json={"status": "done"})
    if resp.status_code == 200:
        await callback.answer("✅ Отмечено как выполнено")
        await _show_task_card(callback, task_id)
    else:
        await callback.answer("❌ Не удалось изменить статус", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("task_reopen:"))
async def task_mark_reopen(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    resp = await client.request(user_id, "PATCH", f"/tasks/{task_id}", json={"status": "in_progress"})
    if resp.status_code == 200:
        await callback.answer("↩️ Вернули в работу")
        await _show_task_card(callback, task_id)
    else:
        await callback.answer("❌ Не удалось изменить статус", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("task_delete:"))
async def task_delete(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    if not await redis_client.is_authenticated(user_id):
        await callback.answer(MSG_NEED_LOGIN, show_alert=True)
        return

    resp = await client.request(user_id, "DELETE", f"/tasks/{task_id}")
    if resp.status_code in (200, 204):
        try:
            await callback.message.edit_text("🗑 Задача удалена")
        except Exception:
            await callback.answer("✅ Задача удалена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось удалить задачу", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("task_archive:"))
async def task_archive(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    if not await redis_client.is_authenticated(user_id):
        await callback.answer(MSG_NEED_LOGIN, show_alert=True)
        return

    resp = await client.request(user_id, "POST", f"/tasks/{task_id}/archive")
    if resp.status_code in (200, 204):
        try:
            await callback.message.edit_text("📦 Задача архивирована")
        except Exception:
            await callback.answer("✅ Задача архивирована", show_alert=True)
    else:
        await callback.answer("❌ Не удалось архивировать задачу", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("task_restore:"))
async def task_restore(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    if not await redis_client.is_authenticated(user_id):
        await callback.answer(MSG_NEED_LOGIN, show_alert=True)
        return

    resp = await client.request(user_id, "POST", f"/tasks/{task_id}/restore")
    if resp.status_code in (200, 204):
        try:
            await callback.message.edit_text("♻️ Задача восстановлена")
        except Exception:
            await callback.answer("✅ Задача восстановлена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось восстановить задачу", show_alert=True)
