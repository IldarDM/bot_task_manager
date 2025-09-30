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
