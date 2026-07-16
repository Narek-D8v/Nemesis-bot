import re
import time

from aiogram import Router, F
from aiogram.types import Message

from bot import bot, logger
from db import db
from utils import esc, format_duration
from utils.time_parser import parse_time, PERMANENT
from utils.mentions import extract_user
from utils.user_name import resolve_name
from .common import check_rank, get_min_rank, get_reason, call_plugin_hooks

router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().split()[0].lower() if msg.text.strip().split() else '') in ('мут',) or re.match(r'^!мут\b', msg.text.strip(), re.IGNORECASE))
async def mute_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    first_word = text.split()[0].lower() if text.split() else ""
    if not (first_word == 'мут' or re.match(r'^!мут\b', text, re.IGNORECASE)):
        return
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    target_id = await extract_user(text, message)

    if not target_id:
        await message.reply("❌ Укажите пользователя (ответом или @username).")
        return
    if target_id == user_id:
        await message.reply("❌ Вы не можете замутить самого себя.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "mute")):
        await message.reply("❌ Недостаточно прав для выдачи мута.")
        return

    reason = get_reason(text)
    parts = text.split()
    duration_min = None
    for p in parts:
        pd = parse_time(p)
        if pd is not None:
            duration_min = pd
            break
    if duration_min is None:
        duration_min = settings.get("mute_default_days", 7) * 1440
    if duration_min == PERMANENT:
        expires_at = None
        until_date = int(time.time()) + 365 * 86400
        dur_str = "навсегда"
    else:
        expires_at = int(time.time()) + duration_min * 60
        until_date = expires_at
        dur_str = format_duration(duration_min)

    await db.add_mute(chat_id, target_id, user_id, reason or "Нарушение", expires_at)
    await db.add_moderator_log(chat_id, user_id, "mute", target_id, reason or "Нарушение")
    try:
        await bot.restrict_chat_member(chat_id, target_id, can_send_messages=False, until_date=until_date)
    except Exception as e:
        logger.warning(f"Mute failed: {e}")
    tname = await resolve_name(chat_id, target_id)
    resp = f"🔇 <b>Мут</b>\nПользователь: {tname}\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}"
    if show_tags:
        resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
    await message.reply(resp)
    try:
        await bot.send_message(target_id, f"🔇 Вы получили мут в группе на {dur_str}.\nПричина: {esc(reason or 'Нарушение')}")
    except Exception:
        pass


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and any(msg.text.strip().lower().startswith(x) for x in ('-мут', 'снять мут', 'говори', 'размут', '!unmute')))
async def unmute_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)

    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unmute")):
        await message.reply("❌ Недостаточно прав для снятия мута.")
        return
    await db.remove_mute(chat_id, target_id)
    try:
        await bot.restrict_chat_member(chat_id, target_id, can_send_messages=True)
    except Exception as e:
        logger.warning(f"Unmute failed: {e}")
    await db.add_moderator_log(chat_id, user_id, "unmute", target_id, "мут снят")
    tname = await resolve_name(chat_id, target_id)
    await message.reply(f"✅ Мут снят с {tname}.")
    try:
        await bot.send_message(target_id, "✅ С вас снят мут в группе.")
    except Exception:
        pass


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().split()[0].lower() if msg.text.strip().split() else '') in ('муты',) or msg.text.strip().lower().startswith('!mutes'))
async def mute_list_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "mute_list")):
        await message.reply("❌ Недостаточно прав.")
        return
    muted = await db.get_muted_users(chat_id)
    if not muted:
        await message.reply("Нет замученных пользователей.")
        return
    lines = ["🔇 <b>Замученные пользователи:</b>\n"]
    for mid, mreason, mcreated, mexpires in muted[:15]:
        if mexpires:
            left = max(0, mexpires - int(time.time()))
            dur = format_duration(left // 60)
        else:
            dur = "навсегда"
        mname = await resolve_name(chat_id, mid)
        lines.append(f"• {mname} — {dur} ({esc(mreason[:30])})")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('проверить мут') or msg.text.strip().lower().startswith('!mute_check')))
