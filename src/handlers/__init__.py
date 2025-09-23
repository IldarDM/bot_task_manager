from aiogram import Router


def setup_handlers() -> Router:
    """Setup all handlers."""
    from . import basic

    router = Router()
    router.include_router(basic.router)

    return router