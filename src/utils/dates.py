import re
from datetime import date, datetime, timedelta

_DD_MM_YYYY_DASH = re.compile(r"^(?P<d>\d{1,2})-(?P<m>\d{1,2})-(?P<y>\d{4})$")
_DD_MM_YYYY_DOT  = re.compile(r"^(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})$")
_YYYY_MM_DD      = re.compile(r"^(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})$")

def _iso_today() -> str:
    return date.today().isoformat()

def _iso_plus_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()

def parse_due(text: str) -> str | None:
    """
    Возвращает ISO YYYY-MM-DD или None.
    Поддерживает:
      "-"  -> None (снять дедлайн)
      "сегодня" / "завтра" / "+N"
      "DD-MM-YYYY" / "DD.MM.YYYY" / "YYYY-MM-DD"
    """
    if not text:
        return None
    t = text.strip().lower()
    if t == "-":
        return None
    if t == "сегодня":
        return _iso_today()
    if t == "завтра":
        return _iso_plus_days(1)
    if t.startswith("+") and t[1:].isdigit():
        return _iso_plus_days(int(t[1:]))

    m = _DD_MM_YYYY_DASH.match(t)
    if m:
        d, mth, y = int(m["d"]), int(m["m"]), int(m["y"])
        return date(y, mth, d).isoformat()

    m = _DD_MM_YYYY_DOT.match(t)
    if m:
        d, mth, y = int(m["d"]), int(m["m"]), int(m["y"])
        return date(y, mth, d).isoformat()

    m = _YYYY_MM_DD.match(t)
    if m:
        y, mth, d = int(m["y"]), int(m["m"]), int(m["d"])
        return date(y, mth, d).isoformat()

    try:
        return datetime.fromisoformat(t).date().isoformat()
    except Exception:
        return None


def format_due(iso_date_str: str) -> str:
    """Показываем пользователю как DD-MM-YYYY."""
    try:
        d = datetime.fromisoformat(iso_date_str).date()
        return d.strftime("%d-%m-%Y")
    except Exception:
        return iso_date_str or "—"
