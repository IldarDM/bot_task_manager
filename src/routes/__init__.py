from aiogram import Router


def setup_handlers() -> Router:
    """Подключение всех роутеров."""
    from . import core, auth, category, fsm

    router = Router()
    router.include_router(core.router)
    router.include_router(auth.router)
    router.include_router(category.router)

    router.include_router(fsm.router)

    return router