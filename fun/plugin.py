import logging

import aiosqlite

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from db import db

logger = logging.getLogger(__name__)

# Ежедневные «карточки» хранятся по (chat_id, user_id):
# cooldown действует отдельно в каждом чате — у пользователя своя карточка на каждый чат.
DAILY_COLUMNS = {
    "fun_criminal_record": ("article_num", "article_title", "created_at"),
    "fun_sins_record": ("sin_name", "sin_desc", "created_at"),
    "fun_addictions_record": ("addiction_name", "addiction_desc", "created_at"),
    "fun_states_record": ("state_name", "state_desc", "created_at"),
    "fun_philosophies_record": ("philosophy_name", "philosophy_desc", "created_at"),
    "fun_souls_record": ("soul_name", "soul_desc", "soul_image", "created_at"),
    "fun_warriors_record": ("warrior_name", "warrior_desc", "created_at"),
}


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
            handle_soul,
            handle_warrior,
            handle_chat_regime,
        )
        register_hook("fun_shipping", handle_shipping)
        register_hook("fun_text_games", handle_text_games)
        register_hook("fun_ping", handle_ping)
        register_hook("fun_criminal_article", handle_criminal_article)
        register_hook("fun_sin", handle_sin)
        register_hook("fun_addiction", handle_addiction)
        register_hook("fun_state", handle_state)
        register_hook("fun_philosophy", handle_philosophy)
        register_hook("fun_soul", handle_soul)
        register_hook("fun_warrior", handle_warrior)
        register_hook("fun_chat_regime", handle_chat_regime)
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
        unregister_hook("fun_soul")
        unregister_hook("fun_warrior")
        unregister_hook("fun_chat_regime")
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
                    chat_id INTEGER,
                    user_id INTEGER,
                    article_num TEXT,
                    article_title TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_sins_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    sin_name TEXT,
                    sin_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_addictions_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    addiction_name TEXT,
                    addiction_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_states_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    state_name TEXT,
                    state_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_philosophies_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    philosophy_name TEXT,
                    philosophy_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_souls_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    soul_name TEXT,
                    soul_desc TEXT,
                    soul_image TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_warriors_record (
                    chat_id INTEGER,
                    user_id INTEGER,
                    warrior_name TEXT,
                    warrior_desc TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS fun_chat_regime (
                    chat_id INTEGER PRIMARY KEY,
                    regime_name TEXT,
                    regime_desc TEXT,
                    set_by INTEGER,
                    created_at INTEGER
                );
            """)
            await self._migrate_daily_tables(conn)
            await conn.commit()
            logger.info("Fun plugin tables ensured (daily records keyed by chat_id + user_id)")

    @staticmethod
    async def _migrate_daily_tables(conn):
        """Приводит ежедневные таблицы к схеме «(chat_id, user_id) PRIMARY KEY».

        Кулдаун действует отдельно в каждом чате: у пользователя своя карточка
        (воин/душа/грех и т.д.) на каждый чат. Если таблицы нет — создаётся.
        Старые таблицы без chat_id пересоздаются с chat_id.
        """
        for table, cols in DAILY_COLUMNS.items():
            cur = await conn.execute(f"PRAGMA table_info({table})")
            existing = {r[1] for r in await cur.fetchall()}
            if not existing:
                cols_sql = ", ".join(f"{c} TEXT" for c in cols)
                await conn.execute(f"CREATE TABLE {table} (chat_id INTEGER, user_id INTEGER, {cols_sql}, PRIMARY KEY (chat_id, user_id))")
                continue
            if "chat_id" in existing and "user_id" in existing:
                continue  # уже новая схема

            await conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
            cols_sql = ", ".join(f"{c} TEXT" for c in cols)
            await conn.execute(f"CREATE TABLE {table} (chat_id INTEGER, user_id INTEGER, {cols_sql}, PRIMARY KEY (chat_id, user_id))")
            if "user_id" in existing and "created_at" in existing:
                cols_sel = ", ".join(f"MAX({c})" for c in cols)
                await conn.execute(
                    f"INSERT INTO {table} (chat_id, user_id, {', '.join(cols)}) "
                    f"SELECT 0, user_id, {cols_sel} FROM {table}_old GROUP BY user_id"
                )
            await conn.execute(f"DROP TABLE IF EXISTS {table}_old")
