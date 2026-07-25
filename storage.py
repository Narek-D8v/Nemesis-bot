import sqlite3
import threading
import time
import logging

logger = logging.getLogger(__name__)


_VALID_TABLES = frozenset({
    'bot_state', 'saved_data', 'notes', 'todos', 'stats',
    'reply_settings', 'sessions', 'protected_chats',
})


def _validate_table(table):
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table name: {table}")
    return table


class Storage:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path='userbot.db'):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(db_path)
        return cls._instance

    def _init(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.executescript('''
                CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS saved_data (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS notes (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY, text TEXT, done INTEGER DEFAULT 0, created INTEGER);
                CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reply_settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS protected_chats (chat_id TEXT PRIMARY KEY, value TEXT);
            ''')
            self.conn.commit()

    # ── Generic helpers ──

    def _get(self, table, key, default=None):
        _validate_table(table)
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(f'SELECT value FROM {table} WHERE key = ?', (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def _set(self, table, key, value):
        _validate_table(table)
        with self.lock:
            self.conn.execute(f'INSERT OR REPLACE INTO {table} (key, value) VALUES (?, ?)', (key, value))
            self.conn.commit()

    def _delete(self, table, key):
        _validate_table(table)
        with self.lock:
            self.conn.execute(f'DELETE FROM {table} WHERE key = ?', (key,))
            self.conn.commit()

    def _get_all(self, table):
        _validate_table(table)
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(f'SELECT key, value FROM {table}')
            return {row[0]: row[1] for row in cur.fetchall()}

    def _delete_all(self, table):
        _validate_table(table)
        with self.lock:
            self.conn.execute(f'DELETE FROM {table}')
            self.conn.commit()

    def _keys(self, table):
        _validate_table(table)
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(f'SELECT key FROM {table}')
            return [row[0] for row in cur.fetchall()]

    def _search(self, table, query):
        _validate_table(table)
        q = f'%{query.lower()}%'
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(f'SELECT key, value FROM {table} WHERE LOWER(key) LIKE ? OR LOWER(value) LIKE ?', (q, q))
            return cur.fetchall()

    # ── Bot state ──

    def get_state(self, key, default=None):
        return self._get('bot_state', key, default)

    def set_state(self, key, value):
        self._set('bot_state', key, str(value))

    # ── Saved data ──

    def get_saved(self, key, default=None):
        return self._get('saved_data', key, default)

    def set_saved(self, key, value):
        self._set('saved_data', key, value)

    def del_saved(self, key):
        self._delete('saved_data', key)

    def all_saved(self):
        return self._get_all('saved_data')

    def search_saved(self, query):
        return self._search('saved_data', query)

    # ── Notes ──

    def get_note(self, key, default=None):
        return self._get('notes', key, default)

    def set_note(self, key, value):
        self._set('notes', key, value)

    def del_note(self, key):
        self._delete('notes', key)

    def all_notes(self):
        return self._get_all('notes')

    def search_notes(self, query):
        return self._search('notes', query)

    # ── Todos ──

    def add_todo(self, text):
        tid = int(time.time())
        with self.lock:
            self.conn.execute(
                'INSERT INTO todos (id, text, done, created) VALUES (?, ?, 0, ?)',
                (tid, text, tid)
            )
            self.conn.commit()
        return tid

    def get_todos(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute('SELECT id, text, done, created FROM todos ORDER BY created')
            return [dict(row) for row in cur.fetchall()]

    def update_todo(self, tid, done=True):
        with self.lock:
            self.conn.execute('UPDATE todos SET done = ? WHERE id = ?', (1 if done else 0, tid))
            self.conn.commit()

    def del_todo(self, tid):
        with self.lock:
            self.conn.execute('DELETE FROM todos WHERE id = ?', (tid,))
            self.conn.commit()

    # ── Stats ──

    def bump_stat(self, key, n=1):
        with self.lock:
            self.conn.execute(
                'INSERT INTO stats (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = value + ?',
                (key, n, n)
            )
            self.conn.commit()

    def all_stats(self):
        raw = self._get_all('stats')
        return {k: int(v) for k, v in raw.items()}

    def clear_all(self):
        with self.lock:
            for t in _VALID_TABLES:
                self.conn.execute(f'DELETE FROM {t}')
            self.conn.commit()

    # ── Reply settings (per-user + default) ──

    def get_reply_text(self, uid):
        return self._get('reply_settings', str(uid))

    def set_reply_text(self, uid, text):
        self._set('reply_settings', str(uid), text)

    def get_default_reply(self):
        return self._get('reply_settings', 'default')

    def set_default_reply(self, text):
        self._set('reply_settings', 'default', text)

    # ── Sessions (!watch) ──

    def all_sessions(self):
        raw = self._get_all('sessions')
        return {k: v for k, v in raw.items()}

    def save_session(self, hash_key, data_json):
        self._set('sessions', hash_key, data_json)

    def clear_sessions(self):
        self._delete_all('sessions')

    # ── Protected chats (!protect) ──

    def add_protected_chat(self, chat_id):
        self._set('protected_chats', str(chat_id), str(int(time.time())))

    def get_protected_chat_ids(self):
        raw = self._keys('protected_chats')
        return [int(x) for x in raw]

    def del_protected_chat(self, chat_id):
        self._delete('protected_chats', str(chat_id))

    def clear_protected_chats(self):
        self._delete_all('protected_chats')
