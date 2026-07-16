import re
import time
import aiosqlite

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

from bot import bot, logger
from db import db
from utils import esc
from utils.mentions import extract_user
from utils.user_name import resolve_name
from .common import RANK_NAMES, check_rank, get_min_rank, parse_cmd_rank, call_plugin_hooks

router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^[+!]?(модер|админ)\b', msg.text.strip(), re.IGNORECASE) and not re.match(r'^[+!]?(модер|админ)\s+теги\b', msg.text.strip(), re.IGNORECASE))
async def promote_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    rank = await db.get_user_rank(chat_id, user_id) or 0
    target_id = await extract_user(text, message)

    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "promote")):
        await message.reply("❌ Недостаточно прав для повышения.")
        return
    if not target_id:
        await message.reply("❌ Укажите пользователя (ответом или @username).")
        return
    if target_id == user_id:
        await message.reply("❌ Вы не можете повысить самого себя.")
        return
    if target_id == (await bot.get_me()).id:
        await message.reply("❌ Вы не можете назначить ранг боту.")
        return

    cmd_rank = parse_cmd_rank(text)
    if cmd_rank is None:
        bang_count = text.count('!')
        cmd_rank = min(bang_count, 5) if bang_count > 1 else 1
    if cmd_rank < 1 or cmd_rank > 5:
        await message.reply("❌ Ранг должен быть от 1 до 5.")
        return
    if rank < 1:
        await message.reply("❌ Недостаточно прав для повышения.")
        return
    if rank != 5 and cmd_rank >= rank:
        await message.reply("❌ Вы не можете назначить ранг выше или равный вашему.")
        return

    await db.set_user_rank(chat_id, target_id, cmd_rank, user_id)
    await db.add_moderator_log(chat_id, user_id, "promote", target_id, f"ранг {cmd_rank}")
    rname = settings.get("moderator_rank_names", {}).get(str(cmd_rank), RANK_NAMES.get(cmd_rank, f"Ранг {cmd_rank}"))
    resp = f"✅ {rname} назначен."
    if show_tags:
        resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
    await message.reply(resp)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^повысить\b', msg.text.strip(), re.IGNORECASE))
