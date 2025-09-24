import logging
from typing import Optional

import redis.asyncio as redis

from ..config import settings
from .statements import UserState, FSMState

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client для хранения состояний, FSM-шагов и токенов."""

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

    # --- ДОЛГОСРОЧНЫЕ СОСТОЯНИЯ ---

    async def set_user_state(self, user_id: int, state: UserState) -> bool:
        """Сохранить состояние пользователя (без TTL)."""
        if not self.redis:
            return False
        try:
            await self.redis.set(f"user:{user_id}:state", state.value)
            return True
        except Exception as e:
            logger.error(f"Redis set state error: {e}")
            return False

    async def get_user_state(self, user_id: int) -> Optional[UserState]:
        """Получить состояние пользователя."""
        if not self.redis:
            return None
        try:
            state = await self.redis.get(f"user:{user_id}:state")
            return UserState(state) if state else None
        except Exception as e:
            logger.error(f"Redis get state error: {e}")
            return None

    async def delete_user_state(self, user_id: int) -> bool:
        """Удалить состояние пользователя."""
        if not self.redis:
            return False
        try:
            await self.redis.delete(f"user:{user_id}:state")
            return True
        except Exception as e:
            logger.error(f"Redis delete state error: {e}")
            return False

    # --- FSM ШАГИ (с TTL) ---

    async def set_fsm_step(self, user_id: int, step: FSMState, ttl: int = 300) -> bool:
        """Сохранить временный FSM-шаг (по умолчанию 5 минут)."""
        if not self.redis:
            return False
        try:
            await self.redis.setex(f"user:{user_id}:fsm", ttl, step)
            return True
        except Exception as e:
            logger.error(f"Redis set FSM step error: {e}")
            return False

    async def get_fsm_step(self, user_id: int) -> Optional[str]:
        """Получить FSM-шаг пользователя."""
        if not self.redis:
            return None
        try:
            return await self.redis.get(f"user:{user_id}:fsm")
        except Exception as e:
            logger.error(f"Redis get FSM step error: {e}")
            return None

    async def delete_fsm_step(self, user_id: int) -> bool:
        """Удалить FSM-шаг."""
        if not self.redis:
            return False
        try:
            await self.redis.delete(f"user:{user_id}:fsm")
            return True
        except Exception as e:
            logger.error(f"Redis delete FSM step error: {e}")
            return False

    # --- TOKEN ---

    async def set_user_token(self, user_id: int, token: str) -> bool:
        """Сохранить токен пользователя (без TTL, до logout)."""
        if not self.redis:
            return False
        try:
            await self.redis.set(f"user:{user_id}:token", token)
            return True
        except Exception as e:
            logger.error(f"Redis set token error: {e}")
            return False

    async def get_user_token(self, user_id: int) -> Optional[str]:
        """Получить токен пользователя."""
        if not self.redis:
            return None
        try:
            return await self.redis.get(f"user:{user_id}:token")
        except Exception as e:
            logger.error(f"Redis get token error: {e}")
            return None

    async def delete_user_token(self, user_id: int) -> bool:
        """Удалить токен пользователя (при logout)."""
        if not self.redis:
            return False
        try:
            await self.redis.delete(f"user:{user_id}:token")
            return True
        except Exception as e:
            logger.error(f"Redis delete token error: {e}")
            return False


# Global instance
redis_client = RedisClient()
