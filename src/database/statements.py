from enum import StrEnum

class UserState(StrEnum):
    """Долгосрочные состояния пользователя."""
    STARTED = "started"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"

class FSMState(StrEnum):
    """Краткосрочные состояния пользователя."""
    # Auth
    LOGIN_EMAIL = "login_email"
    LOGIN_PASSWORD = "login_password"
    REGISTER_EMAIL = "register_email"
    REGISTER_PASSWORD = "register_password"
    REGISTER_PASSWORD_CONFIRM = "register_password_confirm"

    # Tasks
    TASK_CREATE_TITLE = "task_create_title"
    TASK_CREATE_DESCRIPTION = "task_create_description"
    TASK_CREATE_CATEGORY = "task_create_category"
    TASK_CREATE_PRIORITY = "task_create_priority"

    TASK_FILTER_STATUS = "task_filter_status"
    TASK_FILTER_PRIORITY = "task_filter_priority"

    # Categories
    CATEGORY_CREATE_NAME = "category_create_name"
    CATEGORY_UPDATE_NAME = "category_update_name"
