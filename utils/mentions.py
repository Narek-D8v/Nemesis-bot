import re
import time

from aiogram.types import Message


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
            from bot import bot
            async for member in bot.get_chat_members(message.chat.id):
                if member.user.username and member.user.username.lower() == username:
                    return member.user.id
        except Exception:
            pass

    num_match = re.search(r'\b(\d{6,})\b', text)
    if num_match:
        return int(num_match.group(1))

    return None
