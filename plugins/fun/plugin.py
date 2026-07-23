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
            handle_criminal_article,
            handle_sin,
            handle_addiction,
            handle_state,
            handle_philosophy,
        )
        register_hook("fun_shipping", handle_shipping)
        register_hook("fun_text_games", handle_text_games)
        register_hook("fun_ping", handle_ping)
        register_hook("fun_criminal_article", handle_criminal_article)
        register_hook("fun_sin", handle_sin)
        register_hook("fun_addiction", handle_addiction)
        register_hook("fun_state", handle_state)
        register_hook("fun_philosophy", handle_philosophy)
        logger.info("Fun plugin loaded with hooks registered")

    async def on_unload(self):
        unregister_hook("fun_shipping")
        unregister_hook("fun_text_games")
        unregister_hook("fun_ping")
        unregister_hook("fun_criminal_article")
        unregister_hook("fun_sin")
        unregister_hook("fun_addiction")
        unregister_hook("fun_state")
        unregister_hook("fun_philosophy")
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
                CREATE TABLE IF NOT EXISTS fun_criminal_record (
                    user_id INTEGER,
                    chat_id INTEGER,
                    article_num TEXT,
                    article_title TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS fun_sins_record (
                    user_id INTEGER,
                    chat_id INTEGER,
                    sin_name TEXT,
                    sin_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS fun_addictions_record (
                    user_id INTEGER,
                    chat_id INTEGER,
                    addiction_name TEXT,
                    addiction_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS fun_states_record (
                    user_id INTEGER,
                    chat_id INTEGER,
                    state_name TEXT,
                    state_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS fun_philosophies_record (
                    user_id INTEGER,
                    chat_id INTEGER,
                    philosophy_name TEXT,
                    philosophy_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
            """)
            await conn.commit()
