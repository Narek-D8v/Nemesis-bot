import re
import time
import aiosqlite

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

from bot import bot, logger
from db import db
from utils import esc, format_duration
from utils.time_parser import parse_time
from utils.mentions import extract_user

router = Router()

RANK_NAMES = {
    0: "Участник",
    1: "Младший модератор",
    2: "Старший модератор",
    3: "Младший администратор",
    4: "Старший администратор",
    5: "Создатель",
}

CMD_PATTERNS = [
    r'^[+!]?(модер|админ)\b',
    r'^повысить\b',
    r'^понизить\b',
    r'^(снять|разжаловать)\b',
    r'^варн(\b|ы\b|\s)',
    r'^варнлист\b',
    r'^пред\b',
    r'^предупреждение\b',
    r'^мои\s+варны\b',
    r'^мои\s+преды\b',
    r'^мут(\b|ы\b|\s)',
    r'^-мут\b',
    r'^проверить\s+мут\b',
    r'^бан(\b|ы\b|\s)',
    r'^банлист\b',
    r'^разбан\b',
    r'^вернуть\b',
    r'^причина\b',
    r'^!амнистия',
    r'^кто\s+админ',
    r'^а\s+судьи\s+кто',
    r'^!staff',
    r'^/staff',
    r'^!админы',
    r'^кто\s+назначил\b',
    r'^модер\s+лог(\b|$|ы\b|\s)',
    r'^твой\s+модер\s+лог\b',
    r'^мой\s+модер\s+лог\b',
    r'^созвать\b',
    r'^позвать\b',
    r'^\+?триггер\b',
    r'^-триггер\b',
    r'^триггеры\b',
    r'^\+?завещание\b',
    r'^\+?наследство\b',
    r'^моё\s+завещание\b',
    r'^-завещание\b',
    r'^вступить\s+в\s+наследство\b',
    r'^!передать\s+создателя\b',
    r'^восстановить\s+создателя\b',
    r'^дк\b',
    r'^[+!-]модер\s+теги\b',
    r'^[+!]мой\s+онлайн\b',
    r'^снять\s+вышедших\b',
    r'^!снять\s+всех\b',
    r'^!снимаю\s+полномочия\b',
    r'^!ухожу\s+в\s+отставку\b',
    r'^варны\s+лимит\b',
    r'^варны\s+чс\b',
    r'^варны\s+период\b',
    r'^мут\s+период\b',
    r'^бан\s+период\b',
    r'^[+!]?(бан|модер|админ)\s+\d+\b',
]


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
    return ""


async def check_rank(chat_id: int, user_id: int, required_rank: int) -> bool:
    if required_rank == 0:
        return True
    rank = await db.get_user_rank(chat_id, user_id)
    return rank >= required_rank


async def get_min_rank(chat_id: int, cmd_type: str) -> int:
    return await db.get_command_restriction(chat_id, cmd_type)


