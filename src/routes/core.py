from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"Салют, {message.from_user.full_name}!\n"
        "Это TaskFlow — ваш помощник по задачам.\n\n"
        "Команды:\n"
        "• /register — регистрация\n"
        "• /login — вход\n"
        "• /logout — выход\n"
        "• /tasks — список задач\n"
        "• /newtask — новая задача\n"
        "• /categories — категории\n"
        "• /help — помощь\n"
        "• /cancel — отмена текущего действия\n\n"
        "Подсказка: в шагах мастера всегда можно нажать «Отмена»."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Помощь:\n"
        "• Отмена: нажмите кнопку «Отмена» или используйте /cancel — это прервёт текущее действие.\n"
        "• Приоритет: выбирайте кнопками или введите цифру 1..4 (низкий..срочный), "
        "также поддерживаются low/medium/high/urgent и русские слова.\n"
        "• Дедлайн: можно нажать «Сегодня/Завтра/+3 дня» или ввести дату YYYY-MM-DD. "
        "Чтобы убрать дедлайн — отправьте «-».\n\n"
        "Полезные команды: /tasks /newtask /categories /login /logout"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✅ Действие отменено. Что дальше?\n"
        "Например: /tasks, /newtask, /categories, /help"
    )


@router.message(lambda m: (m.text or "").strip().lower() == "отмена")
async def msg_cancel(message: Message, state: FSMContext):
    await cmd_cancel(message, state)


@router.callback_query(lambda c: c.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "✅ Действие отменено. Что дальше?\n"
        "Например: /tasks, /newtask, /categories, /help"
    )
    await callback.answer()
