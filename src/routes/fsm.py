import re
import httpx

from aiogram import Router
from aiogram.types import Message

from src.database.redis_client import redis_client, UserState
from src.database.states import FSMState
from ..config import settings

router = Router()
API_URL = f"{settings.api_base_url}/api/v1"

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
MIN_PASSWORD_LENGTH = 6

# ----------------- HELPERS -----------------
def redis_key(user_id: int, suffix: str) -> str:
    return f"user:{user_id}:{suffix}"

async def send_post(url: str, json_data: dict, token: str | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient() as client:
        return await client.post(url, headers=headers, json=json_data)

async def send_put(url: str, json_data: dict, token: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.put(url, headers={"Authorization": f"Bearer {token}"}, json=json_data)

async def get_redis_value(key: str) -> str | None:
    value = await redis_client.redis.get(key)
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else value

# ----------------- FSM HANDLERS -----------------
async def fsm_login(message: Message, step: FSMState, text: str, user_id: int):
    if step == FSMState.LOGIN_EMAIL:
        if not EMAIL_REGEX.match(text):
            await message.answer("⚠️ Некорректный email. Попробуйте снова:")
            return
        await redis_client.redis.set(redis_key(user_id, "login_email"), text, ex=300)
        await redis_client.set_fsm_step(user_id, FSMState.LOGIN_PASSWORD)
        await message.answer("Теперь введите пароль:")
        return

    if step == FSMState.LOGIN_PASSWORD:
        if len(text) < MIN_PASSWORD_LENGTH:
            await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
            return

        email = await get_redis_value(redis_key(user_id, "login_email"))
        if not email:
            await message.answer("⚠️ Время на ввод email истекло. Попробуйте снова: /login")
            await redis_client.delete_fsm_step(user_id)
            return

        resp = await send_post(f"{API_URL}/auth/login", {"email": email, "password": text})
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            await redis_client.set_user_token(user_id, token)
            await redis_client.set_user_state(user_id, UserState.LOGGED_IN)
            await message.answer("✅ Авторизация успешна!")
        else:
            await message.answer("❌ Неверный email или пароль.")

        await redis_client.delete_fsm_step(user_id)
        await redis_client.redis.delete(redis_key(user_id, "login_email"))

# --------------------------------------
async def fsm_register(message: Message, step: FSMState, text: str, user_id: int):
    if step == FSMState.REGISTER_EMAIL:
        if not EMAIL_REGEX.match(text):
            await message.answer("⚠️ Некорректный email. Попробуйте снова:")
            return
        await redis_client.redis.set(redis_key(user_id, "register_email"), text, ex=300)
        await redis_client.set_fsm_step(user_id, FSMState.REGISTER_PASSWORD)
        await message.answer("Введите пароль (мин. 6 символов):")
        return

    if step == FSMState.REGISTER_PASSWORD:
        if len(text) < MIN_PASSWORD_LENGTH:
            await message.answer(f"⚠️ Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов. Попробуйте снова:")
            return
        await redis_client.redis.set(redis_key(user_id, "register_password"), text, ex=300)
        await redis_client.set_fsm_step(user_id, FSMState.REGISTER_PASSWORD_CONFIRM)
        await message.answer("Подтвердите пароль:")
        return

    if step == FSMState.REGISTER_PASSWORD_CONFIRM:
        password = await get_redis_value(redis_key(user_id, "register_password"))
        email = await get_redis_value(redis_key(user_id, "register_email"))

        if not email or not password:
            await message.answer("⚠️ Время на ввод данных истекло. Попробуйте снова: /register")
            await redis_client.delete_fsm_step(user_id)
            return

        if text != password:
            await message.answer("❌ Пароли не совпадают. Попробуйте снова:")
            return

        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""

        resp = await send_post(
            f"{API_URL}/auth/register",
            {"email": email, "first_name": first_name, "last_name": last_name, "password": password}
        )

        if resp.status_code == 201:
            await message.answer("✅ Регистрация успешна! Теперь вы можете войти через /login")
        else:
            await message.answer("❌ Ошибка регистрации")

        await redis_client.delete_fsm_step(user_id)
        await redis_client.redis.delete(redis_key(user_id, "register_email"))
        await redis_client.redis.delete(redis_key(user_id, "register_password"))

# --------------------------------------
async def fsm_category(message: Message, step: FSMState, text: str, user_id: int):
    if step == FSMState.CATEGORY_CREATE_NAME:
        if not text:
            await message.answer("Название не может быть пустым. Введите название категории:")
            return
        token = await redis_client.get_user_token(user_id)
        if not token:
            await message.answer("⚠️ Сначала войдите через /login")
            await redis_client.delete_fsm_step(user_id)
            return
        resp = await send_post(f"{API_URL}/categories/", {"name": text}, token)
        if resp.status_code in (200, 201):
            await message.answer("✅ Категория успешно создана")
        else:
            await message.answer("❌ Ошибка при создании категории. Попробуйте позже.")
        await redis_client.delete_fsm_step(user_id)

    if step == FSMState.CATEGORY_UPDATE_NAME:
        if not text:
            await message.answer("Название не может быть пустым. Введите новое название:")
            return
        cat_id = await get_redis_value(redis_key(user_id, "category_update_id"))
        if not cat_id:
            await message.answer("⏳ Сессия обновления истекла, попробуйте снова.")
            await redis_client.delete_fsm_step(user_id)
            return
        token = await redis_client.get_user_token(user_id)
        if not token:
            await message.answer("⚠️ Сначала войдите через /login")
            await redis_client.delete_fsm_step(user_id)
            await redis_client.redis.delete(redis_key(user_id, "category_update_id"))
            return
        resp = await send_put(f"{API_URL}/categories/{cat_id}", {"name": text}, token)
        if resp.status_code in (200, 201):
            await message.answer("✅ Название категории обновлено")
        else:
            await message.answer("❌ Ошибка при обновлении категории")
        await redis_client.delete_fsm_step(user_id)
        await redis_client.redis.delete(redis_key(user_id, "category_update_id"))


async def task_create_fsm(message: Message):
    user_id = message.from_user.id
    step = await redis_client.get_fsm_step(user_id)
    text = message.text.strip()

    # --- Шаг 1: заголовок ---
    if step == FSMState.TASK_CREATE_TITLE:
        await redis_client.redis.set(f"user:{user_id}:task_title", text, ex=600)
        await redis_client.set_fsm_step(user_id, FSMState.TASK_CREATE_DESCRIPTION)
        await message.answer("Введите описание задачи:")
        return

    # --- Шаг 2: описание ---
    if step == FSMState.TASK_CREATE_DESCRIPTION:
        await redis_client.redis.set(f"user:{user_id}:task_description", text, ex=600)
        await redis_client.set_fsm_step(user_id, FSMState.TASK_CREATE_CATEGORY)
        await message.answer("Введите категорию (или оставьте пустой для 'Без категории'):")
        return

    # --- Шаг 3: категория ---
    if step == FSMState.TASK_CREATE_CATEGORY:
        category = text if text else None
        await redis_client.redis.set(f"user:{user_id}:task_category", category, ex=600)
        await redis_client.set_fsm_step(user_id, FSMState.TASK_CREATE_PRIORITY)
        await message.answer("Введите приоритет (LOW, MEDIUM, HIGH):")
        return

    # --- Шаг 4: приоритет и создание ---
    if step == FSMState.TASK_CREATE_PRIORITY:
        priority = text.upper()
        if priority not in ["LOW", "MEDIUM", "HIGH"]:
            await message.answer("⚠️ Некорректный приоритет. Используйте: LOW, MEDIUM, HIGH")
            return

        title = await redis_client.redis.get(f"user:{user_id}:task_title")
        description = await redis_client.redis.get(f"user:{user_id}:task_description")
        category = await redis_client.redis.get(f"user:{user_id}:task_category")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{API_URL}/tasks",
                json={
                    "title": title,
                    "description": description,
                    "category_id": category,
                    "priority": priority
                },
                headers={"Authorization": f"Bearer {await redis_client.get_user_token(user_id)}"}
            )

        if resp.status_code == 201:
            await message.answer("✅ Задача успешно создана!")
        else:
            await message.answer("❌ Ошибка при создании задачи.")

        await redis_client.delete_fsm_step(user_id)
        await redis_client.redis.delete(f"user:{user_id}:task_title")
        await redis_client.redis.delete(f"user:{user_id}:task_description")
        await redis_client.redis.delete(f"user:{user_id}:task_category")

# ----------------- MAIN HANDLER -----------------
@router.message()
async def fsm_handler(message: Message):
    user_id = message.from_user.id
    step = await redis_client.get_fsm_step(user_id)
    text = message.text.strip()

    if step in [FSMState.LOGIN_EMAIL, FSMState.LOGIN_PASSWORD]:
        await fsm_login(message, step, text, user_id)
        return

    if step in [
        FSMState.REGISTER_EMAIL,
        FSMState.REGISTER_PASSWORD,
        FSMState.REGISTER_PASSWORD_CONFIRM,
    ]:
        await fsm_register(message, step, text, user_id)
        return

    if step in [FSMState.CATEGORY_CREATE_NAME, FSMState.CATEGORY_UPDATE_NAME]:
        await fsm_category(message, step, text, user_id)
        return

    await message.answer("Неопознанная команда")
