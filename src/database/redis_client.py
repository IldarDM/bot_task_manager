import logging
from typing import Optional, Tuple

import redis.asyncio as redis

from ..config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client: хранение access/refresh токенов пользователя."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._ns = "user"

    async def connect(self):
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self.redis.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis = None

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    # keys
    def _key_access(self, user_id: int) -> str:
        return f"{self._ns}:{user_id}:access_token"

    def _key_refresh(self, user_id: int) -> str:
        return f"{self._ns}:{user_id}:refresh_token"

    # tokens
    async def set_user_tokens(self, user_id: int, access: str, refresh: str) -> bool:
        if not self.redis:
            return False
        try:
            pipe = self.redis.pipeline()
            pipe.set(self._key_access(user_id), access)
            pipe.set(self._key_refresh(user_id), refresh)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis set tokens error: {e}")
            return False

    async def set_user_access_token(self, user_id: int, token: str) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.set(self._key_access(user_id), token)
            return True
        except Exception as e:
            logger.error(f"Redis set access token error: {e}")
            return False

    async def set_user_refresh_token(self, user_id: int, token: str) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.set(self._key_refresh(user_id), token)
            return True
        except Exception as e:
            logger.error(f"Redis set refresh token error: {e}")
            return False

    async def get_user_access_token(self, user_id: int) -> Optional[str]:
        if not self.redis:
            return None
        try:
            return await self.redis.get(self._key_access(user_id))
        except Exception as e:
            logger.error(f"Redis get access token error: {e}")
            return None

    async def get_user_refresh_token(self, user_id: int) -> Optional[str]:
        if not self.redis:
            return None
        try:
            return await self.redis.get(self._key_refresh(user_id))
        except Exception as e:
            logger.error(f"Redis get refresh token error: {e}")
            return None

    async def get_user_tokens(self, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        access = await self.get_user_access_token(user_id)
        refresh = await self.get_user_refresh_token(user_id)
        return access, refresh

    async def delete_user_tokens(self, user_id: int) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.delete(self._key_access(user_id), self._key_refresh(user_id))
            return True
        except Exception as e:
            logger.error(f"Redis delete tokens error: {e}")
            return False

    async def is_authenticated(self, user_id: int) -> bool:
        """Пользователь считается авторизованным, если у него есть refresh-токен."""
        if not self.redis:
            return False
        try:
            refresh = await self.redis.get(self._key_refresh(user_id))
            return bool(refresh)
        except Exception as e:
            logger.error(f"Redis is_authenticated error: {e}")
            return False


# Global instance
redis_client = RedisClient()
