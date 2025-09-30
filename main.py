import asyncio
import logging
from pathlib import Path

from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from redis.asyncio import from_url

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.database.redis_client import redis_client
from src.routes import setup_handlers

# ----------------- LOGGING -----------------
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(getattr(logging, settings.log_level, logging.INFO))
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)

# ----------------- BOT WIRES -----------------
bot = create_bot(settings.bot_token)
redis = from_url(settings.redis_url, decode_responses=True)
storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(with_bot_id=True))
dp = create_dispatcher(storage=storage)
dp.include_router(setup_handlers())

async def on_startup():
    await redis_client.connect()

async def on_shutdown():
    await redis_client.disconnect()

async def main():
    try:
        logger.info("Starting Task Manager Bot...")
        await on_startup()
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Bot fatal error: %s", e)
    finally:
        await on_shutdown()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())