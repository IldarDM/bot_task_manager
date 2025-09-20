import asyncio
import logging

from aiogram.filters import Command
from aiogram.types import Message

from src.bot import create_bot, create_dispatcher
from src.config import settings

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = create_bot(settings.bot_token)
dp = create_dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Hello!")


async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())