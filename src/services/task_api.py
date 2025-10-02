from typing import Any, Dict, Optional
from src.services.http_client import client


class TasksAPI:
    @staticmethod
    async def list(user_id: int, params: Optional[Dict[str, Any]] = None):
        return await client.request(user_id, "GET", "/tasks/", params=params or {})

    @staticmethod
    async def get(user_id: int, task_id: int):
        return await client.request(user_id, "GET", f"/tasks/{task_id}")

    @staticmethod
    async def create(user_id: int, payload: Dict[str, Any]):
        return await client.request(user_id, "POST", "/tasks/", json=payload)

    @staticmethod
    async def patch(user_id: int, task_id: int, payload: Dict[str, Any]):
        return await client.request(user_id, "PATCH", f"/tasks/{task_id}", json=payload)

    @staticmethod
    async def delete(user_id: int, task_id: int):
        return await client.request(user_id, "DELETE", f"/tasks/{task_id}")

    @staticmethod
    async def archive(user_id: int, task_id: int):
        return await client.request(user_id, "POST", f"/tasks/{task_id}/archive")

    @staticmethod
    async def restore(user_id: int, task_id: int):
        return await client.request(user_id, "POST", f"/tasks/{task_id}/restore")
