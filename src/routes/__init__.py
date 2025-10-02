from aiogram import Router


def setup_handlers() -> Router:
    """Connecting all routers."""
    from . import core, auth, category, task, tasks_list

    router = Router()
    router.include_router(core.router)
    router.include_router(auth.router)
    router.include_router(category.router)
    router.include_router(tasks_list.router)
    router.include_router(task.router)

    return router
