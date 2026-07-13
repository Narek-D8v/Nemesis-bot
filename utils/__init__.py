import re
import time
import html

URL_PATTERN = re.compile(
    r'(https?://|www\.|t\.me/|bit\.ly/|tinyurl\.com/|vk\.com/|telegram\.me/|'
    r'youtu\.be/|youtube\.com/|instagram\.com/|twitter\.com/|x\.com/|'
    r'fb\.com/|facebook\.com/|discord\.gg/|discord\.com/invite/)\S+',
    re.IGNORECASE
)
INVITE_PATTERN = re.compile(
    r'(?:t\.me/joinchat/|t\.me/|telegram\.me/|telegram\.dog/)\S+',
    re.IGNORECASE
)
MENTION_ALL_PATTERN = re.compile(r'@(?:everyone|all|channel)', re.IGNORECASE)
BOT_COMMAND_PATTERN = re.compile(r'/\w+')

HOMOGLYPH_MAP = {
    'а': 'a', 'е': 'e', 'о': 'o', 'с': 'c', 'р': 'p', 'х': 'x',
    'у': 'y', 'і': 'i', 'ї': 'i', 'в': 'b',
    'А': 'A', 'Е': 'E', 'О': 'O', 'С': 'C', 'Р': 'P', 'Х': 'X',
    'У': 'Y', 'І': 'I', 'Ї': 'I', 'В': 'B',
}

MAT_LIST = [
    'хуй', 'пизд', 'бляд', 'ебал', 'ебат', 'ебну', 'залуп', 'пизд',
    'мудак', 'гандон', 'шлюх', 'пидор', 'пидар', 'манда', 'лох',
    'чмо', 'гнид', 'сука', 'сучк', 'долбоеб', 'долбаеб', 'уеб',
    'распизд', 'разпизд', 'оху', 'офиг', 'наху', 'нахер',
    'поху', 'похер', 'хуев', 'хуёв', 'хуя', 'хую', 'хуем',
    'пизде', 'пизду', 'пизды', 'ебан', 'ебаш', 'ебет', 'ебут',
    'бля', 'блять', 'блядь', 'бляди', 'блядей',
    'далбаеб', 'шизик', 'дебил', 'идиот', 'кретин', 'даун',
    'ебень', 'выеб', 'заеб', 'наеб', 'объеб', 'отъеб', 'перееб',
    'подъеб', 'проеб', 'разъеб', 'съеб', 'уеб',
    'жопа', 'жоп', 'гандон', 'гнида', 'говно', 'говн',
    'мразь', 'тварь', 'урод', 'сволочь', 'падла',
    'ёб', 'пёзд', 'хули', 'уёбок', 'еблан', 'ёбака', 'хуета',
    'хуесос', 'хуеглот', 'заёб', 'проёб', 'наёбка', 'разёбанный',
]

def has_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def has_invite_link(text: str) -> bool:
    return bool(INVITE_PATTERN.search(text))

def has_mention_all(text: str) -> bool:
    return bool(MENTION_ALL_PATTERN.search(text))

def normalize_text(text: str) -> str:
    result = []
    for ch in text:
        ch = ch.replace('ё', 'е')
        result.append(HOMOGLYPH_MAP.get(ch, ch))
    return ''.join(result)

def has_mask(text: str) -> bool:
    if not text:
        return False
    has_cyrillic = bool(re.search(r'[а-яё]', text, re.IGNORECASE))
    if not has_cyrillic:
        return False
    text_no_yo = text.replace('ё', 'е').replace('Ё', 'Е')
    normalized = normalize_text(text_no_yo)
    if normalized == text_no_yo:
        return False
    diff_count = sum(1 for a, b in zip(text_no_yo, normalized) if a != b)
    return diff_count >= 2

def _strip_non_alpha(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text)

def contains_mat(text: str, mat_list: list = None) -> bool:
    if mat_list is None:
        mat_list = MAT_LIST
    text_lower = text.lower().replace('ё', 'е')
    text_normalized = normalize_text(text_lower)
    text_stripped = _strip_non_alpha(text_normalized)
    for word in mat_list:
        word_norm = normalize_text(word).replace('ё', 'е')
        if word_norm in text_stripped or word in text_lower:
            return True
    return False

