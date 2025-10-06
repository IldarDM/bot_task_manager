from typing import Dict, List, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.database.redis_client import redis_client
from src.keyboards.category import categories_board, category_detail_keyboard
from src.keyboards.common import cancel_keyboard
from src.keyboards.main_menu import (
    CATEGORIES_BUTTON,
    NEW_CATEGORY_BUTTON,
    main_menu_keyboard,
)
from src.routes.states import CategoryStates
from src.services.categories_api import CategoriesAPI
from src.services.http_client import client

router = Router()


async def _respond(target: Message | CallbackQuery, text: str, kb) -> None:
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
        return

    message = target.message
    try:
        if (message.text or "") == text:
            await message.edit_reply_markup(reply_markup=kb)
        else:
            await message.edit_text(text, reply_markup=kb)
    except Exception:
        await message.edit_text(text, reply_markup=kb)


async def _render_categories(target: Message | CallbackQuery, page: int = 0) -> None:
    user_id = target.from_user.id
    if not await redis_client.is_authenticated(user_id):
        if isinstance(target, Message):
            await target.answer("⚠️ Сначала войдите через /login", reply_markup=main_menu_keyboard())
        else:
            await target.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    categories = await CategoriesAPI.list(user_id)
    total = len(categories)

    lines: List[str] = ["📂 <b>Категории</b>", f"Всего: {total}"]
    if total:
        lines.append("Нажмите на категорию, чтобы открыть действия.")
    else:
        lines.append("Категорий пока нет. Нажмите «➕ Категория», чтобы добавить первую.")

    text = "\n".join(lines)
    kb = categories_board(categories, page=page)
    await _respond(target, text, kb)


@router.message(Command("categories"))
async def cmd_categories(message: Message, state: FSMContext) -> None:
    await _render_categories(message)


@router.message(F.text == CATEGORIES_BUTTON)
async def categories_button(message: Message, state: FSMContext) -> None:
    await _render_categories(message)


@router.message(Command("newcategory"))
async def newcategory_start(message: Message, state: FSMContext) -> None:
    await state.set_state(CategoryStates.create_name)
    await message.answer("Введите название новой категории:", reply_markup=cancel_keyboard())


@router.message(F.text == NEW_CATEGORY_BUTTON)
async def new_category_button(message: Message, state: FSMContext) -> None:
    await newcategory_start(message, state)


@router.callback_query(F.data == "cat:new")
async def newcategory_from_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryStates.create_name)
    await callback.message.answer("Введите название новой категории:", reply_markup=cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "category_refresh")
async def category_refresh(callback: CallbackQuery) -> None:
    await _render_categories(callback)
    await callback.answer("Обновлено")


@router.callback_query(F.data.startswith("category_page:"))
async def category_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    await _render_categories(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("category_back:"))
async def category_back(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    await _render_categories(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("category_open:"))
async def category_open(callback: CallbackQuery) -> None:
    _, _, raw = callback.data.partition(":")
    cat_id_str, _, page_str = raw.partition(":")
    cat_id = int(cat_id_str)
    page = int(page_str or "0")

    categories = await CategoriesAPI.list(callback.from_user.id)
    category: Optional[Dict] = next((c for c in categories if c.get("id") == cat_id), None)
    if not category:
        await callback.answer("Категория не найдена", show_alert=True)
        await _render_categories(callback, page=page)
        return

    name = category.get("name") or "Без названия"
    if name.lower() == "uncategorized":
        name = "Без категории"

    text = (
        f"📁 <b>{name}</b>\n"
        "Выберите действие:"
    )
    kb = category_detail_keyboard(cat_id, page)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.message(CategoryStates.create_name)
async def newcategory_create(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите название категории:", reply_markup=cancel_keyboard())
        return

    if not await redis_client.is_authenticated(user_id):
        await state.set_state(None)
        await message.answer("⚠️ Сначала войдите через /login", reply_markup=main_menu_keyboard())
        return

    api_response = await client.request(user_id, "POST", "/categories/", json={"name": name})
    if api_response.status_code in (200, 201):
        await message.answer("✅ Категория создана.", reply_markup=main_menu_keyboard())
        await _render_categories(message)
    else:
        await message.answer("❌ Ошибка при создании категории. Попробуйте позже.")
    await state.set_state(None)


@router.callback_query(lambda c: c.data and c.data.startswith("category_delete:"))
async def category_delete(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    cat_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    if not await redis_client.is_authenticated(callback.from_user.id):
        await callback.answer("⚠️ Сначала войдите через /login", show_alert=True)
        return

    resp = await client.request(callback.from_user.id, "DELETE", f"/categories/{cat_id}")
    if resp.status_code in (200, 204):
        await _render_categories(callback, page=page)
        await callback.answer("Категория удалена")
    else:
        await callback.answer("❌ Не удалось удалить категорию", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("category_update:"))
async def category_update_start(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    cat_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    await state.update_data(category_id=cat_id, category_page=page)
    await state.set_state(CategoryStates.update_name)
    await callback.message.answer("Введите новое название категории:", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(CategoryStates.update_name)
async def category_update_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите новое название:", reply_markup=cancel_keyboard())
        return

    if not await redis_client.is_authenticated(user_id):
        await state.set_state(None)
        await message.answer("⚠️ Сначала войдите через /login", reply_markup=main_menu_keyboard())
        return

    data = await state.get_data()
    cat_id = data.get("category_id")
    page = int(data.get("category_page", 0))

    resp = await client.request(user_id, "PUT", f"/categories/{cat_id}", json={"name": name})
    if resp.status_code in (200, 201):
        await message.answer("✅ Название категории обновлено.", reply_markup=main_menu_keyboard())
        await _render_categories(message, page=page)
    else:
        await message.answer("❌ Ошибка при обновлении категории")
    await state.set_state(None)
