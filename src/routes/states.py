from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    login_email = State()
    login_password = State()
    reg_email = State()
    reg_password = State()
    reg_password_confirm = State()


class CategoryStates(StatesGroup):
    create_name = State()
    update_name = State()


class TaskStates(StatesGroup):
    # Create
    create_title = State()
    create_description = State()
    create_priority = State()
    create_category = State()
    create_due_date = State()

    # Update
    update_title = State()
    update_desc = State()
    update_due_manual = State()