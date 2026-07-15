import logging

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)


class FunPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        from .handlers import (
            handle_shipping,
            handle_text_games,
            handle_ping,
        )
        register_hook("fun_shipping", handle_shipping)
        register_hook("fun_text_games", handle_text_games)
        register_hook("fun_ping", handle_ping)
        logger.info("Fun plugin loaded with hooks registered")

    async def on_unload(self):
        unregister_hook("fun_shipping")
        unregister_hook("fun_text_games")
        unregister_hook("fun_ping")
        logger.info("Fun plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS fun_shipping_pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user1_id INTEGER,
                    user2_id INTEGER,
                    shipper_id INTEGER,
                    created_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS fun_shipping_optout (
                    chat_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            await conn.commit()
