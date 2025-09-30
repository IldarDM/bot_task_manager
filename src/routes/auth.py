import re
import httpx

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.database.redis_client import redis_client
from src.database.states import UserState
from src.config import settings
from states import AuthStates

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
MIN_PASSWORD_LENGTH = 6


# ----------------- LOGIN -----------------
@router.message(Command("login"))
async def login_start(message: Message, state: FSMContext):
    await state.set_state(AuthStates.login_email)
    await message.answer("Введите email:")


@router.message(AuthStates.login_email)
async def login_email(message: Message, state: FSMContext):
    if not EMAIL_REGEX.match(message.text or ""):
        await message.answer("⚠️ Некорректный email. Попробуйте снова:")
        return
    await state.update_data(email=(message.text or "").strip())
    await state.set_state(AuthStates.login_password)
    await message.answer("Теперь введите пароль:")


@router.message(AuthStates.login_password)
async def login_password(message: Message, state: FSMContext):
    pwd = (message.text or "").strip()
    if len(pwd) < MIN_PASSWORD_LENGTH:
        await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
        return
    data = await state.get_data()
    email = data.get("email")
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_URL}/auth/login", json={"email": email, "password": pwd})
    if resp.status_code == 200:
        token = resp.json().get("access_token")
        await redis_client.set_user_token(message.from_user.id, token)
        await redis_client.set_user_state(message.from_user.id, UserState.LOGGED_IN)
        await message.answer("✅ Авторизация успешна!")
        await state.clear()
    else:
        await message.answer("❌ Неверный email или пароль.")


# ----------------- REGISTER -----------------
@router.message(Command("register"))
async def register_start(message: Message, state: FSMContext):
    await state.set_state(AuthStates.reg_email)
    await message.answer("Введите email для регистрации:")


@router.message(AuthStates.reg_email)
async def register_email(message: Message, state: FSMContext):
    if not EMAIL_REGEX.match(message.text or ""):
        await message.answer("⚠️ Некорректный email. Попробуйте снова:")
        return
    await state.update_data(email=(message.text or "").strip())
    await state.set_state(AuthStates.reg_password)
    await message.answer("Введите пароль (мин. 6 символов):")


@router.message(AuthStates.reg_password)
async def register_password(message: Message, state: FSMContext):
    pwd = (message.text or "").strip()
    if len(pwd) < MIN_PASSWORD_LENGTH:
        await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
        return
    await state.update_data(password=pwd)
    await state.set_state(AuthStates.reg_password_confirm)
    await message.answer("Подтвердите пароль:")


@router.message(AuthStates.reg_password_confirm)
async def register_password_confirm(message: Message, state: FSMContext):
    confirm = (message.text or "").strip()
    data = await state.get_data()
    email = data.get("email")
    pwd = data.get("password")
    if not email or not pwd:
        await message.answer("⚠️ Сессия истекла. Начните заново: /register")
        await state.clear()
        return
    if confirm != pwd:
        await message.answer("❌ Пароли не совпадают. Попробуйте ещё раз:")
        return
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_URL}/auth/register",
            json={"email": email, "first_name": first_name, "last_name": last_name, "password": pwd}
        )
    if resp.status_code == 201:
        await message.answer("✅ Регистрация успешна! Теперь вы можете войти через /login")
    else:
        await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
    await state.clear()


# ----------------- LOGOUT -----------------
@router.message(Command("logout"))
async def logout_handler(message: Message):
    user_id = message.from_user.id
    token = await redis_client.get_user_token(user_id)
    if not token:
        await message.answer("Вы и так не авторизованы 🙂")
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{API_URL}/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )

    await redis_client.delete_user_token(user_id)
    await redis_client.set_user_state(user_id, UserState.LOGGED_OUT)
    await message.answer("👋 Вы вышли из аккаунта.")
