import logging

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)


class AwardsPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        from .handlers import handle_award_commands
        register_hook("awards", handle_award_commands)
        logger.info("Awards plugin loaded")

    async def on_unload(self):
        unregister_hook("awards")
        logger.info("Awards plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS awards_medals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    giver_id INTEGER,
                    degree INTEGER DEFAULT 1,
                    description TEXT,
                    created_at INTEGER,
                    expires_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS awards_givers (
                    chat_id INTEGER,
                    user_id INTEGER,
                    max_degree INTEGER DEFAULT 1,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS awards_restrictions (
                    chat_id INTEGER,
                    command_type TEXT,
                    min_rank INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, command_type)
                );
            """)
            await conn.commit()
