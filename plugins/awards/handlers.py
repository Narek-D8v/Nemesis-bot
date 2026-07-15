import re
import time

import aiosqlite
from aiogram.types import Message

from bot import bot, logger
from db import db
from handlers.admin import is_mod_cmd
from utils import esc
from utils.mentions import extract_user
from utils.user_name import resolve_name

AWARD_CMD = re.compile(r'^наградить\b', re.IGNORECASE)
ADD_GIVER_CMD = re.compile(r'^\+награждающий\b', re.IGNORECASE)
REM_GIVER_CMD = re.compile(r'^-награждающий\b', re.IGNORECASE)
LIST_GIVERS_CMD = re.compile(r'^кто\s+награждающий\b', re.IGNORECASE)
REM_ALL_AWARDS_CMD = re.compile(r'^снять\s+все\s+награды\b', re.IGNORECASE)
REM_AWARDS_FROM_CMD = re.compile(r'^снять\s+награды\s+от\b', re.IGNORECASE)
REM_AWARD_CMD = re.compile(r'^(снять\s+награду\s+|\-награда\s+)(\d+)\s+', re.IGNORECASE)
SHOW_AWARDS_CMD = re.compile(r'^награды\s+', re.IGNORECASE)
MY_AWARDS_CMD = re.compile(r'^мои\s+награды\b', re.IGNORECASE)

RESTRICT_AWARD_CMD = re.compile(r'^дк\s+наградить\s+(\d+)', re.IGNORECASE)
RESTRICT_CALL_CMD = re.compile(r'^дк\s+вызов\s+наград\s+(\d+)', re.IGNORECASE)
RESTRICT_REMOVE_CMD = re.compile(r'^дк\s+снятие\s+наград\s+(\d+)', re.IGNORECASE)
RESTRICT_MANAGE_CMD = re.compile(r'^дк\s+управление\s+наградами\s+(\d+)', re.IGNORECASE)

MEDAL_EMOJIS = {1: "🥉", 2: "🥈", 3: "🥇", 4: "🏅", 5: "🎖️", 6: "🏆", 7: "💎", 8: "👑"}
MEDAL_NAMES = {1: "Бронза", 2: "Серебро", 3: "Золото", 4: "Медаль", 5: "Орден", 6: "Кубок", 7: "Алмаз", 8: "Корона"}

RANK_MAX_DEGREE = {0: 0, 1: 1, 2: 2, 3: 4, 4: 6, 5: 8}


