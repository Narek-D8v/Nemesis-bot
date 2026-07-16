import re

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot import logger
from core.plugin_hooks import get_hooks

CMD_PATTERNS = [
    r'^[+!]?(модер|админ)\b',
    r'^[!]?повысить\b',
    r'^[!]?понизить\b',
    r'^[!]?(снять|разжаловать)\b',
    r'^[!]?варн(\b|ы\b|\s)',
    r'^[!]?варнлист\b',
    r'^[!]?пред\b',
    r'^[!]?предупреждение\b',
    r'^[!]?мои\s+варны\b',
    r'^[!]?мои\s+преды\b',
    r'^[!]?мут(\b|ы\b|\s)',
    r'^-мут\b',
    r'^[!]?проверить\s+мут\b',
    r'^[!]?бан(\b|ы\b|\s)',
    r'^[!]?банлист\b',
    r'^[!]?разбан\b',
    r'^[!]?вернуть\b',
    r'^[!]?причина\b',
    r'^!амнистия',
    r'^[!]?кто\s+админ',
    r'^[!]?а\s+судьи\s+кто',
    r'^!staff',
    r'^/staff',
    r'^!админы',
    r'^[!]?кто\s+назначил\b',
    r'^[!]?модер\s+лог(\b|$|ы\b|\s)',
    r'^[!]?твой\s+модер\s+лог\b',
    r'^[!]?мой\s+модер\s+лог\b',
    r'^[!]?созвать\b',
    r'^[!]?позвать\b',
    r'^\+?триггер\b',
    r'^-триггер\b',
    r'^[!]?триггеры\b',
    r'^\+?завещание\b',
    r'^\+?наследство\b',
    r'^[!]?моё\s+завещание\b',
    r'^-завещание\b',
    r'^[!]?вступить\s+в\s+наследство\b',
    r'^!передать\s+создателя\b',
    r'^[!]?восстановить\s+создателя\b',
    r'^[!]?дк\b',
    r'^[+!-]модер\s+теги\b',
    r'^[+!]мой\s+онлайн\b',
    r'^[!]?снять\s+вышедших\b',
    r'^!снять\s+всех\b',
    r'^!снимаю\s+полномочия\b',
    r'^!ухожу\s+в\s+отставку\b',
    r'^[!]?варны\s+лимит\b',
    r'^[!]?варны\s+чс\b',
    r'^[!]?варны\s+период\b',
    r'^[!]?мут\s+период\b',
    r'^[!]?бан\s+период\b',
    r'^[+!]?(бан|модер|админ)\s+\d+\b',
]

RANK_NAMES = {
    0: "Участник",
    1: "Младший модератор",
    2: "Старший модератор",
    3: "Младший администратор",
    4: "Старший администратор",
    5: "Создатель",
}


def is_mod_cmd(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    for p in CMD_PATTERNS:
        if re.match(p, t, re.IGNORECASE):
            return True
    return False


def get_reason(text: str) -> str:
    parts = text.split('\n', 1)
    if len(parts) > 1:
        return parts[1].strip()
    cmd_parts = text.split(maxsplit=2)
    if len(cmd_parts) > 2:
        return cmd_parts[2]
    return ""


async def check_rank(chat_id: int, user_id: int, required_rank: int) -> bool:
    if required_rank == 0:
        return True
    from db import db
    rank = await db.get_user_rank(chat_id, user_id)
    return (rank or 0) >= required_rank


async def get_min_rank(chat_id: int, cmd_type: str) -> int:
    from db import db
    return await db.get_command_restriction(chat_id, cmd_type)


def parse_cmd_rank(text: str):
    m = re.match(r'^[+!]?(модер|админ)\s*(\d*)', text, re.IGNORECASE)
    if m:
        rank_str = m.group(2)
        if rank_str:
            return int(rank_str)
        return 1
    return None


async def call_plugin_hooks(message: Message) -> bool:
    from db import db
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    settings = await db.get_settings(chat_id)
    for hook in get_hooks():
        try:
            if await hook(message, chat_id, user_id, text, settings):
                return True
        except Exception as e:
            logger.warning(f"Plugin hook error: {e}")
    return False
