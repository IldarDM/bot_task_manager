import asyncio
import logging

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.handlers import setup_handlers

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = create_bot(settings.bot_token)
dp = create_dispatcher()

# Setup handlers
dp.include_router(setup_handlers())


async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())