async def promote_up_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)

    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "promote")):
        await message.reply("❌ Недостаточно прав.")
        return
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    cur = await db.get_user_rank(chat_id, target_id) or 0
    if cur >= 5:
        await message.reply("❌ Пользователь уже имеет максимальный ранг.")
        return
    rank = await db.get_user_rank(chat_id, user_id) or 0
    new_rank = cur + 1
    if rank != 5 and new_rank >= rank:
        await message.reply("❌ Вы не можете повысить до ранга выше вашего.")
        return
    await db.set_user_rank(chat_id, target_id, new_rank, user_id)
    await db.add_moderator_log(chat_id, user_id, "promote", target_id, f"ранг {new_rank}")
    await message.reply(f"✅ Пользователь повышен до {RANK_NAMES.get(new_rank, new_rank)}.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^понизить\b', msg.text.strip(), re.IGNORECASE))
async def demote_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)

    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "demote")):
        await message.reply("❌ Недостаточно прав.")
        return
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    cur = await db.get_user_rank(chat_id, target_id) or 0
    if cur <= 0:
        await message.reply("❌ Пользователь не имеет ранга.")
        return
    new_rank = cur - 1
    await db.set_user_rank(chat_id, target_id, new_rank, user_id)
    await db.add_moderator_log(chat_id, user_id, "demote", target_id, f"ранг {new_rank}")
    if new_rank == 0:
        await message.reply(f"✅ Пользователь понижен до участника.")
    else:
        await message.reply(f"✅ Пользователь понижен до {RANK_NAMES.get(new_rank, new_rank)}.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^(снять|разжаловать)\b', msg.text.strip(), re.IGNORECASE))
async def remove_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id

    if text.lower().startswith("снять вышедших"):
        if await check_rank(chat_id, user_id, 4):
            mods = await db.get_moderators(chat_id)
            removed = 0
            for mid, rnk, ab, aa in mods:
                try:
                    m = await bot.get_chat_member(chat_id, mid)
                    if m.status == ChatMemberStatus.LEFT:
                        await db.remove_moderator(chat_id, mid)
                        removed += 1
                except Exception:
                    await db.remove_moderator(chat_id, mid)
                    removed += 1
            await message.reply(f"✅ Снято модераторов: {removed}")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    if text.lower().startswith("!снять всех"):
        if await check_rank(chat_id, user_id, 5):
            mods = await db.get_moderators(chat_id)
            for mid, rnk, ab, aa in mods:
                await db.remove_moderator(chat_id, mid)
            await message.reply("✅ Все модераторы сняты.")
        else:
            await message.reply("❌ Только создатель может снять всех.")
        return

    target_id = await extract_user(text, message)
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "demote")):
        await message.reply("❌ Недостаточно прав.")
        return
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    rank = await db.get_user_rank(chat_id, user_id) or 0
    cur = await db.get_user_rank(chat_id, target_id) or 0
    if rank != 5 and cur >= rank:
        await message.reply("❌ Вы не можете снять модератора с равным или высшим рангом.")
        return
    await db.remove_moderator(chat_id, target_id)
    await db.add_moderator_log(chat_id, user_id, "demote", target_id, "снят")
    await message.reply(f"✅ Пользователь снят с должности.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith("!снимаю полномочия") or msg.text.strip().lower().startswith("!ухожу в отставку")))
async def resign_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    rank = await db.get_user_rank(chat_id, user_id) or 0
    if rank > 0:
        await db.remove_moderator(chat_id, user_id)
        await message.reply("✅ Вы сняли с себя полномочия.")
    else:
        await message.reply("❌ Вы не являетесь модератором.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^(кто\s+админ|а\s+судьи\s+кто|!staff|/staff|!админы)', msg.text.strip(), re.IGNORECASE))
async def staff_list_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    chat_id = message.chat.id
    settings = await db.get_settings(chat_id)
    rank_names = settings.get("moderator_rank_names", {})
    mods = await db.get_moderators(chat_id)
    if not mods:
        await message.reply("Модераторы не назначены.")
        return
    lines = ["👥 <b>Состав модерации:</b>\n"]
    for mid, rnk, ab, aa in mods:
        name = await resolve_name(chat_id, mid)
        rname = rank_names.get(str(rnk), RANK_NAMES.get(rnk, f"Ранг {rnk}"))
        lines.append(f"• {name} — {rname}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^кто\s+назначил\b', msg.text.strip(), re.IGNORECASE))
async def who_assigned_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT assigned_by, assigned_at FROM moderators WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        )
        row = await cursor.fetchone()
    if row:
        ts = time.strftime("%d.%m.%Y %H:%M", time.localtime(row[1]))
        aname = await resolve_name(chat_id, row[0])
        await message.reply(f"👤 Назначен: {aname}\n📅 {ts}")
    else:
        await message.reply("Пользователь не является модератором.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^модер\s+лог', msg.text.strip(), re.IGNORECASE))
async def mod_log_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    rest = text[9:].strip()
    if rest.startswith("от"):
        tid = await extract_user(rest, message)
        if tid:
            logs = await db.get_moderator_logs_by_moderator(chat_id, tid, 15)
        else:
            logs = await db.get_moderator_logs(chat_id, 15)
    else:
        logs = await db.get_moderator_logs(chat_id, 15)
    if not logs:
        await message.reply("Лог пуст.")
        return
    lines = ["📋 <b>Модер лог:</b>\n"]
    for row in logs[-10:]:
        ts = time.strftime("%d.%m %H:%M", time.localtime(row[6]))
        lines.append(f"• [{ts}] <b>{row[3]}</b> на {row[4]}: {row[5]}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^твой\s+модер\s+лог\b', msg.text.strip(), re.IGNORECASE))
async def user_log_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    logs = await db.get_moderator_logs_for_user(chat_id, target_id, 15)
    if not logs:
        await message.reply("Нет записей.")
        return
    tname = await resolve_name(chat_id, target_id)
    lines = [f"📋 <b>Лог для {tname}:</b>\n"]
    for row in logs[-10:]:
        ts = time.strftime("%d.%m %H:%M", time.localtime(row[6]))
        lines.append(f"• [{ts}] <b>{row[3]}</b>: {row[5]}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^мой\s+модер\s+лог\b', msg.text.strip(), re.IGNORECASE))
async def my_log_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    logs = await db.get_moderator_logs_for_user(chat_id, user_id, 15)
    if not logs:
        await message.reply("Нет записей.")
        return
    lines = ["📋 <b>Ваш лог:</b>\n"]
    for row in logs[-10:]:
        ts = time.strftime("%d.%m %H:%M", time.localtime(row[6]))
        lines.append(f"• [{ts}] <b>{row[3]}</b>: {row[5]}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and re.match(r'^(созвать|позвать)\b', msg.text.strip(), re.IGNORECASE))
async def call_mods_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "admin_call")):
        await message.reply("❌ Недостаточно прав.")
        return
    mods = await db.get_moderators(chat_id)
    mentions = []
    for mid, rnk, ab, aa in mods:
        try:
            m = await bot.get_chat_member(chat_id, mid)
            if m.user.username:
                mentions.append(f"@{m.user.username}")
            else:
                mentions.append(f"<a href='tg://user?id={mid}'>тут</a>")
        except Exception:
            pass
    if mentions:
        await message.reply("🚨 <b>Внимание модераторов!</b>\n" + ", ".join(mentions))
    else:
        await message.reply("Нет активных модераторов.")
