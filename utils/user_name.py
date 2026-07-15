import html

from bot import bot


async def get_user_display_name(chat_id: int, user_id: int) -> str | None:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        name = member.user.first_name or member.user.username
        if name:
            return html.escape(str(name), quote=False)
    except Exception:
        pass
    return None


async def resolve_name(chat_id: int, user_id: int) -> str:
    name = await get_user_display_name(chat_id, user_id)
    return name or "пользователь"
