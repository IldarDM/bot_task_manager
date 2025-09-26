import httpx

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.database.redis_client import redis_client, UserState
from src.database.states import FSMState
from ..config import settings

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"


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
