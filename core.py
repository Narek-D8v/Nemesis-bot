import asyncio
import time
from collections import defaultdict

from config import OWNER_ID, MAX_FILE_SIZE_MB, logger
from downloaders import set_max_file_size
from storage import Storage
from utils import fmt_time

set_max_file_size(MAX_FILE_SIZE_MB)

db = Storage()
_log = logger


class BotState:
    def __init__(self):
        self._load()

    def _load(self):
        self.auto_reply_enabled = db.get_state('auto_reply_enabled', 'False') == 'True'
        self.auto_reply_text = db.get_state('auto_reply_text',
            '💫 Я автоответчик, хозяин скоро ответит! Спасибо за терпение 😘')
        self.ghost_mode = db.get_state('ghost_mode', 'False') == 'True'
        raw_afk = db.get_state('afk_start_time')
        self.afk_start_time = float(raw_afk) if raw_afk else None
        self.afk_reason = db.get_state('afk_reason', '')
        self.bot_start_time = float(db.get_state('bot_start_time', str(time.time())))

        self.cover_enabled = db.get_state('cover_enabled', 'False') == 'True'
        self.silent_enabled = db.get_state('silent_enabled', 'False') == 'True'
        self.shadow_enabled = db.get_state('shadow_enabled', 'False') == 'True'
        self.shadow_delay = int(db.get_state('shadow_delay', '5'))
        self.lock_enabled = db.get_state('lock_enabled', 'False') == 'True'
        self.mute_enabled = db.get_state('mute_enabled', 'False') == 'True'
        self.typing_enabled = db.get_state('typing_enabled', 'False') == 'True'
        self.autodel_enabled = db.get_state('autodel_enabled', 'False') == 'True'
        self.autodel_delay = int(db.get_state('autodel_delay', '10'))
        self.reply_delay = int(db.get_state('reply_delay', '0'))
        self.readreceipt_enabled = db.get_state('readreceipt_enabled', 'False') == 'True'
        raw_sudo = db.get_state('sudo_users', '')
        self.sudo_users = set(int(x) for x in raw_sudo.split(',') if x.strip())

    def _save(self):
        db.set_state('auto_reply_enabled', str(self.auto_reply_enabled))
        db.set_state('auto_reply_text', self.auto_reply_text)
        db.set_state('ghost_mode', str(self.ghost_mode))
        db.set_state('afk_start_time', str(self.afk_start_time) if self.afk_start_time else '')
        db.set_state('afk_reason', self.afk_reason)
        db.set_state('bot_start_time', str(self.bot_start_time))
        db.set_state('cover_enabled', str(self.cover_enabled))
        db.set_state('silent_enabled', str(self.silent_enabled))
        db.set_state('shadow_enabled', str(self.shadow_enabled))
        db.set_state('shadow_delay', str(self.shadow_delay))
        db.set_state('lock_enabled', str(self.lock_enabled))
        db.set_state('mute_enabled', str(self.mute_enabled))
        db.set_state('typing_enabled', str(self.typing_enabled))
        db.set_state('autodel_enabled', str(self.autodel_enabled))
        db.set_state('autodel_delay', str(self.autodel_delay))
        db.set_state('reply_delay', str(self.reply_delay))
        db.set_state('readreceipt_enabled', str(self.readreceipt_enabled))
        db.set_state('sudo_users', ','.join(str(x) for x in self.sudo_users))

    def toggle_auto_reply(self, state=None):
        if state is None:
            self.auto_reply_enabled = not self.auto_reply_enabled
        else:
            self.auto_reply_enabled = state
        self._save()

    def set_auto_reply_text(self, text):
        self.auto_reply_text = text
        self._save()

    def toggle_ghost(self, state=None):
        if state is None:
            self.ghost_mode = not self.ghost_mode
        else:
            self.ghost_mode = state
        self._save()

    def set_afk(self, reason=''):
        self.afk_start_time = time.time()
        self.afk_reason = reason
        self._save()

    def clear_afk(self):
        duration = None
        if self.afk_start_time:
            duration = time.time() - self.afk_start_time
        self.afk_start_time = None
        self.afk_reason = ''
        self._save()
        return duration

    @property
    def uptime(self):
        return fmt_time(time.time() - self.bot_start_time)

    def set_cover(self, value):
        self.cover_enabled = value
        self._save()

    def set_silent(self, value):
        self.silent_enabled = value
        self._save()

    def set_shadow(self, value, delay=5):
        self.shadow_enabled = value
        self.shadow_delay = delay
        self._save()

    def set_lock(self, value):
        self.lock_enabled = value
        self._save()

    def set_mute(self, value):
        self.mute_enabled = value
        self._save()

    def set_typing(self, value):
        self.typing_enabled = value
        self._save()

    def set_autodel(self, value, delay=10):
        self.autodel_enabled = value
        self.autodel_delay = delay
        self._save()

    def set_reply_delay(self, seconds):
        self.reply_delay = max(0, seconds)
        self._save()

    def set_readreceipt(self, value):
        self.readreceipt_enabled = value
        self._save()

    def add_sudo(self, uid):
        self.sudo_users.add(uid)
        self._save()

    def remove_sudo(self, uid):
        self.sudo_users.discard(uid)
        self._save()

    def clear_sudo(self):
        self.sudo_users.clear()
        self._save()

    def reset_stealth(self):
        self.cover_enabled = False
        self.silent_enabled = False
        self.shadow_enabled = False
        self.shadow_delay = 5
        self.lock_enabled = False
        self.mute_enabled = False
        self.typing_enabled = False
        self.autodel_enabled = False
        self.autodel_delay = 10
        self.reply_delay = 0
        self.readreceipt_enabled = True
        self._save()


state = BotState()
command_cooldown = defaultdict(float)
reply_cooldown = {}
_download_lock = None
_watch_task = None
_protect_task = None


def owner_filter(event):
    if state.cover_enabled:
        text = event.raw_text or ''
        if not text.startswith('!cover') and not text.startswith('!status_reset'):
            return False
    return event.sender_id == OWNER_ID or event.sender_id in state.sudo_users


async def respond(event, text, **kwargs):
    from telethon.errors import MessageNotModifiedError
    if event.sender_id == OWNER_ID:
        try:
            return await event.edit(text, **kwargs)
        except MessageNotModifiedError:
            return None
    return await event.reply(text, **kwargs)


_translator = {}

def _get_translator(target='ru'):
    if target not in _translator:
        from deep_translator import GoogleTranslator
        _translator[target] = GoogleTranslator(source='auto', target=target)
    return _translator[target]
