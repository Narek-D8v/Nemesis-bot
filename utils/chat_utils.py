import time
import asyncio

from bot import bot, logger
from handlers.messages import is_admin


async def delete_messages(chat_id: int, message_ids: list, silent: bool = False) -> int:
    now = int(time.time())
    forty_eight_hours = 48 * 3600
    valid = []
    async for msg in bot.get_chat_history(chat_id, limit=len(message_ids)):
        if msg.message_id in message_ids and now - msg.date.timestamp() < forty_eight_hours:
            valid.append(msg.message_id)

    deleted = 0
    for i in range(0, len(valid), 100):
        batch = valid[i:i + 100]
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Delete batch failed: {e}")
    return deleted


async def get_messages_above(chat_id: int, from_msg_id: int, limit: int) -> list:
    msg_ids = []
    try:
        async for msg in bot.get_chat_history(chat_id, limit=limit, offset_id=from_msg_id):
            if msg.message_id != from_msg_id:
                msg_ids.append(msg.message_id)
    except Exception as e:
        logger.warning(f"get_messages_above failed: {e}")
    return msg_ids


async def get_messages_below(chat_id: int, from_msg_id: int, limit: int = None) -> list:
    msg_ids = [from_msg_id]
    try:
        async for msg in bot.get_chat_history(chat_id, limit=limit, offset_id=from_msg_id):
            msg_ids.append(msg.message_id)
    except Exception as e:
        logger.warning(f"get_messages_below failed: {e}")
    return msg_ids


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
