from datetime import timedelta, date

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.database.redis_client import redis_client
from src.keyboards.task import task_actions, priority_keyboard, due_quick_keyboard
from src.keyboards.common import cancel_keyboard
from src.services.http_client import client
from src.utils.translations import STATUS_RU, PRIORITY_RU
from src.utils.dates import parse_due, format_due
from .states import TaskStates

router = Router()

# ----------------- UTILS -----------------
_ALLOWED_PRIORITIES = {"low", "medium", "high", "urgent"}
_NUM_TO_PRIORITY = {"1": "low", "2": "medium", "3": "high", "4": "urgent"}
_RU_PRIORITY_TO_EN = {"низкий": "low", "средний": "medium", "высокий": "high", "срочный": "urgent"}

def _fmt_priority(value: str) -> str:
    return PRIORITY_RU.get(value, value or "—")

def _fmt_status(value: str) -> str:
    return STATUS_RU.get(value, value or "—")

def _iso_today() -> str:
    return date.today().isoformat()

def _iso_plus_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


# ----------------- LIST TASKS -----------------
@router.message(Command("tasks"))
async def list_tasks(message: Message):
    user_id = message.from_user.id
    if not await redis_client.is_authenticated(user_id):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return

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
        status = _fmt_status(t.get("status", "todo"))
        priority = _fmt_priority(t.get("priority", "medium"))
        category = t.get("category", {}).get("name") if t.get("category") else "—"
        due_date = t.get("due_date")
        archived = bool(t.get("archived", False))
        task_id = t.get("id")

        text = f"📝 {title}\nСтатус: {status}\nПриоритет: {priority}\nКатегория: {category}"
        if due_date:
            text += f"\nДедлайн: {format_due(due_date)}"

        await message.answer(text, reply_markup=task_actions(task_id, archived))


# ----------------- CREATE TASK (FSM) -----------------
@router.message(Command("newtask"))
async def newtask_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await redis_client.is_authenticated(user_id):
        await message.answer("⚠️ Сначала войдите через /login")
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
    await message.answer("Введите описание (или отправьте дефис `-`, чтобы пропустить):", reply_markup=cancel_keyboard())


@router.message(TaskStates.create_description)
async def newtask_description(message: Message, state: FSMContext):
    desc_raw = (message.text or "").strip()
    description = None if desc_raw == "-" else desc_raw
    await state.update_data(description=description)
    await state.set_state(TaskStates.create_priority)
    await message.answer(
        "Выберите приоритет (кнопкой или цифрой):\n"
        "1 — низкий, 2 — средний, 3 — высокий, 4 — срочный\n"
        "или: low/medium/high/urgent либо по-русски: низкий/средний/высокий/срочный",
        reply_markup=priority_keyboard()
    )


