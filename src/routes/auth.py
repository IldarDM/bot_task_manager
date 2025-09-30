import re
import httpx

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.database.redis_client import redis_client
from src.database.statements import UserState
from src.services.http_client import client
from .states import AuthStates
from src.keyboards.common import cancel_keyboard, auth_retry_keyboard

router = Router()
API_URL = "/api/v1"


EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
MIN_PASSWORD_LENGTH = 6


# ----------------- LOGIN -----------------
@router.message(Command("login"))
async def login_start(message: Message, state: FSMContext):
    await state.set_state(AuthStates.login_email)
    await message.answer("Введите email:", reply_markup=cancel_keyboard())


@router.message(AuthStates.login_email)
async def login_email(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not EMAIL_REGEX.match(text):
        await message.answer("⚠️ Некорректный email. Попробуйте снова:", reply_markup=cancel_keyboard())
        return
    await state.update_data(email=text)
    await state.set_state(AuthStates.login_password)
    await message.answer("Теперь введите пароль:", reply_markup=cancel_keyboard())


@router.message(AuthStates.login_password)
async def login_password(message: Message, state: FSMContext):
    pwd = (message.text or "").strip()
    if len(pwd) < MIN_PASSWORD_LENGTH:
        await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов.",
                             reply_markup=cancel_keyboard())
        return
    data = await state.get_data()
    email = data.get("email")

    async with httpx.AsyncClient(base_url=API_URL, timeout=15.0) as c:
        resp = await c.post("/auth/login", json={"email": email, "password": pwd})

    if resp.status_code == 200:
        body = resp.json()
        access = body.get("access_token")
        refresh = body.get("refresh_token")
        if access and refresh:
            await redis_client.set_user_tokens(message.from_user.id, access, refresh)
            await redis_client.set_user_state(message.from_user.id, UserState.LOGGED_IN)
            await message.answer("✅ Авторизация успешна!")
            await state.clear()
        else:
            await message.answer("❌ Сервер не выдал токены. Попробуйте позже.", reply_markup=cancel_keyboard())
    else:
        await message.answer("❌ Неверный email или пароль.")
        await message.answer("Выберите действие:", reply_markup=auth_retry_keyboard())


# ----------------- REGISTER (с автологином) -----------------
@router.message(Command("register"))
async def register_start(message: Message, state: FSMContext):
    await state.set_state(AuthStates.reg_email)
    await message.answer(
        "Введите email для регистрации:\n"
        "После успешной регистрации вы будете автоматически авторизованы.",
        reply_markup=cancel_keyboard()
    )


@router.message(AuthStates.reg_email)
async def register_email(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not EMAIL_REGEX.match(text):
        await message.answer("⚠️ Некорректный email. Попробуйте снова:", reply_markup=cancel_keyboard())
        return
    await state.update_data(email=text)
    await state.set_state(AuthStates.reg_password)
    await message.answer("Введите пароль (мин. 6 символов):", reply_markup=cancel_keyboard())


@router.message(AuthStates.reg_password)
async def register_password(message: Message, state: FSMContext):
    pwd = (message.text or "").strip()
    if len(pwd) < MIN_PASSWORD_LENGTH:
        await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов.",
                             reply_markup=cancel_keyboard())
        return
    await state.update_data(password=pwd)
    await state.set_state(AuthStates.reg_password_confirm)
    await message.answer("Подтвердите пароль:", reply_markup=cancel_keyboard())


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
        await message.answer("❌ Пароли не совпадают. Попробуйте ещё раз:", reply_markup=cancel_keyboard())
        return

    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""

    async with httpx.AsyncClient(base_url=API_URL, timeout=15.0) as c:
        resp = await c.post(
            "/auth/register",
            json={"email": email, "first_name": first_name, "last_name": last_name, "password": pwd}
        )

    if resp.status_code != 201:
        await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
        await state.clear()
        return

    async with httpx.AsyncClient(base_url=API_URL, timeout=15.0) as c:
        login_resp = await c.post("/auth/login", json={"email": email, "password": pwd})

    if login_resp.status_code == 200:
        body = login_resp.json()
        access = body.get("access_token")
        refresh = body.get("refresh_token")
        if access and refresh:
            await redis_client.set_user_tokens(message.from_user.id, access, refresh)
            await redis_client.set_user_state(message.from_user.id, UserState.LOGGED_IN)
            await message.answer("🎉 Регистрация успешна и вы уже вошли в аккаунт. Добро пожаловать!")
        else:
            await message.answer("✅ Регистрация успешна! Но не удалось выполнить автологин. Используйте /login.")
    else:
        await message.answer("✅ Регистрация успешна! Теперь войдите через /login.")

    await state.clear()


# ----------------- ME (профиль) -----------------
@router.message(Command("me"))
async def me(message: Message):
    user_id = message.from_user.id
    resp = await client.request(user_id, "GET", "/auth/me")
    if resp.status_code == 200:
        data = resp.json() or {}
        email = data.get("email", "—")
        first = data.get("first_name", "—")
        last = data.get("last_name", "—")
        await message.answer(
            f"👤 Профиль:\nEmail: <b>{email}</b>\nИмя: {first}\nФамилия: {last}"
        )
    elif resp.status_code in (401, 403):
        await message.answer("⚠️ Вы не авторизованы. Используйте /login")
    else:
        await message.answer("❌ Не удалось получить профиль. Попробуйте позже.")


# ----------------- LOGOUT -----------------
@router.message(Command("logout"))
async def logout_handler(message: Message):
    user_id = message.from_user.id
    access, refresh = await redis_client.get_user_tokens(user_id)
    if not access and not refresh:
        await message.answer("Вы и так не авторизованы 🙂")
        return

    async with httpx.AsyncClient(base_url=API_URL, timeout=15.0) as c:
        await c.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {access}"} if access else {},
            json={"refresh_token": refresh} if refresh else None
        )

    await redis_client.delete_user_tokens(user_id)
    await redis_client.set_user_state(user_id, UserState.LOGGED_OUT)
    await message.answer("👋 Вы вышли из аккаунта.")