async def _get_restriction(chat_id: int, cmd_type: str) -> int:
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT min_rank FROM awards_restrictions WHERE chat_id = ? AND command_type = ?",
            (chat_id, cmd_type)
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def handle_award_commands(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    stripped = text.strip()

    if is_mod_cmd(stripped):
        if not REM_ALL_AWARDS_CMD.match(stripped) and not REM_AWARDS_FROM_CMD.match(stripped) and not REM_AWARD_CMD.match(stripped):
            return False

    if MY_AWARDS_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, degree, description, giver_id, created_at, expires_at FROM awards_medals WHERE chat_id = ? AND user_id = ? ORDER BY degree DESC, created_at DESC",
                (chat_id, user_id)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("У вас пока нет наград.")
            return True
        lines = [f"🎖️ <b>Награды {esc(message.from_user.first_name or '')}:</b>\n"]
        for aid, degree, desc, giver_id, created_at, expires_at in rows:
            emoji = MEDAL_EMOJIS.get(degree, "🎖️")
            name = MEDAL_NAMES.get(degree, f"Степень {degree}")
            duration = ""
            if expires_at:
                left = max(0, expires_at - int(time.time()))
                if left > 0:
                    duration = f" (ещё {left // 86400} д)"
            lines.append(f"{emoji} <b>{name}</b> #{aid}{duration}\n{esc(desc)}")
        await message.reply("\n\n".join(lines))
        return True

    m = SHOW_AWARDS_CMD.match(stripped)
    if m:
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, degree, description, giver_id, created_at, expires_at FROM awards_medals WHERE chat_id = ? AND user_id = ? ORDER BY degree DESC, created_at DESC",
                (chat_id, target)
            )
            rows = await cursor.fetchall()
        tname = await resolve_name(chat_id, target)
        if not rows:
            await message.reply(f"У {tname} пока нет наград.")
            return True
        lines = [f"🎖️ <b>Награды {tname}:</b>\n"]
        for aid, degree, desc, giver_id, created_at, expires_at in rows:
            emoji = MEDAL_EMOJIS.get(degree, "🎖️")
            name = MEDAL_NAMES.get(degree, f"Степень {degree}")
            lines.append(f"{emoji} <b>{name}</b> #{aid} — {esc(desc)}")
        await message.reply("\n\n".join(lines))
        return True

    if REM_ALL_AWARDS_CMD.match(stripped):
        min_rank = await _get_restriction(chat_id, "снятие_наград")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав для снятия наград.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM awards_medals WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Все награды пользователя {tname} сняты.")
        return True

    if REM_AWARDS_FROM_CMD.match(stripped):
        min_rank = await _get_restriction(chat_id, "снятие_наград")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав для снятия наград.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM awards_medals WHERE chat_id = ? AND giver_id = ?",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Все награды, выданные пользователем {tname}, сняты.")
        return True

    m = REM_AWARD_CMD.match(stripped)
    if m:
        min_rank = await _get_restriction(chat_id, "снятие_наград")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав для снятия наград.")
            return True
        award_num = int(m.group(2))
        rest = stripped[m.end():].strip()
        target = await extract_user(rest, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM awards_medals WHERE chat_id = ? AND user_id = ? ORDER BY degree DESC, created_at DESC",
                (chat_id, target)
            )
            rows = await cursor.fetchall()
            if award_num <= len(rows):
                award_id = rows[award_num - 1][0]
                await conn.execute("DELETE FROM awards_medals WHERE id = ?", (award_id,))
                await conn.commit()
                tname = await resolve_name(chat_id, target)
                await message.reply(f"✅ Награда #{award_num} у {tname} снята.")
            else:
                await message.reply("❌ Награда с таким номером не найдена.")
        return True

    if LIST_GIVERS_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, max_degree FROM awards_givers WHERE chat_id = ? LIMIT 10",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("Нет назначенных награждающих.")
            return True
        lines = ["👑 <b>Награждающие:</b>\n"]
        for uid, md in rows:
            name = await resolve_name(chat_id, uid)
            lines.append(f"• {name} — макс. степень {md}")
        await message.reply("\n".join(lines))
        return True

    if REM_GIVER_CMD.match(stripped):
        min_rank = await _get_restriction(chat_id, "управление_наградами")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank or user_rank < 4:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM awards_givers WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Пользователь {tname} удалён из награждающих.")
        return True

    if ADD_GIVER_CMD.match(stripped):
        min_rank = await _get_restriction(chat_id, "управление_наградами")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank or user_rank < 4:
            await message.reply("❌ Недостаточно прав.")
            return True
        parts = stripped.split()
        max_degree = 1
        if len(parts) >= 2:
            try:
                max_degree = int(parts[1])
            except ValueError:
                pass
        rest = " ".join(parts[2:]) if len(parts) > 2 else ""
        target = await extract_user(rest, message)
        if not target:
            if message.reply_to_message and message.reply_to_message.from_user:
                target = message.reply_to_message.from_user.id
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        max_degree = max(1, min(max_degree, 8))
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO awards_givers (chat_id, user_id, max_degree) VALUES (?, ?, ?)",
                (chat_id, target, max_degree)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Пользователь {tname} назначен награждающим (макс. степень {max_degree}).")
        return True

    for restrict_pattern, cmd_type in [
        (RESTRICT_AWARD_CMD, "наградить"),
        (RESTRICT_CALL_CMD, "вызов_наград"),
        (RESTRICT_REMOVE_CMD, "снятие_наград"),
        (RESTRICT_MANAGE_CMD, "управление_наградами"),
    ]:
        m = restrict_pattern.match(stripped)
        if m:
            user_rank = await db.get_user_rank(chat_id, user_id) or 0
            if user_rank < 4:
                await message.reply("❌ Недостаточно прав. Требуется ранг 4+.")
                return True
            min_rank = int(m.group(1))
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO awards_restrictions (chat_id, command_type, min_rank) VALUES (?, ?, ?)",
                    (chat_id, cmd_type, min_rank)
                )
                await conn.commit()
            await message.reply(f"✅ {cmd_type}: минимальный ранг {min_rank}.")
            return True

    m = AWARD_CMD.match(stripped)
    if m:
        min_rank = await _get_restriction(chat_id, "наградить")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав для выдачи наград.")
            return True

        parts = stripped.split(None, 2)
        degree = 1
        target = None
        description = ""

        if len(parts) >= 2:
            first_arg = parts[1]
            m_deg = re.match(r'^(\d+)$', first_arg)
            if m_deg:
                degree = int(m_deg.group(1))
                degree = max(1, min(degree, 8))
                max_allowed = RANK_MAX_DEGREE.get(user_rank, 0)
                if degree > max_allowed:
                    await message.reply(f"❌ Ваш ранг позволяет выдавать максимум {max_allowed} степень.")
                    return True

                async with aiosqlite.connect(db.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT max_degree FROM awards_givers WHERE chat_id = ? AND user_id = ?",
                        (chat_id, user_id)
                    )
                    giver_row = await cursor.fetchone()
                    if giver_row and degree > giver_row[0]:
                        await message.reply(f"❌ Вам разрешено выдавать максимум {giver_row[0]} степень.")
                        return True

                rest_m = re.match(r'^\d+\s+(.*?)$', stripped[len("наградить "):], re.DOTALL)
                if rest_m:
                    rest_text = rest_m.group(1).strip()
                    newline_idx = rest_text.find('\n')
                    if newline_idx >= 0:
                        target_str = rest_text[:newline_idx].strip()
                        description = rest_text[newline_idx:].strip()
                    else:
                        target_str = rest_text
                        description = ""
                    target = await extract_user(target_str, message)
                    if not target:
                        target = await extract_user("@" + target_str, message)
            else:
                target = await extract_user(first_arg, message)
                if not target:
                    target = await extract_user("@" + first_arg, message)
                newline_idx = stripped.find('\n')
                if newline_idx >= 0:
                    description = stripped[newline_idx:].strip()

        if not target:
            if message.reply_to_message and message.reply_to_message.from_user:
                target = message.reply_to_message.from_user.id
        if not target:
            await message.reply("❌ Укажите пользователя (ответом или @username).")
            return True

        if not description:
            await message.reply("❌ Укажите описание награды после переноса строки.")
            return True

        expires_at = None
        dur_match = re.search(r'удалить\s+через\s+(\S+)', description, re.IGNORECASE)
        if dur_match:
            from utils.time_parser import parse_time
            dur = parse_time(dur_match.group(1))
            if dur:
                expires_at = int(time.time()) + dur * 60
                description = description.replace(dur_match.group(0), "").strip()

        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO awards_medals (chat_id, user_id, giver_id, degree, description, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, target, user_id, degree, description, int(time.time()), expires_at)
            )
            await conn.commit()

        emoji = MEDAL_EMOJIS.get(degree, "🎖️")
        name = MEDAL_NAMES.get(degree, f"Степень {degree}")
        dur_text = ""
        if expires_at:
            dur_text = f" (до {time.strftime('%d.%m.%Y', time.localtime(expires_at))})"
        tname = await resolve_name(chat_id, target)
        await message.reply(f"{emoji} <b>{name}</b> выдана {tname}!{dur_text}\n{esc(description)}")

        try:
            await bot.send_message(
                target,
                f"🎖️ Вам выдана награда <b>{name}</b> в чате {esc(message.chat.title or '')}!\n\n{esc(description)}"
            )
        except Exception:
            pass
        return True

    return False
