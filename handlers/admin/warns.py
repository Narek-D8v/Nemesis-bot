import re
import time

from aiogram import Router, F
from aiogram.types import Message

from bot import bot, logger
from db import db
from utils import esc, format_duration
from utils.time_parser import parse_time
from utils.mentions import extract_user
from utils.user_name import resolve_name
from .common import check_rank, get_min_rank, get_reason, call_plugin_hooks

router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (re.match(r'^[!]?варн\b', msg.text.strip(), re.IGNORECASE) or msg.text.strip().split()[0].lower() if msg.text.strip().split() else False in ('пред', 'предупреждение')))
async def warn_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    first_word = text.split()[0].lower() if text.split() else ""

    if not (re.match(r'^варн\b', text, re.IGNORECASE) or re.match(r'^!варн\b', text, re.IGNORECASE) or re.match(r'^!пред\b', text, re.IGNORECASE) or first_word in ('пред', 'предупреждение')):
        return

    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя (ответом или @username).")
        return
    if target_id == user_id:
        await message.reply("❌ Вы не можете выдать предупреждение самому себе.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
        await message.reply("❌ Недостаточно прав для выдачи варнов.")
        return

    reason = get_reason(text) or "Нарушение правил"
    expires_at = int(time.time()) + settings.get("warn_expire_days", 30) * 86400
    await db.add_warn(chat_id, target_id, user_id, reason, expires_at)
    await db.add_moderator_log(chat_id, user_id, "warn", target_id, reason)
    wcount = await db.count_active_warns(chat_id, target_id)
    wlimit = settings.get("warn_limit", 3)
    tname = await resolve_name(chat_id, target_id)
    resp = f"⚠️ <b>Предупреждение</b>\nПользователь: {tname}\nПричина: {esc(reason)}\nПредупреждений: {wcount}/{wlimit}"
    if show_tags:
        resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
    await message.reply(resp)
    try:
        await bot.send_message(target_id, f"⚠️ Вы получили предупреждение в группе.\nПричина: {esc(reason)}")
    except Exception:
        pass
    if wcount >= wlimit:
        ban_dur = settings.get("warn_ban_duration", 0)
        ban_expires = int(time.time()) + ban_dur * 86400 if ban_dur > 0 else None
        await db.add_ban(chat_id, target_id, user_id, f"Достигнут лимит предупреждений ({wcount})", ban_expires)
        await bot.ban_chat_member(chat_id, target_id)
        await db.add_moderator_log(chat_id, user_id, "ban", target_id, "Лимит предупреждений")
        tname = await resolve_name(chat_id, target_id)
        await message.reply(f"⛔ Пользователь {tname} забанен (лимит предупреждений).")
        await db.clear_warns(chat_id, target_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^варнлист\b', msg.text.strip(), re.IGNORECASE))
async def warnlist_handler(message: Message):
    chat_id = message.chat.id
    warns = await db.get_warnlist(chat_id, 30)
    if not warns:
        await message.reply("Нет предупреждений.")
        return
    lines = ["📋 <b>Список предупреждений:</b>\n"]
    for row in warns[:15]:
        ts = time.strftime("%d.%m %H:%M", time.localtime(row[5]))
        wn = await resolve_name(chat_id, row[2])
        lines.append(f"• {wn} — {esc(row[4])} ({ts})")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (re.match(r'^мои\s+варны\b', msg.text.strip(), re.IGNORECASE) or re.match(r'^мои\s+преды\b', msg.text.strip(), re.IGNORECASE)))
async def my_warns_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    warns = await db.get_active_warns(chat_id, user_id)
    if not warns:
        await message.reply("У вас нет активных предупреждений.")
        return
    lines = [f"⚠️ <b>Ваши предупреждения:</b>\n"]
    for i, (wid, wreason, wcreated, wexpires, wmod) in enumerate(warns, 1):
        ts = time.strftime("%d.%m.%Y", time.localtime(wcreated))
        lines.append(f"{i}. {esc(wreason)} ({ts})")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^варны\b', msg.text.strip(), re.IGNORECASE) and not re.match(r'^варны\s+лимит\b', msg.text.strip(), re.IGNORECASE) and not re.match(r'^варны\s+чс\b', msg.text.strip(), re.IGNORECASE) and not re.match(r'^варны\s+период\b', msg.text.strip(), re.IGNORECASE))
async def warns_by_user_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    target_id = await extract_user(text, message) or message.from_user.id
    warns = await db.get_active_warns(chat_id, target_id)
    uname = await resolve_name(chat_id, target_id)
    if not warns:
        await message.reply(f"У пользователя {uname} нет активных предупреждений.")
        return
    lines = [f"⚠️ <b>Предупреждения {uname}</b>\n"]
    for i, (wid, wreason, wcreated, wexpires, wmod) in enumerate(warns, 1):
        ts = time.strftime("%d.%m.%Y", time.localtime(wcreated))
        lines.append(f"{i}. {esc(wreason)} ({ts})")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().split()[0].lower().startswith('-') if msg.text.strip().split() else False and msg.text.strip().split()[0][1:] in ('варн', 'пред'))
