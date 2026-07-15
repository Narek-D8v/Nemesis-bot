from typing import Callable, Awaitable

from aiogram.types import Message

MessageHook = Callable[[Message, int, int, str, dict], Awaitable[bool]]

_hooks: list[tuple[str, MessageHook]] = []

def register_hook(name: str, hook: MessageHook):
    _hooks.append((name, hook))

def unregister_hook(name: str):
    global _hooks
    _hooks = [(n, h) for n, h in _hooks if n != name]

def get_hooks() -> list[MessageHook]:
    return [h for _, h in _hooks]

def clear_hooks():
    _hooks.clear()
