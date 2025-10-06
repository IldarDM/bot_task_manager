from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.keyboards.main_menu import (
    HELP_BUTTON,
    PROFILE_BUTTON,
    main_menu_keyboard,
)

router = Router()

HELP_TEXT = (
    "👋 <b>TaskFlow</b> — телеграм-пульт к вашему таск-менеджеру.\n\n"
    "<b>Как начать</b>:\n"
    "1️⃣ Нажмите «⚙️ Профиль», чтобы войти или зарегистрироваться.\n"
    "2️⃣ Откройте «📋 Мои задачи» — там фильтры, поиск и создание задач.\n"
    "3️⃣ В разделе «📂 Категории» управляйте папками и смотрите связанные задачи.\n\n"
    "<b>Подсказки</b>:\n"
    "• Кнопка «➕ Задача» мгновенно запускает создание.\n"
    "• Фильтры «🔥/⏰/✅/📦» помогают переключать представление за один тап.\n"
    "• Всегда можно нажать «Отмена» или команду /cancel, чтобы прервать текущий шаг.\n\n"
    "Если что-то пошло не так — используйте кнопку «❓ Помощь» или команду /help."
)


async def _send_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Салют, {message.from_user.full_name}!\n"
        "TaskFlow держит ваши задачи и категории под рукой.\n"
        "Внизу — главное меню, им можно управлять без команд.",
        reply_markup=main_menu_keyboard(),
    )
    await _send_help(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await _send_help(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✅ Действие отменено. Меню снова с вами.", reply_markup=main_menu_keyboard())


@router.message(lambda m: (m.text or "").strip().lower() == "отмена")
async def msg_cancel(message: Message, state: FSMContext) -> None:
    await cmd_cancel(message, state)


@router.callback_query(lambda c: c.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(
        "✅ Действие отменено. Выберите следующее действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.message(lambda m: m.text == HELP_BUTTON)
async def help_button(message: Message) -> None:
    await _send_help(message)


@router.message(lambda m: m.text == PROFILE_BUTTON)
async def profile_button(message: Message) -> None:
    await message.answer(
        "📌 Доступные действия:\n"
        "• /login — вход\n"
        "• /register — регистрация\n"
        "• /logout — выход\n"
        "• /me — профиль",
        reply_markup=main_menu_keyboard(),
    )


@router.message(lambda m: m.text == "Отмена")
async def russian_cancel_button(message: Message, state: FSMContext) -> None:
    await cmd_cancel(message, state)
