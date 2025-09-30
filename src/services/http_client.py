import httpx
from typing import Any, Dict, Optional, Callable, Awaitable

from src.config import settings
from src.database.redis_client import redis_client

API_URL = f"{settings.api_base_url}/api/v1"


class BotHttpClient:
    """
    Обёртка над httpx с автообновлением access по refresh при 401 один раз.
    """

    def __init__(self, base_url: str = API_URL, timeout: float = 15.0):
        self.base_url = base_url
        self.timeout = httpx.Timeout(timeout)

    async def _refresh_tokens(self, user_id: int) -> bool:
        refresh = await redis_client.get_user_refresh_token(user_id)
        if not refresh:
            return False
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as c:
            resp = await c.post("/auth/refresh", json={"refresh_token": refresh})
        if resp.status_code != 200:
            return False
        data = resp.json()
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        if not new_access or not new_refresh:
            return False
        await redis_client.set_user_tokens(user_id, new_access, new_refresh)
        return True

    async def request(
        self,
        user_id: int,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        access = await redis_client.get_user_access_token(user_id)
        headers = {"Authorization": f"Bearer {access}"} if access else {}

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as c:
            resp = await c.request(method, path, json=json, params=params, headers=headers)

            if resp.status_code == 401:
                refreshed = await self._refresh_tokens(user_id)
                if refreshed:
                    access = await redis_client.get_user_access_token(user_id)
                    headers = {"Authorization": f"Bearer {access}"} if access else {}
                    resp = await c.request(method, path, json=json, params=params, headers=headers)

            return resp


client = BotHttpClient()
