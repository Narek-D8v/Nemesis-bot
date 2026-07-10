import json
import time
import aiosqlite

DB_PATH = "moderator_bot.db"

DEFAULT_SETTINGS = {
    "antispam": {"enabled": True, "threshold": 5},
    "captcha": {"enabled": True, "type": "button"},
    "captcha_for_suspicious": True,
    "duplicate_block": True,
    "mention_block": True,
    "forward_block": True,
    "filter_links": {"enabled": True, "action": "delete"},
    "blacklist_words": [],
    "invite_block": True,
    "mask_check": True,
    "filter_mute": {"enabled": True, "replace_with_stars": False},
    "auto_mute_after_warns": 3,
    "auto_ban_bots": True,
    "min_account_age_days": 3,
    "block_no_avatar": False,
    "warn_system": True,
    "auto_mute_durations": {"flood": 5, "links": 15, "mat": 10},
    "auto_ban_spam": True,
    "report_enabled": True,
    "logging_enabled": True,
    "greeting": {"enabled": True, "text": "Добро пожаловать, {username}!"},
    "farewell": {"enabled": True, "text": "Пока, {username}!"},
    "clear_chat_enabled": True,
    "block_bot_commands": True,
    "count_commands_as_spam": False,
    "advanced_settings": False,
    "whitelist": [],
    "blacklist": [],
    "night_mode": {"enabled": False, "start": 23, "end": 7, "action": "mute"},
    "daily_rules": {"enabled": False, "time": "09:00", "text": "Правила группы..."},
    "top_violators": False,
    "stats_period": "week",
    "aggression_level": 2,
    "bayes_enabled": True,
    "bayes_threshold": 0.7,
    "bayes_auto_train": False,
    "bayes_model": "default",
    "warn_limit": 3,
    "warn_ban_duration": 0,
    "warn_expire_days": 30,
    "mute_default_days": 7,
    "ban_default_days": 0,
    "show_moderator_tags": True,
    "moderator_rank_names": {
        "1": "Младший модератор",
        "2": "Старший модератор",
        "3": "Младший администратор",
        "4": "Старший администратор",
        "5": "Создатель"
    },
    "command_restrictions": {},
    "autokick_on_exit": False,
    "autokick_exit_count": 3,
    "autokick_exit_time": 60,
    "autokick_exit_action": "ban",
    "autokick_lurkers": False,
    "autokick_lurkers_days": 7,
    "show_join_leave": True,
    "min_register_days": 0,
    "rules": {"enabled": False, "text": ""},
    "chat_locked": False,
    "chat_link": None,
    "pinned_message": None,
    "virus_total_enabled": False,
    "virus_total_scan_files": False
}


