from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.database.redis_client import redis_client
from src.database.states import UserState, FSMState

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_user_state(user_id, UserState.STARTED)

    await message.answer(f"""
Салют, {message.from_user.full_name}!
Добро пожаловать в TaskFlow - бота, призванного помочь разобраться с вечными насущными делами 🚀

Используй /help, чтобы увидеть доступные команды.
Используй /login, чтобы авторизоваться, или /register, если ещё нет аккаунта.
""")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer("""
Доступные команды:

/start - Запуск бота
/help - Показать это сообщение
/register - Зарегистрировать аккаунт
/login - Войти в аккаунт

Скоро появятся новые функции...
""")

