import asyncio
import logging
import time

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)

TAX_RATING_INTERVAL = 3 * 86400


class ReputationPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        await self._init_db()
        from .handlers import (
            handle_rating_vote,
            handle_rating_commands,
        )
        register_hook("rep_vote", handle_rating_vote)
        register_hook("rep_commands", handle_rating_commands)

        asyncio.create_task(self._tax_loop())
        logger.info("Reputation plugin loaded, tax loop started")

    async def on_unload(self):
        unregister_hook("rep_vote")
        unregister_hook("rep_commands")
        logger.info("Reputation plugin unloaded")

    async def _init_db(self):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS rep_rating (
                    chat_id INTEGER,
                    user_id INTEGER,
                    rating INTEGER DEFAULT 0,
                    stars INTEGER DEFAULT 0,
                    last_tax_rating INTEGER DEFAULT 0,
                    pluses_given INTEGER DEFAULT 0,
                    pluses_received INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            await conn.commit()

    async def _tax_loop(self):
        while True:
            try:
                await self._apply_taxes()
            except Exception as e:
                logger.error(f"Tax loop error: {e}")
            await asyncio.sleep(3600)

    async def _apply_taxes(self):
        now = int(time.time())
        async with aiosqlite.connect(db.db_path) as conn:
            cutoff_rating = now - TAX_RATING_INTERVAL
            await conn.execute("""
                UPDATE rep_rating
                SET rating = CAST(rating * 0.95 AS INTEGER),
                    last_tax_rating = ?
                WHERE last_tax_rating < ? AND rating != 0
            """, (now, cutoff_rating))

            await conn.commit()
            logger.debug("Reputation taxes applied")
