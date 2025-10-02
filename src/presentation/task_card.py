from typing import Dict, Optional
from src.utils.translations import tr_status, tr_priority
from src.utils.dates import format_due
from src.keyboards.task_actions import task_actions_keyboard


def build_task_text(task: Dict) -> str:
    title = task.get("title", "Без названия")
    status = tr_status(task.get("status"))
    priority = tr_priority(task.get("priority"))
    category = (task.get("category") or {}).get("name") if task.get("category") else "—"
    due_date = task.get("due_date")

    text = (
        f"📝 <b>{title}</b>\n"
        f"Статус: {status}\n"
        f"Приоритет: {priority}\n"
        f"Категория: {category}"
    )
    if due_date:
        text += f"\nДедлайн: {format_due(due_date)}"
    return text


def build_task_keyboard(task: Dict):
    task_id = task.get("id")
    status = task.get("status")
    archived = bool(task.get("archived", False))
    return task_actions_keyboard(task_id, status, archived)
