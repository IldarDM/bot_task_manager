import redis.asyncio as redis
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Simple Redis client for user states."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self.redis.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Don't raise - bot should work without Redis
            self.redis = None

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def set_user_state(self, user_id: int, state: str) -> bool:
        """Set user state."""
        if not self.redis:
            return False
        try:
            await self.redis.setex(f"user:{user_id}:state", 3600, state)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def get_user_state(self, user_id: int) -> Optional[str]:
        """Get user state."""
        if not self.redis:
            return None
        try:
            return await self.redis.get(f"user:{user_id}:state")
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None


# Global instance
redis_client = RedisClient()