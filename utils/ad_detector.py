import re
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from utils import has_url

AD_KEYWORDS = [
    'заработок', 'пассивный доход', 'крипт', 'биткоин', 'майнинг',
    'инвестици', 'лотерея', 'розыгрыш', 'приз', 'бонус',
    'скидка', 'акция', 'распродажа', 'бесплатно',
    'подпишись', 'переходи', 'вступай', 'присоединяйся',
    'канал', 'чат', 'групп', 'бот',
    'оформи', 'карт', 'кредит', 'займ', 'деньги',
    'заработай', 'зарабатывай', 'ломбокрипт', 'скам',
    'реферал', 'партнёр', 'партнер',
    'телеграм', 'telegram', 't.me',
    'промокод', 'купон', 'оффер',
    'регистрируйся', 'депозит', 'вывод',
    'саппорт', 'поддержк', 'техподдержк',
]

INVITE_PATTERN_WIDE = re.compile(
    r'(?:t\.me/(?:joinchat/|\+|c/|s/|\+|publicsupergroup/|publicgroup/|channel/|supergroup/)|'
    r'telegram\.me/(?:joinchat/|\+|c/|s/|)|'
    r'telegram\.dog/(?:joinchat/|\+|c/|s/|)|'
    r'telegram\.org/|tg://|'
    r'telegra\.ph/|te.li/)\S+',
    re.IGNORECASE
)

SPAM_ENTITY_KEYWORDS = [
    r'joinchat', r't\.me/', r'telegram\.me/',
    r'@\w{4,}', r'https?://t\.me/\w{4,}',
]

_url_timestamps: Dict[str, List[Tuple[int, int, float]]] = defaultdict(list)
_cleanup_counter = 0


def has_invite_wide(text: str) -> bool:
    return bool(INVITE_PATTERN_WIDE.search(text))


def is_short_ad_message(text: str, urls: list | None = None) -> bool:
    if not text:
        return False
    text_lower = text.lower().strip()
    if not has_url(text) and not urls:
        return False
    word_count = len(text_lower.split())
    if word_count > 20:
        return False
    if word_count <= 3 and not has_invite_wide(text):
        for kw in AD_KEYWORDS[:8]:
            if kw in text_lower:
                return True
        return False
    for kw in AD_KEYWORDS:
        if kw in text_lower:
            return True
    if has_invite_wide(text) and word_count <= 8:
        return True
    return False


async def check_url_frequency(url: str, chat_id: int, user_id: int, threshold: int = 3, window: float = 60.0) -> bool:
    global _cleanup_counter
    now = time.time()
    _url_timestamps[url].append((chat_id, user_id, now))

    _cleanup_counter += 1
    if _cleanup_counter % 20 == 0:
        _cleanup_old_entries(window)

    unique_users: set[int] = set()
    same_chat_count = 0
    for cid, uid, ts in _url_timestamps[url]:
        if now - ts > window:
            continue
        unique_users.add(uid)
        if cid == chat_id:
            same_chat_count += 1

    if len(unique_users) >= threshold:
        return True
    if same_chat_count >= 3:
        return True
    return False


def _cleanup_old_entries(window: float = 60.0):
    now = time.time()
    expired_urls = []
    for url, entries in _url_timestamps.items():
        _url_timestamps[url] = [(cid, uid, ts) for cid, uid, ts in entries if now - ts <= window]
        if not _url_timestamps[url]:
            expired_urls.append(url)
    for url in expired_urls:
        del _url_timestamps[url]
