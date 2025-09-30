from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from typing import Optional


def create_bot(token: str) -> Bot:
    """Create and configure bot instance."""
    return Bot(token=token)


def create_dispatcher(storage: Optional[BaseStorage] = None) -> Dispatcher:
    """Create and configure dispatcher instance."""
    return Dispatcher(storage=storage)
