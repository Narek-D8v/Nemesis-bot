import re


def parse_time(text: str):
    if not text:
        return None
    text = text.strip().lower()
    if text in ('навсегда', '∞', 'бессрочно', '0', '-1'):
        return 0

    patterns = [
        (r'^(\d+)\s*м(ин)?$', 1),
        (r'^(\d+)\s*ч$', 60),
        (r'^(\d+)\s*д$', 1440),
        (r'^(\d+)\s*н$', 10080),
        (r'^(\d+)\s*мес(яц)?$', 43200),
        (r'^(\d+)\s*г(од)?$', 525600),
    ]

    for pattern, multiplier in patterns:
        m = re.match(pattern, text)
        if m:
            return int(m.group(1)) * multiplier

    try:
        return int(text)
    except ValueError:
        return None


def format_time(minutes: int) -> str:
    if minutes is None:
        return "навсегда"
    if minutes < 60:
        return f"{minutes} мин"
    if minutes < 1440:
        h = minutes // 60
        m = minutes % 60
        if m == 0:
            return f"{h} ч"
        return f"{h} ч {m} мин"
    if minutes < 10080:
        d = minutes // 1440
        return f"{d} д"
    if minutes < 43200:
        w = minutes // 10080
        return f"{w} н"
    if minutes < 525600:
        mo = minutes // 43200
        return f"{mo} мес"
    y = minutes // 525600
    return f"{y} г"
