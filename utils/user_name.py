import html
import time

from bot import bot

_name_cache: dict[tuple[int, int], tuple[str, float]] = {}
_CACHE_TTL = 300


async def get_user_display_name(chat_id: int, user_id: int) -> str | None:
    cached = _name_cache.get((chat_id, user_id))
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        name = member.user.first_name or member.user.username
        if name:
            escaped = html.escape(str(name), quote=False)
            _name_cache[(chat_id, user_id)] = (escaped, time.time())
            return escaped
    except Exception:
        pass
    return None


async def resolve_name(chat_id: int, user_id: int) -> str:
    name = await get_user_display_name(chat_id, user_id)
    return name or "пользователь"


async def resolve_name_link(chat_id: int, user_id: int) -> str:
    name = await resolve_name(chat_id, user_id)
    return f"<a href='tg://user?id={user_id}'>{name}</a>"
