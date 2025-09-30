import httpx

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.keyboards.category import category_actions, categories_menu
from src.database.redis_client import redis_client
from src.database.states import UserState
from ..config import settings
from .states import CategoryStates

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
async def newcategory_start(message: Message, state: FSMContext):
    await state.set_state(CategoryStates.create_name)
    await message.answer("Введите название новой категории:")


@router.message(CategoryStates.create_name)
async def newcategory_create(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите название категории:")
        return
    token = await redis_client.get_user_token(user_id)
    if not token:
        await state.clear()
        await message.answer("⚠️ Сначала войдите через /login")
        return
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_URL}/categories/", json={"name": name},
            headers={"Authorization": f"Bearer {token}"}
        )
    if resp.status_code in (200, 201):
        await message.answer("✅ Категория успешно создана. Посмотреть список — /categories")
    else:
        await message.answer("❌ Ошибка при создании категории. Попробуйте позже.")
    await state.clear()


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
async def category_update_start(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split(":", 1)[1])
    await state.update_data(category_id=cat_id)
    await state.set_state(CategoryStates.update_name)
    await callback.message.answer("Введите новое название категории:")
    await callback.answer()


@router.message(CategoryStates.update_name)
async def category_update_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите новое название:")
        return
    token = await redis_client.get_user_token(user_id)
    if not token:
        await state.clear()
        await message.answer("⚠️ Сначала войдите через /login")
        return
    data = await state.get_data()
    cat_id = data.get("category_id")
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{API_URL}/categories/{cat_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name}
        )
    if resp.status_code in (200, 201):
        await message.answer("✅ Название категории обновлено. Посмотреть список — /categories")
    else:
        await message.answer("❌ Ошибка при обновлении категории")
    await state.clear()