def _word_to_pattern(word: str) -> str:
    rev: dict[str, list[str]] = {}
    for cyr, lat in HOMOGLYPH_MAP.items():
        rev.setdefault(lat, []).append(cyr)
    parts = []
    for c in word:
        homoglyphs = {c}
        if c in HOMOGLYPH_MAP:
            homoglyphs.add(HOMOGLYPH_MAP[c])
        if c in rev:
            homoglyphs.update(rev[c])
        if c == 'ё':
            homoglyphs.add('е')
        elif c == 'е':
            homoglyphs.add('ё')
        if len(homoglyphs) > 1:
            parts.append('[' + ''.join(re.escape(g) for g in homoglyphs) + ']')
        else:
            parts.append(re.escape(c))
    return r'[\W_]*'.join(parts)

def replace_mat(text: str, mat_list: list = None) -> str:
    if mat_list is None:
        mat_list = MAT_LIST
    result = text
    for word in sorted(mat_list, key=len, reverse=True):
        pattern = re.compile(_word_to_pattern(word), re.IGNORECASE)
        result = pattern.sub('*' * len(word), result)
    return result

def has_bot_command(text: str) -> bool:
    return bool(BOT_COMMAND_PATTERN.match(text.strip()))

def is_account_old_enough(join_date: int, min_days: int = 3) -> bool:
    if join_date is None:
        return True
    account_age_days = (time.time() - join_date) / 86400
    return account_age_days >= min_days

def esc(text: str) -> str:
    if not text:
        return ""
    return html.escape(str(text), quote=False)

def format_duration(minutes: int) -> str:
    if minutes is None:
        return "навсегда"
    if minutes < 60:
        return f"{minutes} мин"
    if minutes < 1440:
        h = minutes // 60
        m = minutes % 60
        return f"{h} ч {m} мин" if m else f"{h} ч"
    d = minutes // 1440
    if d >= 365:
        y = d // 365
        return f"{y} г"
    if d >= 30:
        mo = d // 30
        return f"{mo} мес"
    if d >= 7:
        w = d // 7
        return f"{w} н"
    return f"{d} д"

def apply_aggression_level(settings: dict, level: int):
    if level == 0:
        settings.setdefault("antispam", {})["threshold"] = 15
        settings.setdefault("filter_links", {})["action"] = "delete"
        settings["block_no_avatar"] = False
        settings["min_account_age_days"] = 1
        settings["captcha_for_suspicious"] = False
        settings["duplicate_block"] = False
        settings["mention_block"] = False
    elif level == 1:
        settings.setdefault("antispam", {})["threshold"] = 10
        settings.setdefault("filter_links", {})["action"] = "delete"
        settings["block_no_avatar"] = False
        settings["min_account_age_days"] = 3
        settings["captcha_for_suspicious"] = False
        settings["duplicate_block"] = True
        settings["mention_block"] = False
    elif level == 2:
        settings.setdefault("antispam", {})["threshold"] = 5
        settings.setdefault("filter_links", {})["action"] = "warn_mute"
        settings["block_no_avatar"] = True
        settings["min_account_age_days"] = 7
        settings["captcha_for_suspicious"] = True
        settings["duplicate_block"] = True
        settings["mention_block"] = True
    elif level == 3:
        settings.setdefault("antispam", {})["threshold"] = 3
        settings.setdefault("filter_links", {})["action"] = "ban"
        settings["block_no_avatar"] = True
        settings["min_account_age_days"] = 14
        settings["captcha_for_suspicious"] = True
        settings["duplicate_block"] = True
        settings["mention_block"] = True
        settings["forward_block"] = True

def is_night_mode(settings: dict) -> bool:
    night = settings.get("night_mode", {})
    if not night.get("enabled"):
        return False
    now = time.localtime()
    current_hour = now.tm_hour
    start = night.get("start", 23)
    end = night.get("end", 7)
    if start > end:
        return current_hour >= start or current_hour < end
    return start <= current_hour < end