async def mute_check_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    m = await db.get_active_mute(chat_id, target_id)
    tname = await resolve_name(chat_id, target_id)
    if m:
        mexp = m[3]
        if mexp:
            left = format_duration(max(0, mexp - int(time.time())) // 60)
            await message.reply(f"🔇 Пользователь {tname} в муте. Осталось: {left}")
        else:
            await message.reply(f"🔇 Пользователь {tname} в муте. Бессрочно.")
    else:
        await message.reply(f"✅ Пользователь {tname} не в муте.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^мут\s+период\b', msg.text.strip(), re.IGNORECASE))
async def mute_period_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "mute")):
        await message.reply("❌ Недостаточно прав.")
        return
    settings = await db.get_settings(chat_id)
    dur = parse_time(text.split()[-1])
    if dur is not None:
        settings["mute_default_days"] = max(1, dur // 1440)
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Срок мута по умолчанию: {format_duration(dur)}")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and ((msg.text.strip().split()[0].lower() if msg.text.strip().split() else '') in ('бан', 'чс') or re.match(r'^!бан\b', msg.text.strip(), re.IGNORECASE)))
async def ban_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    first_word = text.split()[0].lower() if text.split() else ""
    if not (first_word == 'бан' or first_word == 'чс' or re.match(r'^!бан\b', text, re.IGNORECASE)):
        return
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    target_id = await extract_user(text, message)

    if not target_id:
        await message.reply("❌ Укажите пользователя (ответом или @username).")
        return
    if target_id == user_id:
        await message.reply("❌ Вы не можете забанить самого себя.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "ban")):
        await message.reply("❌ Недостаточно прав для бана.")
        return

    reason = get_reason(text)
    parts = text.split()
    duration_min = None
    for p in parts:
        pd = parse_time(p)
        if pd is not None:
            duration_min = pd
            break
    if duration_min is None:
        ban_days = settings.get("ban_default_days", 0)
        duration_min = ban_days * 1440 if ban_days > 0 else None
    if duration_min == PERMANENT or duration_min is None:
        expires_at = None
        until_date = None
        dur_str = "навсегда"
    else:
        expires_at = int(time.time()) + duration_min * 60
        until_date = expires_at
        dur_str = format_duration(duration_min)

    await db.add_ban(chat_id, target_id, user_id, reason or "Нарушение", expires_at)
    await db.add_moderator_log(chat_id, user_id, "ban", target_id, reason or "Нарушение")
    try:
        await bot.ban_chat_member(chat_id, target_id, until_date=until_date)
    except Exception as e:
        logger.warning(f"Ban failed: {e}")
    tname = await resolve_name(chat_id, target_id)
    resp = f"⛔ <b>Бан</b>\nПользователь: {tname}\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}"
    if show_tags:
        resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
    await message.reply(resp)
    try:
        await bot.send_message(target_id, f"⛔ Вы забанены в группе.\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}")
    except Exception:
        pass


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('разбан') or msg.text.strip().lower().startswith('вернуть') or msg.text.strip().lower().startswith('!unban')))
async def unban_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)

    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unban")):
        await message.reply("❌ Недостаточно прав для разбана.")
        return
    await db.remove_ban(chat_id, target_id)
    try:
        await bot.unban_chat_member(chat_id, target_id)
    except Exception as e:
        logger.warning(f"Unban failed: {e}")
    await db.add_moderator_log(chat_id, user_id, "unban", target_id, "разбанен")
    tname = await resolve_name(chat_id, target_id)
    await message.reply(f"✅ Пользователь {tname} разбанен.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('!амнистия'))
async def amnesty_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "amnesty")):
        await message.reply("❌ Недостаточно прав для амнистии.")
        return
    await db.amnesty(chat_id)
    await message.reply("✅ Амнистия проведена. Все баны сняты.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('причина') and not msg.text.strip().lower().startswith('причина бан'))
async def ban_reason_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    target_id = await extract_user(text, message)
    if not target_id:
        tparts = text.split()
        if len(tparts) > 1:
            rest_text = ' '.join(tparts[1:])
            target_id = await extract_user(rest_text, message)
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
    ban = await db.get_active_ban(chat_id, target_id)
    if ban:
        ts = time.strftime("%d.%m.%Y %H:%M", time.localtime(ban[2]))
        mname = await resolve_name(chat_id, ban[4])
        dur = "навсегда"
        if ban[3]:
            left = max(0, ban[3] - int(time.time())) // 60
            dur = format_duration(left)
        tname = await resolve_name(chat_id, target_id)
        await message.reply(f"⛔ <b>Причина бана {tname}</b>\nМодератор: {mname}\nПричина: {esc(ban[1])}\nСрок: {dur}\nДата: {ts}")
    else:
        await message.reply("Пользователь не забанен.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and ((msg.text.strip().split()[0].lower() if msg.text.strip().split() else '') == 'банлист' or msg.text.strip().lower().startswith('!banlist')))
async def banlist_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "banlist")):
        await message.reply("❌ Недостаточно прав.")
        return
    bans = await db.get_banned_users(chat_id)
    if not bans:
        await message.reply("Нет забаненных пользователей.")
        return
    lines = ["⛔ <b>Банлист:</b>\n"]
    for bid, breason, bcreated, bexpires, bmod in bans[:15]:
        if bexpires:
            left = max(0, bexpires - int(time.time()))
            dur = format_duration(left // 60)
        else:
            dur = "навсегда"
        bname = await resolve_name(chat_id, bid)
        lines.append(f"• {bname} — {dur} ({esc(breason[:30])})")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^бан\s+период\b', msg.text.strip(), re.IGNORECASE))
async def ban_period_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "ban")):
        await message.reply("❌ Недостаточно прав.")
        return
    settings = await db.get_settings(chat_id)
    dur = parse_time(text.split()[-1])
    if dur is not None:
        settings["ban_default_days"] = max(1, dur // 1440)
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Срок бана по умолчанию: {format_duration(dur)}")
