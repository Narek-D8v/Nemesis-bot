import time
import asyncio
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.enums import ChatType

from bot import bot, logger
from db import db
from utils import is_night_mode, esc


_init_lock = asyncio.Lock()
_init_cache: set = set()


class ChatInitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        chat_id = event.chat.id
        if chat_id in _init_cache:
            return await handler(event, data)

        if event.chat.type not in ("group", "supergroup"):
            return await handler(event, data)

        async with _init_lock:
            if chat_id in _init_cache:
                return await handler(event, data)

            from handlers.start import assign_owner_as_creator, ensure_bot_owner_rank

            try:
                if not await db.has_creator(chat_id):
                    await assign_owner_as_creator(chat_id)
            except Exception as e:
                logger.warning(f"ChatInitMiddleware assign_owner: {e}")

            try:
                await ensure_bot_owner_rank(chat_id)
            except Exception as e:
                logger.warning(f"ChatInitMiddleware ensure_rank: {e}")

            _init_cache.add(chat_id)

        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    CLEANUP_INTERVAL = 3600

    def __init__(self):
        self.user_messages: Dict[tuple, list] = defaultdict(list)
        self._last_cleanup = 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)

        if event.from_user is None:
            return await handler(event, data)
        user_id = event.from_user.id
        chat_id = event.chat.id

        if event.chat.type == ChatType.PRIVATE:
            return await handler(event, data)

        now = time.time()
        if now - self._last_cleanup > self.CLEANUP_INTERVAL:
            cutoff = now - 60
            expired = [(k, v) for k, v in self.user_messages.items() if not v or max(v) < cutoff]
            for k, _ in expired:
                del self.user_messages[k]
            self._last_cleanup = now

        settings = await db.get_settings(chat_id)
        antispam = settings.get("antispam", {})
        if not antispam.get("enabled"):
            return await handler(event, data)

        threshold = antispam.get("threshold", 5)
        if threshold == 0:
            return await handler(event, data)

        if not settings.get("count_commands_as_spam", False) and event.text.startswith("/"):
            return await handler(event, data)

        self.user_messages[(chat_id, user_id)].append(now)
        self.user_messages[(chat_id, user_id)] = [
            t for t in self.user_messages[(chat_id, user_id)] if now - t < 60
        ]

        if len(self.user_messages[(chat_id, user_id)]) > threshold:
            try:
                await event.delete()
                await db.add_log(chat_id, user_id, "delete", "Флуд")
                logger.info(f"Anti-flood: deleted message from {user_id} in {chat_id}")
                warn_msg = await event.answer(
                    f"<b>🚫 Анти-флуд:</b> {esc(event.from_user.first_name)}, не спамьте!",
                )
                await asyncio.sleep(5)
                await warn_msg.delete()
            except Exception as e:
                logger.warning(f"Anti-flood delete failed: {e}")
            return

        return await handler(event, data)


class NightModeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if not event.text and not event.caption:
            return await handler(event, data)

        if event.chat.type == ChatType.PRIVATE:
            return await handler(event, data)

        if event.from_user is None:
            return await handler(event, data)
        user_id = event.from_user.id
        chat_id = event.chat.id

        is_premium = await db.is_premium_group(chat_id)
        if not is_premium:
            return await handler(event, data)

        settings = await db.get_settings(chat_id)
        if not is_night_mode(settings):
            return await handler(event, data)

        try:
            member = await event.chat.get_member(user_id)
        except Exception:
            return await handler(event, data)
        if member.status in ("administrator", "creator"):
            return await handler(event, data)

        text = event.text or event.caption or ""
        if text.startswith("/"):
            return await handler(event, data)

        night_action = settings.get("night_mode", {}).get("action", "mute")
        try:
            await event.delete()
        except Exception:
            pass
        if night_action == "mute":
            until_date = int(time.time()) + 21600
            try:
                await event.chat.restrict(
                    user_id,
                    can_send_messages=False,
                    until_date=until_date,
                )
                await db.add_log(chat_id, user_id, "mute", "Ночной режим")
            except Exception as e:
                logger.warning(f"Night mode mute failed: {e}")
        elif night_action == "ban":
            try:
                await bot.ban_chat_member(chat_id, user_id)
                await db.add_log(chat_id, user_id, "ban", "Ночной режим")
            except Exception as e:
                logger.warning(f"Night mode ban failed: {e}")
        elif night_action == "warn":
            try:
                await db.add_warn(chat_id, user_id, 0, "Нарушение ночного режима")
                await db.add_log(chat_id, user_id, "warn", "Ночной режим")
            except Exception as e:
                logger.warning(f"Night mode warn failed: {e}")

        return
