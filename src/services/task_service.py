import httpx

from ..config import settings

API_URL = f"{settings.api_base_url}/api/v1"


class TaskService:
    @staticmethod
    async def list_tasks(token: str, params: dict = None):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_URL}/tasks/",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {}
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("tasks", [])

    @staticmethod
    async def get_task(token: str, task_id: int):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            return resp.json() if resp.status_code == 200 else None

    @staticmethod
    async def create_task(token: str, task_data: dict):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{API_URL}/tasks/",
                headers={"Authorization": f"Bearer {token}"},
                json=task_data
            )
            return resp.json() if resp.status_code == 201 else None

    @staticmethod
    async def update_task(token: str, task_id: int, task_data: dict):
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"},
                json=task_data
            )
            return resp.json() if resp.status_code == 200 else None

    @staticmethod
    async def delete_task(token: str, task_id: int):
        async with httpx.AsyncClient() as client:
            return await client.delete(
                f"{API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

    @staticmethod
    async def restore_task(token: str, task_id: int):
        async with httpx.AsyncClient() as client:
            return await client.post(
                f"{API_URL}/tasks/{task_id}/restore",
                headers={"Authorization": f"Bearer {token}"}
            )

    @staticmethod
    async def archive_task(token: str, task_id: int):
        async with httpx.AsyncClient() as client:
            return await client.post(
                f"{API_URL}/tasks/{task_id}/archive",
                headers={"Authorization": f"Bearer {token}"}
            )

    @staticmethod
    async def get_stats(token: str):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_URL}/tasks/stats/overview",
                headers={"Authorization": f"Bearer {token}"}
            )
            return resp.json() if resp.status_code == 200 else None
