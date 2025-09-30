import logging
from typing import Optional, Tuple

import redis.asyncio as redis

from ..config import settings
from .states import UserState

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client: хранение access/refresh токенов и долгосрочного состояния пользователя."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

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

    # -------- USER STATE (long-lived) --------
    async def set_user_state(self, user_id: int, state: UserState) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.set(f"user:{user_id}:state", state.value)
            return True
        except Exception as e:
            logger.error(f"Redis set state error: {e}")
            return False

    async def get_user_state(self, user_id: int) -> Optional[UserState]:
        if not self.redis:
            return None
        try:
            value = await self.redis.get(f"user:{user_id}:state")
            return UserState(value) if value else None
        except Exception as e:
            logger.error(f"Redis get state error: {e}")
            return None

    async def delete_user_state(self, user_id: int) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.delete(f"user:{user_id}:state")
            return True
        except Exception as e:
            logger.error(f"Redis delete state error: {e}")
            return False

    # -------- TOKENS (access + refresh) --------
    def _key_access(self, user_id: int) -> str:
        return f"user:{user_id}:access_token"

    def _key_refresh(self, user_id: int) -> str:
        return f"user:{user_id}:refresh_token"

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


# Global instance
redis_client = RedisClient()
