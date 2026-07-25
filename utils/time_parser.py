import re


PERMANENT = -1


def parse_time(text: str):
    if not text:
        return None
    text = text.strip().lower()
    if text in ('навсегда', '∞', 'бессрочно', '0', '-1'):
        return PERMANENT

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