DEFAULT_COMMAND_RANKS = {
    "warn": 1,
    "unwarn": 1,
    "warn_view": 0,
    "mute": 2,
    "unmute": 2,
    "mute_check": 0,
    "mute_list": 1,
    "ban": 3,
    "unban": 3,
    "banlist": 1,
    "kick": 2,
    "amnesty": 4,
    "ban_reason": 0,
    "promote": 4,
    "demote": 4,
    "admin_list": 0,
    "admin_call": 1,
    "cleanup_messages": 1,
    "purge": 1,
    "kick_inactive": 2,
    "kick_active": 2,
    "kick_newcomers": 2,
    "kick_deleted": 2,
    "kick_lurkers": 2,
    "kick_by_msgs": 2,
    "chat_settings": 3,
    "pin": 2,
    "set_title": 3,
    "set_description": 3,
    "set_link": 3,
    "autokick": 3,
    "lock_chat": 4,
    "tg_admin": 5,
}


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS user_premium (
                    user_id INTEGER PRIMARY KEY,
                    expires_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS group_premium (
                    chat_id INTEGER PRIMARY KEY,
                    expires_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS group_settings (
                    chat_id INTEGER PRIMARY KEY,
                    config TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    action TEXT,
                    reason TEXT,
                    timestamp INTEGER
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    reporter_id INTEGER,
                    reported_id INTEGER,
                    message TEXT,
                    timestamp INTEGER,
                    resolved INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    reason TEXT,
                    timestamp INTEGER
                );
                CREATE TABLE IF NOT EXISTS last_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    text TEXT,
                    timestamp INTEGER
                );
                CREATE TABLE IF NOT EXISTS captcha_pending (
                    user_id INTEGER,
                    chat_id INTEGER,
                    message_id INTEGER,
                    timestamp INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS bayes_stats (
                    model_name TEXT,
                    word TEXT,
                    spam_count INTEGER DEFAULT 0,
                    ham_count INTEGER DEFAULT 0,
                    PRIMARY KEY (model_name, word)
                );
                CREATE TABLE IF NOT EXISTS bayes_counts (
                    model_name TEXT PRIMARY KEY,
                    spam_total INTEGER DEFAULT 0,
                    ham_total INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS moderators (
                    chat_id INTEGER,
                    user_id INTEGER,
                    rank INTEGER DEFAULT 0,
                    assigned_by INTEGER,
                    assigned_at INTEGER,
                    is_online BOOLEAN DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at INTEGER,
                    expires_at INTEGER,
                    is_active BOOLEAN DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS mutes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at INTEGER,
                    expires_at INTEGER,
                    is_active BOOLEAN DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS bans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at INTEGER,
                    expires_at INTEGER,
                    is_active BOOLEAN DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS kicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at INTEGER,
                    is_silent BOOLEAN DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    trigger_type TEXT,
                    action TEXT,
                    duration INTEGER,
                    custom_text TEXT,
                    rank_required INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS moderator_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    moderator_id INTEGER,
                    action TEXT,
                    target_id INTEGER,
                    reason TEXT,
                    created_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS inheritances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    owner_id INTEGER,
                    heir_id INTEGER,
                    created_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS command_restrictions (
                    chat_id INTEGER,
                    command_type TEXT,
                    min_rank INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, command_type)
                );
                CREATE TABLE IF NOT EXISTS autokick_exits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    exit_count INTEGER DEFAULT 1,
                    last_exit_at INTEGER,
                    UNIQUE(chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS autokick_lurkers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    last_message_at INTEGER,
                    joined_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS chat_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    link TEXT,
                    type TEXT,
                    created_at INTEGER,
                    created_by INTEGER
                );
                CREATE TABLE IF NOT EXISTS user_last_message (
                    chat_id INTEGER,
                    user_id INTEGER,
                    last_msg_at INTEGER,
                    msg_count INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            await db.commit()

    async def get_settings(self, chat_id: int) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT config FROM group_settings WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            if row:
                try:
                    settings = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    settings = {}
                for key, val in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = val
                return settings
            return dict(DEFAULT_SETTINGS)

    async def save_settings(self, chat_id: int, settings: dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO group_settings (chat_id, config) VALUES (?, ?)",
                (chat_id, json.dumps(settings, ensure_ascii=False)),
            )
            await db.commit()

    async def is_premium_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT expires_at FROM user_premium WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row and row[0] > int(time.time()):
                return True
            return False

    async def is_premium_group(self, chat_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT expires_at FROM group_premium WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            if row and row[0] > int(time.time()):
                return True
            return False

    async def has_premium(self, chat_id: int) -> bool:
        return await self.is_premium_group(chat_id)

    async def get_bayes_settings(self, chat_id: int) -> dict:
        settings = await self.get_settings(chat_id)
        return {
            'enabled': settings.get('bayes_enabled', True),
            'threshold': settings.get('bayes_threshold', 0.7),
            'auto_train': settings.get('bayes_auto_train', False),
            'model_name': settings.get('bayes_model', 'default'),
        }

    async def set_bayes_settings(self, chat_id: int, key: str, value):
        settings = await self.get_settings(chat_id)
        settings[key] = value
        await self.save_settings(chat_id, settings)

    async def activate_premium_user(self, user_id: int, days: int = 30):
        expires_at = int(time.time()) + days * 86400
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO user_premium (user_id, expires_at) VALUES (?, ?)",
                (user_id, expires_at),
            )
            await db.commit()

    async def activate_premium_group(self, chat_id: int, days: int = 30):
        expires_at = int(time.time()) + days * 86400
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO group_premium (chat_id, expires_at) VALUES (?, ?)",
                (chat_id, expires_at),
            )
            await db.commit()

    async def add_log(self, chat_id: int, user_id: int, action: str, reason: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (chat_id, user_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, action, reason, int(time.time())),
            )
            await db.commit()

    async def get_logs(self, chat_id: int, limit: int = 50) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM logs WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return rows

    async def add_report(self, chat_id: int, reporter_id: int, reported_id: int, message: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO reports (chat_id, reporter_id, reported_id, message, timestamp) VALUES (?, ?, ?, ?, ?)",
                (chat_id, reporter_id, reported_id, message, int(time.time())),
            )
            await db.commit()

    async def get_reports(self, chat_id: int, limit: int = 20) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM reports WHERE chat_id = ? AND resolved = 0 ORDER BY timestamp DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return rows

    async def resolve_report(self, report_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE reports SET resolved = 1 WHERE id = ?", (report_id,))
            await db.commit()

    async def add_warning(self, chat_id: int, user_id: int, reason: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO warnings (chat_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, reason, int(time.time())),
            )
            await db.commit()

    async def get_warnings(self, chat_id: int, user_id: int) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY timestamp DESC",
                (chat_id, user_id),
            )
            rows = await cursor.fetchall()
            return rows

    async def clear_warnings(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            )
            await db.commit()

    async def get_user_rank(self, chat_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT rank FROM moderators WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def set_user_rank(self, chat_id: int, user_id: int, rank: int, assigned_by: int):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                """INSERT OR REPLACE INTO moderators (chat_id, user_id, rank, assigned_by, assigned_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (chat_id, user_id, rank, assigned_by, now)
            )
            await conn.commit()

    async def remove_moderator(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM moderators WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            await conn.commit()

    async def get_moderators(self, chat_id: int) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, rank, assigned_by, assigned_at FROM moderators WHERE chat_id = ? ORDER BY rank DESC",
                (chat_id,)
            )
            return await cursor.fetchall()

    async def has_moderators(self, chat_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM moderators WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            return row[0] > 0

    async def has_creator(self, chat_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM moderators WHERE chat_id = ? AND rank = 5", (chat_id,)
            )
            row = await cursor.fetchone()
            return row[0] > 0

    async def add_warn(self, chat_id: int, user_id: int, moderator_id: int, reason: str, expires_at: int | None = None):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT INTO warns (chat_id, user_id, moderator_id, reason, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, moderator_id, reason, now, expires_at)
            )
            await conn.commit()

    async def get_active_warns(self, chat_id: int, user_id: int) -> list:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, reason, created_at, expires_at, moderator_id FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)",
                (chat_id, user_id, now)
            )
            return await cursor.fetchall()

    async def count_active_warns(self, chat_id: int, user_id: int) -> int:
        warns = await self.get_active_warns(chat_id, user_id)
        return len(warns)

    async def remove_last_warn(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
            if row:
                await conn.execute(
                    "UPDATE warns SET is_active = 0 WHERE id = ?",
                    (row[0],)
                )
                await conn.commit()
                return True
            return False

    async def remove_warn_by_number(self, chat_id: int, user_id: int, num: int) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1 OFFSET ?",
                (chat_id, user_id, num - 1)
            )
            row = await cursor.fetchone()
            if row:
                await conn.execute("UPDATE warns SET is_active = 0 WHERE id = ?", (row[0],))
                await conn.commit()
                return True
            return False

    async def remove_warns_count(self, chat_id: int, user_id: int, count: int) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1 ORDER BY created_at ASC LIMIT ?",
                (chat_id, user_id, count)
            )
            ids = [row[0] for row in await cursor.fetchall()]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                await conn.execute(
                    f"UPDATE warns SET is_active = 0 WHERE id IN ({placeholders})",
                    ids
                )
                await conn.commit()
            return len(ids)

    async def clear_warns(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE warns SET is_active = 0 WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            await conn.commit()

    async def get_warnlist(self, chat_id: int, limit: int = 30) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM warns WHERE chat_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit)
            )
            return await cursor.fetchall()

    async def add_mute(self, chat_id: int, user_id: int, moderator_id: int, reason: str, expires_at: int | None = None):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT INTO mutes (chat_id, user_id, moderator_id, reason, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, moderator_id, reason, now, expires_at)
            )
            await conn.commit()

    async def get_active_mute(self, chat_id: int, user_id: int) -> tuple | None:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, reason, created_at, expires_at, moderator_id FROM mutes WHERE chat_id = ? AND user_id = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)",
                (chat_id, user_id, now)
            )
            return await cursor.fetchone()

    async def remove_mute(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE mutes SET is_active = 0 WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            await conn.commit()

    async def get_muted_users(self, chat_id: int) -> list:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, reason, created_at, expires_at FROM mutes WHERE chat_id = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)",
                (chat_id, now)
            )
            return await cursor.fetchall()

    async def add_ban(self, chat_id: int, user_id: int, moderator_id: int, reason: str, expires_at: int | None = None):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT INTO bans (chat_id, user_id, moderator_id, reason, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, moderator_id, reason, now, expires_at)
            )
            await conn.commit()

    async def get_active_ban(self, chat_id: int, user_id: int) -> tuple | None:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, reason, created_at, expires_at, moderator_id FROM bans WHERE chat_id = ? AND user_id = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)",
                (chat_id, user_id, now)
            )
            return await cursor.fetchone()

    async def remove_ban(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE bans SET is_active = 0 WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            await conn.commit()

    async def get_banned_users(self, chat_id: int) -> list:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, reason, created_at, expires_at, moderator_id FROM bans WHERE chat_id = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)",
                (chat_id, now)
            )
            return await cursor.fetchall()

    async def amnesty(self, chat_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE bans SET is_active = 0 WHERE chat_id = ?",
                (chat_id,)
            )
            await conn.commit()

    async def add_kick(self, chat_id: int, user_id: int, moderator_id: int, reason: str, is_silent: bool = False):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT INTO kicks (chat_id, user_id, moderator_id, reason, created_at, is_silent) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, moderator_id, reason, now, int(is_silent))
            )
            await conn.commit()

    async def add_trigger(self, chat_id: int, trigger_type: str, action: str, duration: int | None = None, custom_text: str | None = None, rank_required: int = 0):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO triggers (chat_id, trigger_type, action, duration, custom_text, rank_required) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, trigger_type, action, duration, custom_text, rank_required)
            )
            await conn.commit()

    async def remove_trigger(self, chat_id: int, trigger_type: str):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM triggers WHERE chat_id = ? AND trigger_type = ?",
                (chat_id, trigger_type)
            )
            await conn.commit()

    async def get_triggers(self, chat_id: int) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT trigger_type, action, duration, custom_text, rank_required FROM triggers WHERE chat_id = ?",
                (chat_id,)
            )
            return await cursor.fetchall()

    async def add_moderator_log(self, chat_id: int, moderator_id: int, action: str, target_id: int, reason: str = ""):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT INTO moderator_logs (chat_id, moderator_id, action, target_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, moderator_id, action, target_id, reason, now)
            )
            await conn.commit()

    async def get_moderator_logs(self, chat_id: int, limit: int = 20) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM moderator_logs WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit)
            )
            return await cursor.fetchall()

    async def get_moderator_logs_by_moderator(self, chat_id: int, moderator_id: int, limit: int = 20) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM moderator_logs WHERE chat_id = ? AND moderator_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, moderator_id, limit)
            )
            return await cursor.fetchall()

    async def get_moderator_logs_for_user(self, chat_id: int, user_id: int, limit: int = 20) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM moderator_logs WHERE chat_id = ? AND target_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, user_id, limit)
            )
            return await cursor.fetchall()

    async def get_moderator_logs_by_days(self, chat_id: int, days: int = 30, limit: int | None = None) -> list:
        async with aiosqlite.connect(self.db_path) as conn:
            cutoff = int(time.time()) - days * 86400
            query = (
                "SELECT created_at, action, target_id, moderator_id, reason "
                "FROM moderator_logs WHERE chat_id = ? AND created_at >= ? ORDER BY created_at DESC"
            )
            params: list = [chat_id, cutoff]
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            cursor = await conn.execute(query, params)
            return await cursor.fetchall()

    async def delete_old_logs(self, days: int = 90) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM moderator_logs WHERE created_at < strftime('%s', 'now') - ? * 86400",
                (days,)
            )
            await conn.commit()
            return cursor.rowcount

    async def add_inheritance(self, chat_id: int, owner_id: int, heir_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            now = int(time.time())
            await conn.execute(
                "INSERT OR REPLACE INTO inheritances (chat_id, owner_id, heir_id, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, owner_id, heir_id, now)
            )
            await conn.commit()

    async def get_inheritance(self, chat_id: int, owner_id: int) -> tuple | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT heir_id, created_at FROM inheritances WHERE chat_id = ? AND owner_id = ?",
                (chat_id, owner_id)
            )
            return await cursor.fetchone()

    async def remove_inheritance(self, chat_id: int, owner_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM inheritances WHERE chat_id = ? AND owner_id = ?",
                (chat_id, owner_id)
            )
            await conn.commit()

    async def get_command_restriction(self, chat_id: int, command_type: str) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT min_rank FROM command_restrictions WHERE chat_id = ? AND command_type = ?",
                (chat_id, command_type)
            )
            row = await cursor.fetchone()
            return row[0] if row else DEFAULT_COMMAND_RANKS.get(command_type, 0)

    async def set_command_restriction(self, chat_id: int, command_type: str, min_rank: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO command_restrictions (chat_id, command_type, min_rank) VALUES (?, ?, ?)",
                (chat_id, command_type, min_rank)
            )
            await conn.commit()

    async def track_message(self, chat_id: int, user_id: int):
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO user_last_message (chat_id, user_id, last_msg_at, msg_count) VALUES (?, ?, ?, 1)
                   ON CONFLICT(chat_id, user_id) DO UPDATE SET last_msg_at = ?, msg_count = msg_count + 1""",
                (chat_id, user_id, now, now)
            )
            await conn.commit()

    async def get_last_message_time(self, chat_id: int, user_id: int) -> tuple | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT last_msg_at, msg_count FROM user_last_message WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            return await cursor.fetchone()

    async def get_users_by_msg_count(self, chat_id: int, min_count: int = 0, max_count: int | None = None, since: int | None = None) -> list:
        if since is None:
            since = 0
        async with aiosqlite.connect(self.db_path) as conn:
            if max_count is not None:
                cursor = await conn.execute(
                    "SELECT user_id, msg_count, last_msg_at FROM user_last_message WHERE chat_id = ? AND msg_count >= ? AND msg_count < ? AND last_msg_at >= ?",
                    (chat_id, min_count, max_count, since)
                )
            else:
                cursor = await conn.execute(
                    "SELECT user_id, msg_count, last_msg_at FROM user_last_message WHERE chat_id = ? AND msg_count >= ? AND last_msg_at >= ?",
                    (chat_id, min_count, since)
                )
            return await cursor.fetchall()

    async def get_lurkers(self, chat_id: int, cutoff: int, limit: int = None):
        async with aiosqlite.connect(self.db_path) as conn:
            params = [chat_id, cutoff]
            query = "SELECT user_id, last_msg_at FROM user_last_message WHERE chat_id = ? AND last_msg_at < ? ORDER BY last_msg_at ASC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor = await conn.execute(query, params)
            return await cursor.fetchall()

    async def add_exit_event(self, chat_id: int, user_id: int):
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO autokick_exits (chat_id, user_id, exit_count, last_exit_at) VALUES (?, ?, 1, ?)
                   ON CONFLICT(chat_id, user_id) DO UPDATE SET exit_count = exit_count + 1, last_exit_at = ?""",
                (chat_id, user_id, now, now)
            )
            await conn.commit()

    async def get_exit_count(self, chat_id: int, user_id: int) -> tuple | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT exit_count, last_exit_at FROM autokick_exits WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            return await cursor.fetchone()

    async def reset_exit_count(self, chat_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM autokick_exits WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            await conn.commit()

    async def add_chat_link(self, chat_id: int, link: str, link_type: str, created_by: int):
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO chat_links (chat_id, link, type, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                (chat_id, link, link_type, now, created_by)
            )
            await conn.commit()

    async def get_chat_links(self, chat_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT link, type, created_at, created_by FROM chat_links WHERE chat_id = ? ORDER BY created_at DESC",
                (chat_id,)
            )
            return await cursor.fetchall()

    async def clear_chat_links(self, chat_id: int):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM chat_links WHERE chat_id = ?", (chat_id,))
            await conn.commit()

    async def set_online_status(self, chat_id: int, user_id: int, is_online: bool):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE moderators SET is_online = ? WHERE chat_id = ? AND user_id = ?",
                (int(is_online), chat_id, user_id)
            )
            await conn.commit()

    async def get_stats(self, chat_id: int, period: str = "week") -> dict:
        now = int(time.time())
        if period == "day":
            cutoff = now - 86400
        elif period == "month":
            cutoff = now - 30 * 86400
        else:
            cutoff = now - 7 * 86400
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT action, COUNT(*) as cnt FROM logs WHERE chat_id = ? AND timestamp > ? GROUP BY action",
                (chat_id, cutoff),
            )
            rows = await cursor.fetchall()
            stats = {"bans": 0, "mutes": 0, "deletes": 0, "warns": 0}
            for action, cnt in rows:
                if action == "ban":
                    stats["bans"] = cnt
                elif action == "mute":
                    stats["mutes"] = cnt
                elif action == "delete":
                    stats["deletes"] = cnt
                elif action == "warn":
                    stats["warns"] = cnt
            return stats

    async def get_top_violators(self, chat_id: int, period: str = "week", limit: int = 10) -> list:
        now = int(time.time())
        if period == "day":
            cutoff = now - 86400
        elif period == "month":
            cutoff = now - 30 * 86400
        else:
            cutoff = now - 7 * 86400
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, COUNT(*) as cnt FROM logs WHERE chat_id = ? AND timestamp > ? AND action NOT IN ('mute', 'unmute', 'ban', 'unban', 'warn', 'unwarn', 'delete', 'edit', 'kick', 'amnesty') GROUP BY user_id ORDER BY cnt DESC LIMIT ?",
                (chat_id, cutoff, limit),
            )
            return await cursor.fetchall()


db = Database()
