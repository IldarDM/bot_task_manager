import httpx

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from src.keyboards.task import task_actions
from src.database.redis_client import redis_client
from src.database.states import FSMState, UserState
from ..config import settings

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"

# ----------------- LIST TASKS -----------------
@router.message(Command("tasks"))
async def list_tasks(message: Message):
    user_id = message.from_user.id
    token = await redis_client.get_user_token(user_id)
    if not token:
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_URL}/tasks/",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code == 401:
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
        return
    elif resp.status_code != 200:
        await message.answer("❌ Ошибка получения задач.")
        return

    data = resp.json()
    tasks = data.get("tasks", [])

    if not tasks:
        await message.answer("У вас пока нет задач 📝")
        return

    for t in tasks:
        if isinstance(t, dict):
            title = t.get("title", "Без названия")
            status = t.get("status", "unknown")
            priority = t.get("priority", "—")
            category = t.get("category", {}).get("name") if t.get("category") else "—"
            due_date = t.get("due_date")
            archived = t.get("archived", False)
            task_id = t.get("id")

            text = f"📝 {title}\nСтатус: {status}\nПриоритет: {priority}\nКатегория: {category}"
            if due_date:
                text += f"\nДедлайн: {due_date}"

            await message.answer(text, reply_markup=task_actions(task_id, archived))
        else:
            await message.answer(f"📝 {t}")

# ----------------- CREATE TASK -----------------
@router.message(Command("create_task"))
async def task_create_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_fsm_step(user_id, FSMState.TASK_CREATE_TITLE)
    await message.answer("Введите заголовок задачи:")


# ----------------- STUB CALLBACKS -----------------
@router.callback_query(lambda c: c.data and c.data.startswith("task_delete:"))
async def task_delete_stub(callback: CallbackQuery):
    await callback.answer("Удаление —  реализуется.", show_alert=True)

@router.callback_query(lambda c: c.data and c.data.startswith("task_update:"))
async def task_update_stub(callback: CallbackQuery):
    await callback.answer("Обновление — реализуется.", show_alert=True)

@router.callback_query(lambda c: c.data and c.data.startswith("task_archive:"))
async def task_archive_stub(callback: CallbackQuery):
    await callback.answer("Архивирование — реализуется.", show_alert=True)

@router.callback_query(lambda c: c.data and c.data.startswith("task_restore:"))
async def task_restore_stub(callback: CallbackQuery):
    await callback.answer("Восстановление — реализуется.", show_alert=True)
