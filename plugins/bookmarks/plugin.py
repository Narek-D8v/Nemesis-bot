import logging

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)


class BookmarksPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        from .handlers import handle_bookmark_commands
        register_hook("bookmarks", handle_bookmark_commands)
        logger.info("Bookmarks plugin loaded")

    async def on_unload(self):
        unregister_hook("bookmarks")
        logger.info("Bookmarks plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    title TEXT,
                    text_content TEXT,
                    message_id INTEGER,
                    created_at INTEGER,
                    is_hidden INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS bookmarks_banned (
                    chat_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            await conn.commit()
