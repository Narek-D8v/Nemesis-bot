import re

from aiogram.types import Message
from aiogram.enums import MessageEntityType
from bot import bot


async def extract_user(text: str, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                return entity.user.id

    id_match = re.search(r'id[=:](\d+)', text, re.IGNORECASE)
    if id_match:
        return int(id_match.group(1))

    mention = re.search(r'@(\w+)', text)
    if mention:
        username = mention.group(1).lower()
        from db import db
        user_id = await db.resolve_username_from_cache(message.chat.id, username)
        if user_id:
            return user_id
        try:
            admins = await bot.get_chat_administrators(message.chat.id)
            for admin in admins:
                if admin.user.username and admin.user.username.lower() == username:
                    return admin.user.id
        except Exception:
            pass

    num_match = re.search(r'\b(\d{5,})\b', text)
    if num_match:
        return int(num_match.group(1))

    return None


async def cache_user_from_message(message: Message):
    user = message.from_user
    if user and not user.is_bot and user.username:
        from db import db
        await db.cache_username(message.chat.id, user.id, user.username.lower())


async def cache_user_from_member(chat_id: int, user_id: int, username: str | None):
    if username:
        from db import db
        await db.cache_username(chat_id, user_id, username.lower())
