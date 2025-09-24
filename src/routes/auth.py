import re
import httpx

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.database.redis_client import redis_client, UserState
from src.database.statements import FSMState
from ..config import settings

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
MIN_PASSWORD_LENGTH = 6

# ----------------- LOGIN -----------------
@router.message(Command("login"))
async def login_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_fsm_step(user_id, FSMState.LOGIN_EMAIL)
    await message.answer("Введите email:")


# ----------------- REGISTER -----------------
@router.message(Command("register"))
async def register_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_fsm_step(user_id, FSMState.REGISTER_EMAIL)
    await message.answer("Введите email для регистрации:")


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


# ----------------- FSM HANDLER -----------------
@router.message()
async def fsm_handler(message: Message):
    user_id = message.from_user.id
    step = await redis_client.get_fsm_step(user_id)
    text = message.text.strip()

    # --- LOGIN STEPS ---
    if step in [FSMState.LOGIN_EMAIL, FSMState.LOGIN_PASSWORD]:
        if step == FSMState.LOGIN_EMAIL:
            if not EMAIL_REGEX.match(text):
                await message.answer("⚠️ Некорректный email. Попробуйте снова:")
                return

            await redis_client.set_fsm_step(user_id, FSMState.LOGIN_PASSWORD)
            await redis_client.redis.set(f"user:{user_id}:login_email", text, ex=300)
            await message.answer("Теперь введите пароль:")
            return

        if step == FSMState.LOGIN_PASSWORD:
            password = text
            if len(password) < MIN_PASSWORD_LENGTH:
                await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
                return

            email = await redis_client.redis.get(f"user:{user_id}:login_email")
            if not email:
                await message.answer("⚠️ Время на ввод email истекло. Попробуйте снова: /login")
                await redis_client.delete_fsm_step(user_id)
                return

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{API_URL}/auth/login",
                    json={"email": email, "password": password}
                )

            if resp.status_code == 200:
                token = resp.json()["access_token"]
                await redis_client.set_user_token(user_id, token)
                await redis_client.set_user_state(user_id, UserState.LOGGED_IN)
                await message.answer("✅ Авторизация успешна!")
            else:
                await message.answer("❌ Неверный email или пароль.")

            # Очистка FSM
            await redis_client.delete_fsm_step(user_id)
            await redis_client.redis.delete(f"user:{user_id}:login_email")
            return

    # --- REGISTER STEPS ---
    if step in [FSMState.REGISTER_EMAIL, FSMState.REGISTER_PASSWORD, FSMState.REGISTER_PASSWORD_CONFIRM]:
        # Шаг 1: email
        if step == FSMState.REGISTER_EMAIL:
            if not EMAIL_REGEX.match(text):
                await message.answer("⚠️ Некорректный email. Попробуйте снова:")
                return

            await redis_client.redis.set(f"user:{user_id}:register_email", text, ex=300)
            await redis_client.set_fsm_step(user_id, FSMState.REGISTER_PASSWORD)
            await message.answer("Введите пароль (мин. 6 символов):")
            return

        # Шаг 2: пароль
        if step == FSMState.REGISTER_PASSWORD:
            if len(text) < MIN_PASSWORD_LENGTH:
                await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
                return

            await redis_client.redis.set(f"user:{user_id}:register_password", text, ex=300)
            await redis_client.set_fsm_step(user_id, FSMState.REGISTER_PASSWORD_CONFIRM)
            await message.answer("Подтвердите пароль:")
            return

        # Шаг 3: подтверждение пароля
        if step == FSMState.REGISTER_PASSWORD_CONFIRM:
            password = await redis_client.redis.get(f"user:{user_id}:register_password")
            email = await redis_client.redis.get(f"user:{user_id}:register_email")

            if not email or not password:
                await message.answer("⚠️ Время на ввод данных истекло. Попробуйте снова: /register")
                await redis_client.delete_fsm_step(user_id)
                return

            if text != password:
                await message.answer("❌ Пароли не совпадают. Попробуйте снова:")
                return

            # Подтягиваем имя и фамилию из Telegram
            first_name = message.from_user.first_name or ""
            last_name = message.from_user.last_name or ""

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{API_URL}/auth/register",
                    json={
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "password": password
                    }
                )

            if resp.status_code == 201:
                await message.answer("✅ Регистрация успешна! Теперь вы можете войти через /login")
            else:
                await message.answer("❌ Ошибка регистрации")

            # Очистка FSM и временных данных
            await redis_client.delete_fsm_step(user_id)
            await redis_client.redis.delete(f"user:{user_id}:register_email")
            await redis_client.redis.delete(f"user:{user_id}:register_password")
            return
