from aiogram import Bot, Dispatcher


def create_bot(token: str) -> Bot:
    """Create and configure bot instance."""
    return Bot(token=token)


def create_dispatcher() -> Dispatcher:
    """Create and configure dispatcher instance."""
    return Dispatcher()