from typing import List, Dict
from src.services.http_client import client


class CategoriesAPI:
    @staticmethod
    async def list(user_id: int) -> List[Dict]:
        resp = await client.request(user_id, "GET", "/categories/")
        if resp.status_code != 200:
            return []
        data = resp.json() or []
        items = data if isinstance(data, list) else []
        cleaned: List[Dict] = []
        for item in items:
            name = str(item.get("name", "")).strip().lower()
            if name in {"uncategorized", "без категории"}:
                continue
            cleaned.append(item)
        return cleaned
