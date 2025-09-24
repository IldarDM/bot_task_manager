from aiogram import Router


def setup_handlers() -> Router:
    """Setup all routes."""
    from . import core, auth

    router = Router()
    router.include_router(core.router)
    router.include_router(auth.router)

    return router