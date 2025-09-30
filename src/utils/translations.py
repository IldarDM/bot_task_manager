STATUS_RU = {
    "todo": "📝 В планах",
    "in_progress": "⏳ В работе",
    "done": "✅ Выполнено",
    "archived": "📦 Архивировано",
}

PRIORITY_RU = {
    "low": "⬇️ Низкий",
    "medium": "⚖️ Средний",
    "high": "⬆️ Высокий",
    "urgent": "🔥 Срочный",
}


def tr_status(value: str | None) -> str:
    """Преобразует статус задачи в читаемый вид."""
    if not value:
        return "—"
    return STATUS_RU.get(value, value)


def tr_priority(value: str | None) -> str:
    """Преобразует приоритет задачи в читаемый вид."""
    if not value:
        return "—"
    return PRIORITY_RU.get(value, value)
