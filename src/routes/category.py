import httpx

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from src.keyboards.category import category_actions, categories_menu
from src.database.redis_client import redis_client
from src.database.states import FSMState, UserState
from ..config import settings

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"

# ----------------- LIST CATEGORIES -----------------
@router.message(Command("categories"))
async def list_categories(message: Message):
    user_id = message.from_user.id
    token = await redis_client.get_user_token(user_id)
    if not token:
        await message.answer("⚠️ Сначала войдите через /login")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_URL}/categories/",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code != 200:
        await message.answer("❌ Ошибка получения категорий")
        return

    categories = resp.json()
    if not categories:
        await message.answer("У вас ещё нет категорий. Создать — /newcategory", reply_markup=categories_menu())
        return

    for cat in categories:
        name = cat.get("name")
        if name == "Uncategorized":
            name = "Без категории"
        await message.answer(f"📁 {name}", reply_markup=category_actions(cat.get("id")))


# ----------------- CREATE CATEGORY -----------------
@router.message(Command("newcategory"))
async def newcategory_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_fsm_step(user_id, FSMState.CATEGORY_CREATE_NAME)
    await message.answer("Введите название новой категории:")


# ----------------- DELETE CATEGORY -----------------
@router.callback_query(lambda c: c.data and c.data.startswith("category_delete:"))
async def category_delete(callback: CallbackQuery):
    cat_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    token = await redis_client.get_user_token(user_id)

    if not token:
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{API_URL}/categories/{cat_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code in (200, 204):
        try:
            await callback.message.edit_text("🗑 Категория удалена")
        except Exception:
            await callback.answer("✅ Категория удалена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось удалить категорию", show_alert=True)


# ----------------- UPDATE CATEGORY -----------------
@router.callback_query(lambda c: c.data and c.data.startswith("category_update:"))
async def category_update_start(callback: CallbackQuery):
    cat_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    await redis_client.redis.set(f"user:{user_id}:category_update_id", cat_id, ex=300)
    await redis_client.set_fsm_step(user_id, FSMState.CATEGORY_UPDATE_NAME)

    await callback.message.answer("Введите новое название категории:")
    await callback.answer()