@router.message(TaskStates.create_priority)
async def newtask_priority_text(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    if raw in _NUM_TO_PRIORITY:
        priority = _NUM_TO_PRIORITY[raw]
    elif raw == "-":
        priority = "medium"
    else:
        mapped = _RU_PRIORITY_TO_EN.get(raw, raw)
        if mapped not in _ALLOWED_PRIORITIES:
            await message.answer(
                "Некорректный приоритет. Допустимо: 1..4 | low/medium/high/urgent | "
                "низкий/средний/высокий/срочный",
                reply_markup=priority_keyboard()
            )
            return
        priority = mapped
    await state.update_data(priority=priority)
    await state.set_state(TaskStates.create_due_date)
    await message.answer(
        "Выберите быстрый вариант или введите дату в формате <b>DD-MM-YYYY</b>.\n"
        "Также принимается: «сегодня», «завтра», «+3», «15.10.2025», «YYYY-MM-DD», или «-» чтобы пропустить.",
        reply_markup=due_quick_keyboard()
    )


@router.callback_query(lambda c: c.data and c.data.startswith("prio:"))
async def newtask_priority_cb(callback: CallbackQuery, state: FSMContext):
    priority = callback.data.split(":", 1)[1]
    if priority not in _ALLOWED_PRIORITIES:
        await callback.answer("Некорректный приоритет", show_alert=True)
        return
    await state.update_data(priority=priority)
    await state.set_state(TaskStates.create_due_date)
    await callback.message.answer(
        "Выберите быстрый вариант или введите дату в формате <b>DD-MM-YYYY</b>.\n"
        "Также принимается: «сегодня», «завтра», «+3», «15.10.2025», «YYYY-MM-DD», или «-».",
        reply_markup=due_quick_keyboard()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("due:"))
async def newtask_due_quick(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    tag = callback.data.split(":", 1)[1]

    iso_date = None
    if tag == "today":
        iso_date = _iso_today()
    elif tag == "tomorrow":
        iso_date = _iso_plus_days(1)
    elif tag == "+3":
        iso_date = _iso_plus_days(3)
    elif tag == "none":
        iso_date = None

    form = await state.get_data()
    payload = {
        "title": form.get("title"),
        "description": form.get("description"),
        "priority": form.get("priority", "medium"),
    }
    if iso_date:
        payload["due_date"] = iso_date

    resp = await client.request(user_id, "POST", "/tasks/", json=payload)
    if resp.status_code in (200, 201):
        await callback.message.answer("✅ Задача создана. Посмотреть список — /tasks")
    else:
        await callback.message.answer("❌ Не удалось создать задачу. Попробуйте позже.")
    await state.clear()
    await callback.answer()


@router.message(TaskStates.create_due_date)
async def newtask_due_date_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    raw = (message.text or "").strip()

    iso_date = parse_due(raw)
    if iso_date is None and raw not in {"-", ""}:
        await message.answer(
            "Не похоже на дату. Примеры: «сегодня», «завтра», «+3», <b>15-10-2025</b>, 15.10.2025, 2025-10-15 или «-».",
            reply_markup=due_quick_keyboard()
        )
        return

    form = await state.get_data()
    payload = {
        "title": form.get("title"),
        "description": form.get("description"),
        "priority": form.get("priority", "medium"),
    }
    if iso_date:
        payload["due_date"] = iso_date

    resp = await client.request(user_id, "POST", "/tasks/", json=payload)
    if resp.status_code in (200, 201):
        await message.answer("✅ Задача создана. Посмотреть список — /tasks")
    else:
        await message.answer("❌ Не удалось создать задачу. Попробуйте позже.")
    await state.clear()


# ----------------- UPDATE TASK (FSM) -----------------
@router.callback_query(lambda c: c.data and c.data.startswith("task_update:"))
async def task_update_start(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":", 1)[1])
    await state.clear()
    await state.update_data(task_id=task_id)
    await state.set_state(TaskStates.update_field)
    await callback.message.answer(
        "Что обновить? Введите:\n"
        "- title\n"
        "- description\n"
        "- priority (1..4 | low/medium/high/urgent | низкий/средний/высокий/срочный)\n"
        "- due_date (<b>DD-MM-YYYY</b> | сегодня | завтра | +3 | -)\n",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


@router.message(TaskStates.update_field)
async def task_update_field(message: Message, state: FSMContext):
    field = (message.text or "").strip().lower()
    if field not in {"title", "description", "priority", "due_date"}:
        await message.answer("Неверное поле. Введите: title / description / priority / due_date",
                             reply_markup=cancel_keyboard())
        return
    await state.update_data(field=field)
    await state.set_state(TaskStates.update_value)
    if field == "priority":
        await message.answer(
            "Введите новый приоритет (1..4 | low/medium/high/urgent | низкий/средний/высокий/срочный):",
            reply_markup=priority_keyboard()
        )
    elif field == "due_date":
        await message.answer(
            "Введите новую дату в формате <b>DD-MM-YYYY</b> или выберите быстрый вариант:",
            reply_markup=due_quick_keyboard()
        )
    else:
        await message.answer(f"Введите новое значение для поля `{field}`:", reply_markup=cancel_keyboard())


@router.message(TaskStates.update_value)
async def task_update_value(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task_id = data.get("task_id")
    field = data.get("field")
    raw_value = (message.text or "").strip()

    payload = {}

    if field == "priority":
        if raw_value in _NUM_TO_PRIORITY:
            mapped = _NUM_TO_PRIORITY[raw_value]
        else:
            mapped = _RU_PRIORITY_TO_EN.get(raw_value.lower(), raw_value.lower())
        if mapped not in _ALLOWED_PRIORITIES:
            await message.answer(
                "Некорректный приоритет. Допустимо: 1..4 | low/medium/high/urgent | "
                "низкий/средний/высокий/срочный",
                reply_markup=priority_keyboard()
            )
            return
        payload["priority"] = mapped

    elif field == "due_date":
        iso_date = parse_due(raw_value)
        if iso_date is None and raw_value != "-":
            await message.answer(
                "Не похоже на дату. Примеры: «сегодня», «завтра», «+3», <b>15-10-2025</b>, 15.10.2025, 2025-10-15 или «-».",
                reply_markup=due_quick_keyboard()
            )
            return
        payload["due_date"] = iso_date

    else:
        payload[field] = raw_value

    resp = await client.request(user_id, "PUT", f"/tasks/{task_id}", json=payload)
    if resp.status_code == 200:
        await message.answer("✅ Задача обновлена. Посмотреть список — /tasks")
    else:
        await message.answer("❌ Не удалось обновить задачу.")
    await state.clear()


# ----------------- DELETE / ARCHIVE / RESTORE -----------------
@router.callback_query(lambda c: c.data and c.data.startswith("task_delete:"))
async def task_delete(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split(":", 1)[1])

    if not await redis_client.is_authenticated(user_id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
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
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
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
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    resp = await client.request(user_id, "POST", f"/tasks/{task_id}/restore")
    if resp.status_code in (200, 204):
        try:
            await callback.message.edit_text("♻️ Задача восстановлена")
        except Exception:
            await callback.answer("✅ Задача восстановлена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось восстановить задачу", show_alert=True)