async def unwarn_handler(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    first_word = text.split()[0].lower() if text.split() else ""
    if not (first_word.startswith('-') and first_word[1:] in ('варн', 'пред')):
        return
    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unwarn")):
        await message.reply("❌ Недостаточно прав.")
        return
    if await db.remove_last_warn(chat_id, target_id):
        await db.add_moderator_log(chat_id, user_id, "unwarn", target_id, "снято последнее")
        tname = await resolve_name(chat_id, target_id)
        await message.reply(f"✅ Последнее предупреждение снято с {tname}.")
    else:
        await message.reply("❌ Нет активных предупреждений.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^снять\s+варн(ы|а)?\s+', msg.text.strip(), re.IGNORECASE) and not msg.text.strip().lower().startswith("снять вышедших"))
async def remove_warns_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    rest = text[10:].strip() if text.lower().startswith("снять варны") else text[11:].strip()
    target_id = await extract_user(text, message)

    m = re.match(r'все\s+', rest, re.IGNORECASE)
    if m:
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unwarn")):
            await message.reply("❌ Недостаточно прав.")
            return
        await db.clear_warns(chat_id, target_id)
        await db.add_moderator_log(chat_id, user_id, "unwarn", target_id, "все сняты")
        tname = await resolve_name(chat_id, target_id)
        await message.reply(f"✅ Все предупреждения сняты с {tname}.")
        return

    m = re.match(r'номер\s+(\d+)\s+', rest, re.IGNORECASE)
    if m:
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        num = int(m.group(1))
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unwarn")):
            await message.reply("❌ Недостаточно прав.")
            return
        if await db.remove_warn_by_number(chat_id, target_id, num):
            await db.add_moderator_log(chat_id, user_id, "unwarn", target_id, f"#{num}")
            await message.reply(f"✅ Предупреждение #{num} снято.")
        else:
            await message.reply("❌ Предупреждение не найдено.")
        return

    m = re.match(r'(\d+)\s+', rest)
    if m:
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        count = int(m.group(1))
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unwarn")):
            await message.reply("❌ Недостаточно прав.")
            return
        removed = await db.remove_warns_count(chat_id, target_id, count)
        await message.reply(f"✅ Снято предупреждений: {removed}")
        return


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^варны\s+лимит\s+(\d+)', msg.text.strip(), re.IGNORECASE))
async def warn_limit_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
        await message.reply("❌ Недостаточно прав.")
        return
    settings = await db.get_settings(chat_id)
    m = re.search(r'(\d+)', text)
    if m:
        settings["warn_limit"] = int(m.group(1))
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Лимит предупреждений: {m.group(1)}")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^варны\s+чс\s+', msg.text.strip(), re.IGNORECASE))
async def warn_ban_duration_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
        await message.reply("❌ Недостаточно прав.")
        return
    settings = await db.get_settings(chat_id)
    dur = parse_time(text.split()[-1])
    if dur is not None:
        settings["warn_ban_duration"] = dur // 1440
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Срок бана по лимиту: {format_duration(dur)}")
    else:
        settings["warn_ban_duration"] = 0
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Бан по лимиту: навсегда.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^варны\s+период\s+', msg.text.strip(), re.IGNORECASE))
async def warn_expire_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
        await message.reply("❌ Недостаточно прав.")
        return
    settings = await db.get_settings(chat_id)
    dur = parse_time(text.split()[-1])
    if dur is not None:
        settings["warn_expire_days"] = max(1, dur // 1440)
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Срок хранения варна: {format_duration(dur)}")
