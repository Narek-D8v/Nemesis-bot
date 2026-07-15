import re

from aiogram.types import Message
from bot import bot


async def extract_user(text: str, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    id_match = re.search(r'id[=:](\d+)', text, re.IGNORECASE)
    if id_match:
        return int(id_match.group(1))

    mention = re.search(r'@(\w+)', text)
    if mention:
        username = mention.group(1).lower()
        try:
            member = await bot.get_chat_member(message.chat.id, username)
            if member.user.username and member.user.username.lower() == username:
                return member.user.id
        except Exception:
            pass

    num_match = re.search(r'\b(\d{5,})\b', text)
    if num_match:
        return int(num_match.group(1))

    return None
