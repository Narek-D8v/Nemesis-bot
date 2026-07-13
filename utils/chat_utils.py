import time
import asyncio

from bot import bot, logger
from handlers.messages import is_admin


async def delete_messages(chat_id: int, message_ids: list, silent: bool = False) -> int:
    deleted = 0
    for i in range(0, len(message_ids), 100):
        batch = message_ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Delete batch failed: {e}")
    return deleted


async def get_messages_above(chat_id: int, from_msg_id: int, limit: int) -> list:
    return list(range(max(1, from_msg_id - limit), from_msg_id))


async def get_messages_below(chat_id: int, from_msg_id: int, limit: int = None) -> list:
    count = limit or 100
    return list(range(from_msg_id + 1, from_msg_id + 1 + count))


async def kick_user(chat_id: int, user_id: int, reason: str = ""):
    if await is_admin(chat_id, user_id):
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logger.warning(f"Kick failed for {user_id} in {chat_id}: {e}")
        return False


async def ban_user_simple(chat_id: int, user_id: int, reason: str = ""):
    if await is_admin(chat_id, user_id):
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logger.warning(f"Ban failed for {user_id} in {chat_id}: {e}")
        return False
