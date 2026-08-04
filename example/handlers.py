from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command


def setup_handlers(router: Router):

    @router.message(Command("hello"))
    async def cmd_hello(message: Message):
        name = message.from_user.first_name or "User"
        await message.reply(f"👋 Привет, {name}! Это example-плагин.")

    @router.message(Command("echo"))
    async def cmd_echo(message: Message):
        text = message.text.replace("/echo", "", 1).strip()
        if not text:
            await message.reply("Напиши текст после /echo")
            return
        await message.reply(f"🔁 {text}")

    @router.message(F.text.lower() == "ping")
    async def cmd_ping(message: Message):
        await message.reply("🏓 Pong! (example plugin)")
