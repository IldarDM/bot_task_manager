import asyncio
import logging

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.database.redis_client import redis_client
from src.routes import setup_handlers

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = create_bot(settings.bot_token)
dp = create_dispatcher()

# Setup routes
dp.include_router(setup_handlers())


async def on_startup():
    """Initialize services on startup."""
    await redis_client.connect()


async def on_shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()


async def main():
    """Main function to start the bot."""
    try:
        logger.info("Starting Task Manager Bot...")
        await on_startup()
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await on_shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())