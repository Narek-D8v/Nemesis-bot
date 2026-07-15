import logging

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)


class MentionsPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        from .handlers import handle_mention_commands
        register_hook("mentions", handle_mention_commands)
        logger.info("Mentions plugin loaded")

    async def on_unload(self):
        unregister_hook("mentions")
        logger.info("Mentions plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS mention_restrictions (
                    chat_id INTEGER,
                    command_type TEXT,
                    min_rank INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, command_type)
                );
            """)
            await conn.commit()
