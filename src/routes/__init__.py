from aiogram import Router


def setup_handlers() -> Router:
    """Connecting all routers."""
    from . import auth, category, core, tasks

    router = Router()
    router.include_router(core.router)
    router.include_router(auth.router)
    router.include_router(category.router)
    router.include_router(tasks.router)

    return router
