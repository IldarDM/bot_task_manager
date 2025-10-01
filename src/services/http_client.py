import json
import logging
import uuid
from enum import Enum
from typing import Any, Dict, Optional
import httpx

from src.config import settings
from src.database.redis_client import redis_client

API_URL = f"{settings.api_base_url}/api/v1"
logger = logging.getLogger(__name__)

MAX_LOG_BODY = 2000


class BotHttpClient:
    """
    Обёртка над httpx с автообновлением access по refresh при 401 один раз.
    Добавлено подробное логгирование и нормализация JSON перед отправкой.
    """

    def __init__(self, base_url: str = API_URL, timeout: float = 15.0):
        self.base_url = base_url
        self.timeout = httpx.Timeout(timeout)

    def _to_jsonable(self, obj: Any) -> Any:
        """
        Делает объект сериализуемым для JSON:
        - Enum -> value
        - pydantic BaseModel -> model_dump()
        - dataclass -> asdict
        - set -> list
        - dict/list/tuple -> рекурсивно
        - всё остальное -> как есть
        """
        # Enum
        if isinstance(obj, Enum):
            return obj.value

        try:
            from pydantic import BaseModel  # type: ignore
            if isinstance(obj, BaseModel):  # noqa
                return self._to_jsonable(obj.model_dump())
        except Exception:
            pass

        # dataclass
        try:
            from dataclasses import is_dataclass, asdict
            if is_dataclass(obj):
                return self._to_jsonable(asdict(obj))
        except Exception:
            pass

        # mapping
        if isinstance(obj, dict):
            return {k: self._to_jsonable(v) for k, v in obj.items()}

        # sequence
        if isinstance(obj, (list, tuple)):
            return [self._to_jsonable(v) for v in obj]

        # set
        if isinstance(obj, set):
            return [self._to_jsonable(v) for v in obj]

        return obj

    def _safe_body_for_log(self, data: Optional[Dict[str, Any]]) -> Any:
        if data is None:
            return None
        try:
            norm = self._to_jsonable(data)
            json.dumps(norm, ensure_ascii=False)
            return norm
        except Exception:
            return "<unserializable>"

    async def _refresh_tokens(self, user_id: int) -> bool:
        refresh = await redis_client.get_user_refresh_token(user_id)
        if not refresh:
            logger.warning("No refresh token in redis for user_id=%s", user_id)
            return False

        req_id = str(uuid.uuid4())
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as c:
                logger.info(
                    "API → POST /auth/refresh | req_id=%s | user_id=%s",
                    req_id, user_id
                )
                resp = await c.post(
                    "/auth/refresh",
                    json={"refresh_token": refresh},
                    headers={"X-Request-ID": req_id, "X-User-ID": str(user_id)},
                )
        except httpx.HTTPError as e:
            logger.exception("Refresh transport error | req_id=%s | user_id=%s | %s", req_id, user_id, e)
            return False

        if resp.status_code != 200:
            body_text = resp.text or ""
            body_json = None
            try:
                body_json = resp.json()
            except Exception:
                pass
            logger.error(
                "API ← %s POST /auth/refresh | req_id=%s | user_id=%s | resp_json=%s | resp_text=%s",
                resp.status_code, req_id, user_id, body_json, body_text[:MAX_LOG_BODY],
            )
            return False

        data = resp.json()
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        if not new_access or not new_refresh:
            logger.error(
                "Refresh response missing tokens | req_id=%s | user_id=%s | payload=%s",
                req_id, user_id, data
            )
            return False

        await redis_client.set_user_tokens(user_id, new_access, new_refresh)
        logger.info("Tokens refreshed successfully | req_id=%s | user_id=%s", req_id, user_id)
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

        req_id = str(uuid.uuid4())
        headers["X-Request-ID"] = req_id
        headers["X-User-ID"] = str(user_id)

        json_normalized = self._to_jsonable(json) if json is not None else None
        body_for_log = self._safe_body_for_log(json_normalized)
        # -----------------------------------------------------------------------

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as c:
            logger.info(
                "API → %s %s | req_id=%s | user_id=%s | params=%s | json=%s",
                method.upper(), path, req_id, user_id, params, body_for_log
            )
            try:
                resp = await c.request(method, path, json=json_normalized, params=params, headers=headers)
            except httpx.HTTPError as e:
                logger.exception(
                    "API transport error | req_id=%s | user_id=%s | %s %s | error=%s",
                    req_id, user_id, method.upper(), path, e
                )
                raise

            if resp.status_code == 401:
                logger.warning(
                    "401 received, trying token refresh | req_id=%s | user_id=%s | %s %s",
                    req_id, user_id, method.upper(), path
                )
                refreshed = await self._refresh_tokens(user_id)
                if refreshed:
                    access = await redis_client.get_user_access_token(user_id)
                    headers["Authorization"] = f"Bearer {access}" if access else ""
                    try:
                        resp = await c.request(method, path, json=json_normalized, params=params, headers=headers)
                    except httpx.HTTPError as e:
                        logger.exception(
                            "API transport error after refresh | req_id=%s | user_id=%s | %s %s | error=%s",
                            req_id, user_id, method.upper(), path, e
                        )
                        raise
                else:
                    logger.error(
                        "Token refresh failed, returning original 401 | req_id=%s | user_id=%s",
                        req_id, user_id
                    )

            if resp.status_code >= 400:
                resp_text = resp.text or ""
                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = None
                logger.error(
                    "API ← %s %s %s | req_id=%s | user_id=%s | resp_json=%s | resp_text=%s",
                    resp.status_code, method.upper(), path, req_id, user_id,
                    resp_json, resp_text[:MAX_LOG_BODY]
                )
            else:
                logger.info(
                    "API ← %s %s %s | req_id=%s | user_id=%s",
                    resp.status_code, method.upper(), path, req_id, user_id
                )

            return resp


client = BotHttpClient()
