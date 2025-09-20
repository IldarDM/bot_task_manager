from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"Салют, {message.from_user.full_name}!\n"
        "Добро пожаловать в TaskFlow - бота, призванного помочь разобраться с вечными насущными делами"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n"
        "/start - Запуск бота\n"
        "/help - Доступные команды"
    )