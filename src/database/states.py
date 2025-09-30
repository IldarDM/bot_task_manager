from enum import StrEnum

class UserState(StrEnum):
    """Долгосрочные состояния пользователя."""
    STARTED = "started"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"