def parse_cmd_rank(text: str):
    m = re.match(r'^[+!]?(модер|админ)\s*(\d*)', text, re.IGNORECASE)
    if m:
        rank_str = m.group(2)
        if rank_str:
            return int(rank_str)
        return 1
    return None


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: is_mod_cmd(msg.text))
async def admin_handler(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    rank = await db.get_user_rank(chat_id, user_id)
    rank_names = settings.get("moderator_rank_names", {})

    target_id = await extract_user(text, message)
    reason = get_reason(text)
    first_word = text.split()[0].lower() if text.split() else ""

    # ---- RANK MANAGEMENT ----
    if re.match(r'^[+!]?(модер|админ)', text, re.IGNORECASE):
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "promote")):
            await message.reply("❌ Недостаточно прав для повышения.")
            return
        if not target_id:
            await message.reply("❌ Укажите пользователя (ответом или @username).")
            return
        cmd_rank = parse_cmd_rank(text)
        if cmd_rank is None:
            bang_count = text.count('!')
            cmd_rank = min(bang_count, 5) if bang_count > 1 else 1
        if cmd_rank < 1 or cmd_rank > 5:
            await message.reply("❌ Ранг должен быть от 1 до 5.")
            return
        if cmd_rank >= rank:
            await message.reply("❌ Вы не можете назначить ранг выше или равный вашему.")
            return
        await db.set_user_rank(chat_id, target_id, cmd_rank, user_id)
        await db.add_moderator_log(chat_id, user_id, "promote", target_id, f"ранг {cmd_rank}")
        rname = rank_names.get(str(cmd_rank), RANK_NAMES.get(cmd_rank, f"Ранг {cmd_rank}"))
        resp = f"✅ {rname} назначен."
        if show_tags:
            resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
        await message.reply(resp)
        return

    if re.match(r'^повысить\b', text, re.IGNORECASE):
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "promote")):
            await message.reply("❌ Недостаточно прав.")
            return
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        cur = await db.get_user_rank(chat_id, target_id)
        if cur >= 5:
            await message.reply("❌ Пользователь уже имеет максимальный ранг.")
            return
        new_rank = cur + 1
        if new_rank >= rank:
            await message.reply("❌ Вы не можете повысить до ранга выше вашего.")
            return
        await db.set_user_rank(chat_id, target_id, new_rank, user_id)
        await db.add_moderator_log(chat_id, user_id, "promote", target_id, f"ранг {new_rank}")
        await message.reply(f"✅ Пользователь повышен до {RANK_NAMES.get(new_rank, new_rank)}.")
        return

    if re.match(r'^понизить\b', text, re.IGNORECASE):
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "demote")):
            await message.reply("❌ Недостаточно прав.")
            return
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        cur = await db.get_user_rank(chat_id, target_id)
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
        return

    if re.match(r'^(снять|разжаловать)\b', text, re.IGNORECASE):
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
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "demote")):
            await message.reply("❌ Недостаточно прав.")
            return
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        cur = await db.get_user_rank(chat_id, target_id)
        if cur >= rank:
            await message.reply("❌ Вы не можете снять модератора с равным или высшим рангом.")
            return
        await db.remove_moderator(chat_id, target_id)
        await db.add_moderator_log(chat_id, user_id, "demote", target_id, "снят")
        await message.reply(f"✅ Пользователь снят с должности.")
        return

    if text.lower().startswith("!снимаю полномочия") or text.lower().startswith("!ухожу в отставку"):
        if rank > 0:
            await db.remove_moderator(chat_id, user_id)
            await message.reply("✅ Вы сняли с себя полномочия.")
        else:
            await message.reply("❌ Вы не являетесь модератором.")
        return

    # ---- STAFF LIST ----
    if re.match(r'^(кто\s+админ|а\s+судьи\s+кто|!staff|/staff|!админы)', text, re.IGNORECASE):
        mods = await db.get_moderators(chat_id)
        if not mods:
            await message.reply("Модераторы не назначены.")
            return
        lines = ["👥 <b>Состав модерации:</b>\n"]
        for mid, rnk, ab, aa in mods:
            try:
                m = await bot.get_chat_member(chat_id, mid)
                name = esc(m.user.first_name or str(mid))
            except Exception:
                name = f"ID:{mid}"
            rname = rank_names.get(str(rnk), RANK_NAMES.get(rnk, f"Ранг {rnk}"))
            lines.append(f"• {name} — {rname}")
        await message.reply("\n".join(lines))
        return

    if re.match(r'^кто\s+назначил\b', text, re.IGNORECASE):
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
            try:
                m = await bot.get_chat_member(chat_id, row[0])
                aname = esc(m.user.first_name or str(row[0]))
            except Exception:
                aname = f"ID:{row[0]}"
            await message.reply(f"👤 Назначен: {aname}\n📅 {ts}")
        else:
            await message.reply("Пользователь не является модератором.")
        return

    # ---- MODERATOR LOGS ----
    if re.match(r'^модер\s+лог', text, re.IGNORECASE):
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
        return

    if re.match(r'^твой\s+модер\s+лог\b', text, re.IGNORECASE):
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        logs = await db.get_moderator_logs_for_user(chat_id, target_id, 15)
        if not logs:
            await message.reply("Нет записей.")
            return
        lines = [f"📋 <b>Лог для ID:{target_id}:</b>\n"]
        for row in logs[-10:]:
            ts = time.strftime("%d.%m %H:%M", time.localtime(row[6]))
            lines.append(f"• [{ts}] <b>{row[3]}</b>: {row[5]}")
        await message.reply("\n".join(lines))
        return

    if re.match(r'^мой\s+модер\s+лог\b', text, re.IGNORECASE):
        logs = await db.get_moderator_logs_for_user(chat_id, user_id, 15)
        if not logs:
            await message.reply("Нет записей.")
            return
        lines = ["📋 <b>Ваш лог:</b>\n"]
        for row in logs[-10:]:
            ts = time.strftime("%d.%m %H:%M", time.localtime(row[6]))
            lines.append(f"• [{ts}] <b>{row[3]}</b>: {row[5]}")
        await message.reply("\n".join(lines))
        return

    if re.match(r'^(созвать|позвать)\b', text, re.IGNORECASE):
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
        return

    # ---- WARN SYSTEM ----
    if re.match(r'^варн\b', text, re.IGNORECASE) or first_word in ('пред', 'предупреждение') or re.match(r'^!варн\b', text, re.IGNORECASE) or re.match(r'^!пред\b', text, re.IGNORECASE):
        if not target_id:
            await message.reply("❌ Укажите пользователя (ответом или @username).")
            return
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
            await message.reply("❌ Недостаточно прав для выдачи варнов.")
            return
        if not reason:
            reason = "Нарушение правил"
        expires_at = int(time.time()) + settings.get("warn_expire_days", 30) * 86400
        await db.add_warn(chat_id, target_id, user_id, reason, expires_at)
        await db.add_moderator_log(chat_id, user_id, "warn", target_id, reason)
        wcount = await db.count_active_warns(chat_id, target_id)
        wlimit = settings.get("warn_limit", 3)
        resp = f"⚠️ <b>Предупреждение</b>\nПользователь: ID:{target_id}\nПричина: {esc(reason)}\nПредупреждений: {wcount}/{wlimit}"
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
            await message.reply(f"⛔ Пользователь ID:{target_id} забанен (лимит предупреждений).")
            await db.clear_warns(chat_id, target_id)
        return

    if first_word in ('варны',) and len(text.split()) == 1 and not re.match(r'^варны\s+лимит', text, re.IGNORECASE) and not re.match(r'^варны\s+чс', text, re.IGNORECASE) and not re.match(r'^варны\s+период', text, re.IGNORECASE):
        warns = await db.get_active_warns(chat_id, target_id or user_id)
        uid = target_id or user_id
        if not warns:
            await message.reply(f"У пользователя ID:{uid} нет активных предупреждений.")
            return
        lines = [f"⚠️ <b>Предупреждения ID:{uid}</b>\n"]
        for i, (wid, wreason, wcreated, wexpires, wmod) in enumerate(warns, 1):
            ts = time.strftime("%d.%m.%Y", time.localtime(wcreated))
            lines.append(f"{i}. {esc(wreason)} ({ts})")
        await message.reply("\n".join(lines))
        return

    if re.match(r'^мои\s+варны\b', text, re.IGNORECASE) or re.match(r'^мои\s+преды\b', text, re.IGNORECASE):
        warns = await db.get_active_warns(chat_id, user_id)
        if not warns:
            await message.reply("У вас нет активных предупреждений.")
            return
        lines = [f"⚠️ <b>Ваши предупреждения:</b>\n"]
        for i, (wid, wreason, wcreated, wexpires, wmod) in enumerate(warns, 1):
            ts = time.strftime("%d.%m.%Y", time.localtime(wcreated))
            lines.append(f"{i}. {esc(wreason)} ({ts})")
        await message.reply("\n".join(lines))
        return

    if re.match(r'^варнлист\b', text, re.IGNORECASE):
        warns = await db.get_warnlist(chat_id, 30)
        if not warns:
            await message.reply("Нет предупреждений.")
            return
        lines = ["📋 <b>Список предупреждений:</b>\n"]
        for row in warns[:15]:
            ts = time.strftime("%d.%m %H:%M", time.localtime(row[5]))
            lines.append(f"• ID:{row[2]} — {esc(row[4])} ({ts})")
        await message.reply("\n".join(lines))
        return

    if first_word.startswith('-') and first_word[1:] in ('варн', 'пред'):
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "unwarn")):
            await message.reply("❌ Недостаточно прав.")
            return
        if await db.remove_last_warn(chat_id, target_id):
            await db.add_moderator_log(chat_id, user_id, "unwarn", target_id, "снято последнее")
            await message.reply(f"✅ Последнее предупреждение снято с ID:{target_id}.")
        else:
            await message.reply("❌ Нет активных предупреждений.")
        return

    if re.match(r'^снять\s+варн(ы|а)?\s+', text, re.IGNORECASE) and not text.lower().startswith("снять вышедших"):
        rest = text[10:].strip() if text.lower().startswith("снять варны") else text[11:].strip()
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
            await message.reply(f"✅ Все предупреждения сняты с ID:{target_id}.")
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

    # ---- WARN SETTINGS ----
    if re.match(r'^варны\s+лимит\s+(\d+)', text, re.IGNORECASE):
        if await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
            m = re.search(r'(\d+)', text)
            if m:
                settings["warn_limit"] = int(m.group(1))
                await db.save_settings(chat_id, settings)
                await message.reply(f"✅ Лимит предупреждений: {m.group(1)}")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    if re.match(r'^варны\s+чс\s+', text, re.IGNORECASE):
        if await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
            dur = parse_time(text.split()[-1])
            if dur is not None:
                settings["warn_ban_duration"] = dur // 1440
                await db.save_settings(chat_id, settings)
                await message.reply(f"✅ Срок бана по лимиту: {format_duration(dur)}")
            else:
                settings["warn_ban_duration"] = 0
                await db.save_settings(chat_id, settings)
                await message.reply("✅ Бан по лимиту: навсегда.")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    if re.match(r'^варны\s+период\s+', text, re.IGNORECASE):
        if await check_rank(chat_id, user_id, await get_min_rank(chat_id, "warn")):
            dur = parse_time(text.split()[-1])
            if dur is not None:
                settings["warn_expire_days"] = max(1, dur // 1440)
                await db.save_settings(chat_id, settings)
                await message.reply(f"✅ Срок хранения варна: {format_duration(dur)}")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    # ---- MUTE SYSTEM ----
    if first_word == 'мут' or re.match(r'^!мут\b', text, re.IGNORECASE):
        if not target_id:
            await message.reply("❌ Укажите пользователя (ответом или @username).")
            return
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "mute")):
            await message.reply("❌ Недостаточно прав для выдачи мута.")
            return
        parts = text.split()
        duration_min = None
        for i, p in enumerate(parts):
            pd = parse_time(p)
            if pd is not None:
                duration_min = pd
                break
        if duration_min is None:
            duration_min = settings.get("mute_default_days", 7) * 1440
        expires_at = int(time.time()) + duration_min * 60 if duration_min else None
        await db.add_mute(chat_id, target_id, user_id, reason or "Нарушение", expires_at)
        await db.add_moderator_log(chat_id, user_id, "mute", target_id, reason or "Нарушение")
        try:
            until_date = int(time.time()) + duration_min * 60 if duration_min else int(time.time()) + 365 * 86400
            await bot.restrict_chat_member(chat_id, target_id, can_send_messages=False, until_date=until_date)
        except Exception as e:
            logger.warning(f"Mute failed: {e}")
        dur_str = format_duration(duration_min) if duration_min else "навсегда"
        resp = f"🔇 <b>Мут</b>\nПользователь: ID:{target_id}\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}"
        if show_tags:
            resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
        await message.reply(resp)
        try:
            await bot.send_message(target_id, f"🔇 Вы получили мут в группе на {dur_str}.\nПричина: {esc(reason or 'Нарушение')}")
        except Exception:
            pass
        return

    if first_word == '-мут' or text.lower().startswith('снять мут') or text.lower().startswith('говори') or text.lower().startswith('размут') or text.lower().startswith('!unmute'):
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
        await message.reply(f"✅ Мут снят с ID:{target_id}.")
        try:
            await bot.send_message(target_id, "✅ С вас снят мут в группе.")
        except Exception:
            pass
        return

    if first_word == 'муты' or text.lower().startswith('!mutes'):
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
            lines.append(f"• ID:{mid} — {dur} ({esc(mreason[:30])})")
        await message.reply("\n".join(lines))
        return

    if text.lower().startswith('проверить мут') or text.lower().startswith('!mute_check'):
        if not target_id:
            await message.reply("❌ Укажите пользователя.")
            return
        m = await db.get_active_mute(chat_id, target_id)
        if m:
            mexp = m[3]
            if mexp:
                left = format_duration(max(0, mexp - int(time.time())) // 60)
                await message.reply(f"🔇 Пользователь ID:{target_id} в муте. Осталось: {left}")
            else:
                await message.reply(f"🔇 Пользователь ID:{target_id} в муте. Бессрочно.")
        else:
            await message.reply(f"✅ Пользователь ID:{target_id} не в муте.")
        return

    if text.lower().startswith('мут период'):
        if await check_rank(chat_id, user_id, await get_min_rank(chat_id, "mute")):
            dur = parse_time(text.split()[-1])
            if dur is not None:
                settings["mute_default_days"] = max(1, dur // 1440)
                await db.save_settings(chat_id, settings)
                await message.reply(f"✅ Срок мута по умолчанию: {format_duration(dur)}")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    # ---- BAN SYSTEM ----
    if first_word == 'бан' or re.match(r'^!бан\b', text, re.IGNORECASE) or first_word == 'чс':
        if not target_id:
            await message.reply("❌ Укажите пользователя (ответом или @username).")
            return
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "ban")):
            await message.reply("❌ Недостаточно прав для бана.")
            return
        parts = text.split()
        duration_min = None
        for i, p in enumerate(parts):
            pd = parse_time(p)
            if pd is not None:
                duration_min = pd
                break
        if duration_min is None:
            ban_days = settings.get("ban_default_days", 0)
            duration_min = ban_days * 1440 if ban_days > 0 else None
        expires_at = int(time.time()) + duration_min * 60 if duration_min else None
        await db.add_ban(chat_id, target_id, user_id, reason or "Нарушение", expires_at)
        await db.add_moderator_log(chat_id, user_id, "ban", target_id, reason or "Нарушение")
        try:
            until_date = int(time.time()) + duration_min * 60 if duration_min else None
            await bot.ban_chat_member(chat_id, target_id, until_date=until_date)
        except Exception as e:
            logger.warning(f"Ban failed: {e}")
        dur_str = format_duration(duration_min) if duration_min else "навсегда"
        resp = f"⛔ <b>Бан</b>\nПользователь: ID:{target_id}\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}"
        if show_tags:
            resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
        await message.reply(resp)
        try:
            await bot.send_message(target_id, f"⛔ Вы забанены в группе.\nСрок: {dur_str}\nПричина: {esc(reason or 'Нарушение')}")
        except Exception:
            pass
        return

    if text.lower().startswith('разбан') or text.lower().startswith('вернуть') or text.lower().startswith('!unban'):
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
        await message.reply(f"✅ Пользователь ID:{target_id} разбанен.")
        return

    if text.lower().startswith('!амнистия'):
        if not await check_rank(chat_id, user_id, await get_min_rank(chat_id, "amnesty")):
            await message.reply("❌ Недостаточно прав для амнистии.")
            return
        await db.amnesty(chat_id)
        await message.reply("✅ Амнистия проведена. Все баны сняты.")
        return

    if text.lower().startswith('причина') and not text.lower().startswith('причина бан'):
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
            try:
                m = await bot.get_chat_member(chat_id, ban[4])
                mname = esc(m.user.first_name or str(ban[4]))
            except Exception:
                mname = f"ID:{ban[4]}"
            dur = "навсегда"
            if ban[3]:
                left = max(0, ban[3] - int(time.time())) // 60
                dur = format_duration(left)
            await message.reply(f"⛔ <b>Причина бана ID:{target_id}</b>\nМодератор: {mname}\nПричина: {esc(ban[1])}\nСрок: {dur}\nДата: {ts}")
        else:
            await message.reply("Пользователь не забанен.")
        return

    if first_word == 'банлист' or text.lower().startswith('!banlist'):
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
            lines.append(f"• ID:{bid} — {dur} ({esc(breason[:30])})")
        await message.reply("\n".join(lines))
        return

    if text.lower().startswith('бан период'):
        if await check_rank(chat_id, user_id, await get_min_rank(chat_id, "ban")):
            dur = parse_time(text.split()[-1])
            if dur is not None:
                settings["ban_default_days"] = max(1, dur // 1440)
                await db.save_settings(chat_id, settings)
                await message.reply(f"✅ Срок бана по умолчанию: {format_duration(dur)}")
        else:
            await message.reply("❌ Недостаточно прав.")
        return

    # ---- TRIGGERS ----
    if text.lower().startswith('+триггер') or text.lower().startswith('!триггер'):
        if not await check_rank(chat_id, user_id, 3):
            await message.reply("❌ Недостаточно прав для управления триггерами.")
            return
        parts = text.split()
        if len(parts) < 3:
            await message.reply("❌ Формат: +Триггер <тип> <действие> [время]\nТипы: спам, ссылки, мат, инвайт, капс, флуд, custom")
            return
        ttype_map = {
            'спам': 'spam', 'ссылки': 'links', 'мат': 'mute', 'инвайт': 'invite',
            'упоминания': 'mention', 'капс': 'caps', 'флуд': 'flood', 'custom': 'custom',
        }
        ttype = ttype_map.get(parts[1].lower(), parts[1].lower())
        action = parts[2].lower()
        if action not in ('warn', 'mute', 'ban', 'kick', 'delete'):
            await message.reply("❌ Действие должно быть: warn, mute, ban, kick, delete")
            return
        duration = None
        if len(parts) > 3:
            dur_str = parts[3]
            if dur_str not in ('warn', 'mute', 'ban', 'kick', 'delete'):
                duration = parse_time(dur_str)
        await db.add_trigger(chat_id, ttype, action, duration)
        await message.reply(f"✅ Триггер добавлен: {ttype} → {action}")
        return

    if text.lower().startswith('-триггер'):
        if not await check_rank(chat_id, user_id, 3):
            await message.reply("❌ Недостаточно прав.")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply("❌ Укажите тип триггера.")
            return
        ttype_map = {
            'спам': 'spam', 'ссылки': 'links', 'мат': 'mute', 'инвайт': 'invite',
            'упоминания': 'mention', 'капс': 'caps', 'флуд': 'flood', 'custom': 'custom',
        }
        ttype = ttype_map.get(parts[1].lower(), parts[1].lower())
        await db.remove_trigger(chat_id, ttype)
        await message.reply(f"✅ Триггер {ttype} удалён.")
        return

    if first_word == 'триггеры' or text.lower().startswith('!triggers'):
        triggers = await db.get_triggers(chat_id)
        if not triggers:
            await message.reply("Нет активных триггеров.")
            return
        lines = ["⚡ <b>Триггеры:</b>\n"]
        for tt, act, dur, ct, rr in triggers:
            dur_str = f" {format_duration(dur)}" if dur else ""
            lines.append(f"• {tt} → {act}{dur_str}")
        await message.reply("\n".join(lines))
        return

    # ---- INHERITANCE ----
    if text.lower().startswith('+завещание') or text.lower().startswith('+наследство'):
        if not await check_rank(chat_id, user_id, 3):
            await message.reply("❌ Недостаточно прав.")
            return
        if not target_id:
            await message.reply("❌ Укажите наследника (ответом или @username).")
            return
        await db.add_inheritance(chat_id, user_id, target_id)
        await message.reply(f"✅ Завещание оставлено на пользователя ID:{target_id}.")
        return

    if text.lower().startswith('моё завещание') or text.lower().startswith('мое завещание'):
        inh = await db.get_inheritance(chat_id, user_id)
        if inh:
            try:
                m = await bot.get_chat_member(chat_id, inh[0])
                hname = esc(m.user.first_name or str(inh[0]))
            except Exception:
                hname = f"ID:{inh[0]}"
            ts = time.strftime("%d.%m.%Y", time.localtime(inh[1]))
            await message.reply(f"📜 Ваше завещание: {hname} (от {ts})")
        else:
            await message.reply("У вас нет завещания.")
        return

    if text.lower().startswith('-завещание'):
        await db.remove_inheritance(chat_id, user_id)
        await message.reply("✅ Завещание аннулировано.")
        return

    if text.lower().startswith('вступить в наследство'):
        if not target_id:
            await message.reply("❌ Укажите пользователя, от которого вступаете в наследство.")
            return
        inh = await db.get_inheritance(chat_id, target_id)
        if not inh or inh[0] != user_id:
            await message.reply("❌ Вы не указаны как наследник этого пользователя.")
            return
        trank = await db.get_user_rank(chat_id, target_id)
        await db.set_user_rank(chat_id, user_id, trank, user_id)
        await db.remove_inheritance(chat_id, target_id)
        await db.remove_moderator(chat_id, target_id)
        await db.add_moderator_log(chat_id, user_id, "promote", user_id, f"наследство ранг {trank}")
        await message.reply(f"✅ Вы вступили в наследство. Ваш ранг: {RANK_NAMES.get(trank, trank)}.")
        return

    if text.lower().startswith('!передать создателя'):
        if await check_rank(chat_id, user_id, 5):
            if not target_id:
                await message.reply("❌ Укажите пользователя.")
                return
            try:
                cm = await bot.get_chat_member(chat_id, user_id)
                if cm.status != ChatMemberStatus.CREATOR:
                    await message.reply("❌ Вы не являетесь создателем чата.")
                    return
            except Exception:
                await message.reply("❌ Не удалось проверить статус.")
                return
            await db.set_user_rank(chat_id, target_id, 5, user_id)
            await db.set_user_rank(chat_id, user_id, 4, user_id)
            await message.reply(f"✅ Права создателя переданы ID:{target_id}.")
        else:
            await message.reply("❌ Только создатель может передать права.")
        return

    if text.lower().startswith('восстановить создателя'):
        try:
            me = await bot.get_chat_member(chat_id, user_id)
            if me.status == ChatMemberStatus.CREATOR:
                await db.set_user_rank(chat_id, user_id, 5, user_id)
                await message.reply("✅ Вы восстановлены как создатель.")
                return
        except Exception:
            pass
        inh = await db.get_inheritance(chat_id, user_id)
        if inh and inh[0]:
            await message.reply("❌ Вы не создатель чата. Указанный в завещании наследник может вступить в наследство.")
        else:
            await message.reply("❌ Вы не создатель чата.")
        return

    # ---- ONLINE STATUS ----
    if text.lower().startswith('+мой онлайн') or text.lower().startswith('!мой онлайн') or text.lower().startswith('+online'):
        await db.set_online_status(chat_id, user_id, True)
        await message.reply("✅ Ваш онлайн включён.")
        return

    if text.lower().startswith('-мой онлайн') or text.lower().startswith('-online'):
        await db.set_online_status(chat_id, user_id, False)
        await message.reply("✅ Ваш онлайн выключен.")
        return

    # ---- MODERATOR TAGS ----
    if text.lower().startswith('+модер теги') or text.lower().startswith('!модер теги'):
        if await check_rank(chat_id, user_id, 5):
            settings["show_moderator_tags"] = True
            await db.save_settings(chat_id, settings)
            await message.reply("✅ Отображение тегов включено.")
        else:
            await message.reply("❌ Только создатель может изменить эту настройку.")
        return

    if text.lower().startswith('-модер теги'):
        if await check_rank(chat_id, user_id, 5):
            settings["show_moderator_tags"] = False
            await db.save_settings(chat_id, settings)
            await message.reply("✅ Отображение тегов выключено.")
        else:
            await message.reply("❌ Только создатель может изменить эту настройку.")
        return

    # ---- DK (COMMAND RESTRICTIONS) ----
    if text.lower().startswith('дк') or text.lower().startswith('!dk'):
        parts = text.split()
        if len(parts) < 3:
            await message.reply("❌ Формат: дк <команда> <ранг>\nПример: дк бан 3")
            return
        cmd_type_map = {
            'выдача варнов': 'warn', 'варн': 'warn', 'warn': 'warn',
            'снятие варнов': 'unwarn', 'разварн': 'unwarn',
            'выдача мута': 'mute', 'мут': 'mute', 'mute': 'mute',
            'снятие мута': 'unmute', 'размут': 'unmute',
            'выдача бана': 'ban', 'бан': 'ban', 'ban': 'ban',
            'снятие бана': 'unban', 'разбан': 'unban',
            'кик': 'kick', 'kick': 'kick',
            'амнистия': 'amnesty', 'банлист': 'banlist',
            'кто админ': 'admin_list', 'вызов админов': 'admin_call',
            'повышение': 'promote', 'понижение': 'demote',
        }
        cmd_key = ' '.join(parts[1:-1]).lower()
        cmd_type = cmd_type_map.get(cmd_key, parts[1].lower())
        try:
            min_rank = int(parts[-1])
        except ValueError:
            await message.reply("❌ Ранг должен быть числом (0-5).")
            return
        if min_rank < 0 or min_rank > 5:
            await message.reply("❌ Ранг от 0 до 5.")
            return
        await db.set_command_restriction(chat_id, cmd_type, min_rank)
        await message.reply(f"✅ Для команды {cmd_type} установлен минимальный ранг {min_rank}.")
        return

    # -- If nothing matched, do nothing (message falls through) --
    return
