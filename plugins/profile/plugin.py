import logging
import re

import aiosqlite
from aiogram import F, Router
from aiogram.types import Message

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)

ANKETA_ROUTER = Router()
ANKETA_RE = re.compile(r'^(моя\s+)?анкета\b', re.IGNORECASE)

@ANKETA_ROUTER.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and ANKETA_RE.match(msg.text.strip()))
async def anketta_direct_handler(message: Message):
    from .handlers import handle_profile_commands
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""
    settings = await db.get_settings(chat_id)
    await handle_profile_commands(message, chat_id, user_id, text, settings)


class ProfilePlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        self.router.include_router(ANKETA_ROUTER)
        from .handlers import handle_profile_commands
        register_hook("profile", handle_profile_commands)
        logger.info("Profile plugin loaded")

    async def on_unload(self):
        unregister_hook("profile")
        logger.info("Profile plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS profile_global (
                    user_id INTEGER PRIMARY KEY,
                    gender TEXT DEFAULT '',
                    city TEXT DEFAULT '',
                    birthday TEXT DEFAULT '',
                    birthday_visibility TEXT DEFAULT 'full',
                    description TEXT DEFAULT '',
                    motto TEXT DEFAULT '',
                    achievements_visible INTEGER DEFAULT 1,
                    registered_at INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS profile_chat (
                    chat_id INTEGER,
                    user_id INTEGER,
                    nickname TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    citizenship INTEGER DEFAULT 0,
                    profile_visible INTEGER DEFAULT 1,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS profile_subscriptions (
                    subscriber_id INTEGER,
                    target_id INTEGER,
                    created_at INTEGER,
                    PRIMARY KEY (subscriber_id, target_id)
                );
                CREATE TABLE IF NOT EXISTS profile_achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    achievement_key TEXT,
                    title TEXT,
                    description TEXT,
                    unlocked_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS profile_restrictions (
                    chat_id INTEGER,
                    command_type TEXT,
                    min_rank INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, command_type)
                );
            """)
            await conn.commit()
