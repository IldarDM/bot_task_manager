from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.client.default import DefaultBotProperties
from typing import Optional


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))


def create_dispatcher(storage: Optional[BaseStorage] = None) -> Dispatcher:
    return Dispatcher(storage=storage)
