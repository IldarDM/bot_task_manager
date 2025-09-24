from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.database.redis_client import redis_client
from src.database.statements import UserState, FSMState

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await redis_client.set_user_state(user_id, UserState.STARTED)

    await message.answer(f"""
Салют, {message.from_user.full_name}!
Добро пожаловать в TaskFlow - бота, призванного помочь разобраться с вечными насущными делами 🚀

Используй /help, чтобы увидеть доступные команды.
Используй /login, чтобы авторизоваться.
""")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer("""
Доступные команды:

/start - Запуск бота
/help - Показать это сообщение
/login - Войти в аккаунт
/status - Проверить текущий статус

Скоро появятся новые функции...
""")


@router.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    user_state = await redis_client.get_user_state(user_id)

    if user_state:
        await message.answer(f"Текущее состояние: {user_state}")
    else:
        await message.answer("Состояние не найдено. Используй /start, чтобы начать.")


@router.message(Command("login"))
async def cmd_login(message: Message):
    await message.answer("""
🔐 Авторизация в Task Manager

Эта функция будет реализована в ближайшее время.
Пока можешь использовать /status, чтобы проверить состояние.
""")
