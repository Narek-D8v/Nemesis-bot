import asyncio
import logging

import aiosqlite
from aiogram import Router
from aiogram.types import ChatJoinRequest

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)

TOOLS_ROUTER = Router()


@TOOLS_ROUTER.chat_join_request()
async def on_join_request(event: ChatJoinRequest):
    from .handlers import on_chat_join_request
    await on_chat_join_request(event)


class GroupToolsPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        self.router.include_router(TOOLS_ROUTER)
        from .handlers import handle_group_command
        register_hook("group_tools", handle_group_command)
        self.add_background_task(self._run_autokick_silent())
        logger.info("GroupTools plugin loaded")

    async def on_unload(self):
        unregister_hook("group_tools")
        logger.info("GroupTools plugin unloaded")

    async def _run_autokick_silent(self):
        from .handlers import _autokick_silent_loop
        await _autokick_silent_loop()

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS group_rules (
                    chat_id INTEGER PRIMARY KEY,
                    text TEXT NOT NULL DEFAULT '',
                    entities_json TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS group_tags (
                    chat_id INTEGER,
                    user_id INTEGER,
                    tag TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS user_first_seen (
                    user_id INTEGER PRIMARY KEY,
                    first_seen_at INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS auto_join_requests (
                    chat_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0
                );
            """)
            await conn.commit()
            try:
                await conn.execute(
                    "ALTER TABLE group_rules ADD COLUMN entities_json TEXT NOT NULL DEFAULT ''"
                )
                await conn.commit()
            except Exception:
                pass
            try:
                await conn.execute(
                    "ALTER TABLE group_rules ADD COLUMN html_parts TEXT NOT NULL DEFAULT '[]'"
                )
                await conn.commit()
            except Exception:
                pass
