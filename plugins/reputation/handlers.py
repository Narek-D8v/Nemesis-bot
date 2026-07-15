import re
import time

import aiosqlite
from aiogram.types import Message

from bot import bot, logger
from db import db
from utils.user_name import resolve_name

PLUS_VOTE = re.compile(r'^[+](\d*)$')
MINUS_VOTE = re.compile(r'^[-](\d+)$')
STAR_VOTE = re.compile(r'^[*^](\d*)$')

SYNONYM_PLUS = {'лайк', 'респект', 'f', 'уважение', 'увожение', 'жиза', 'жыза', 'плюс', 'красавчик', 'справедливо', 'meine respektierung'}

RATING_CMD = re.compile(r'^рейт(инг)?\b', re.IGNORECASE)
STAR_USER_CMD = re.compile(r'^(звёздность|звездность|!зв)\s+', re.IGNORECASE)
MY_STAR_CMD = re.compile(r'^(моя\s+звёздность|моя\s+звездность|мзв)\b', re.IGNORECASE)
STARS_CHAT_CMD = re.compile(r'^звёзды\s+чата\b', re.IGNORECASE)
STARS_ALL_CMD = re.compile(r'^все\s+звёзды\b', re.IGNORECASE)
PROMOTE_STAR_CMD = re.compile(r'^(!повысить|повысить)\s+звёздность\s+до\s+(\d+)\b', re.IGNORECASE)
RESET_RATING_CMD = re.compile(r'^(!сбросить|!обнулить)\s+рейтинг\b', re.IGNORECASE)

MAX_VOTE_BY_RANK = {0: 1, 1: 3, 2: 5, 3: 10, 4: 20, 5: 50}


async def _get_user_rank_for_vote(chat_id: int, user_id: int) -> int:
    return await db.get_user_rank(chat_id, user_id) or 0


async def handle_rating_vote(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return False

    stripped = text.strip()
    target_id = message.reply_to_message.from_user.id
    if target_id == user_id or target_id == (await bot.get_me()).id:
        return False

    vote_amount = 0
    vote_type = None

    m = PLUS_VOTE.match(stripped)
    if m:
        vote_type = "plus"
        rank = await _get_user_rank_for_vote(chat_id, user_id)
        max_vote = MAX_VOTE_BY_RANK.get(rank, 1)
        vote_amount = int(m.group(1)) if m.group(1) else 1
        vote_amount = min(vote_amount, max_vote)

    if not m:
        m = MINUS_VOTE.match(stripped)
        if m:
            vote_type = "minus"
            rank = await _get_user_rank_for_vote(chat_id, user_id)
            max_vote = MAX_VOTE_BY_RANK.get(rank, 1)
            vote_amount = int(m.group(1))
            vote_amount = min(vote_amount, max_vote)

    if not m:
        m = STAR_VOTE.match(stripped)
        if m:
            vote_type = "star"
            vote_amount = int(m.group(1)) if m.group(1) else 1

    if not vote_type:
        lower_word = stripped.lower().strip()
        if lower_word in SYNONYM_PLUS:
            vote_type = "plus"
            vote_amount = 1

    if not vote_type or vote_amount <= 0:
        return False

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT rating, stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        )
        row = await cursor.fetchone()

        now = int(time.time())
        if row:
            rating, stars = row
            if vote_type == "plus":
                new_rating = rating + vote_amount
                await conn.execute(
                    "UPDATE rep_rating SET rating = ?, pluses_received = pluses_received + ? WHERE chat_id = ? AND user_id = ?",
                    (new_rating, vote_amount, chat_id, target_id)
                )
                await conn.execute(
                    "UPDATE rep_rating SET pluses_given = pluses_given + ? WHERE chat_id = ? AND user_id = ?",
                    (vote_amount, chat_id, user_id)
                )
            elif vote_type == "minus":
                new_rating = rating - vote_amount
                await conn.execute(
                    "UPDATE rep_rating SET rating = ? WHERE chat_id = ? AND user_id = ?",
                    (new_rating, chat_id, target_id)
                )
            elif vote_type == "star":
                await conn.execute(
                    "UPDATE rep_rating SET stars = stars + ? WHERE chat_id = ? AND user_id = ?",
                    (vote_amount, chat_id, target_id)
                )
        else:
            if vote_type == "plus":
                await conn.execute(
                    "INSERT INTO rep_rating (chat_id, user_id, rating, stars, last_tax_rating, pluses_given, pluses_received) VALUES (?, ?, ?, 0, ?, ?, ?)",
                    (chat_id, target_id, vote_amount, now, 0, vote_amount)
                )
                await conn.execute(
                    "INSERT OR IGNORE INTO rep_rating (chat_id, user_id, rating, stars, last_tax_rating, pluses_given, pluses_received) VALUES (?, ?, 0, 0, ?, ?, 0)",
                    (chat_id, user_id, now, vote_amount)
                )
            elif vote_type == "minus":
                await conn.execute(
                    "INSERT INTO rep_rating (chat_id, user_id, rating, stars, last_tax_rating) VALUES (?, ?, ?, 0, ?)",
                    (chat_id, target_id, -vote_amount, now)
                )
            elif vote_type == "star":
                await conn.execute(
                    "INSERT INTO rep_rating (chat_id, user_id, rating, stars, last_tax_rating) VALUES (?, ?, 0, ?, ?)",
                    (chat_id, target_id, vote_amount, now)
                )
        await conn.commit()

    await message.delete()
    return True


async def handle_rating_commands(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    stripped = text.strip()

    if RESET_RATING_CMD.match(stripped):
        rank = await db.get_user_rank(chat_id, user_id) or 0
        if rank < 4:
            await message.reply("❌ Недостаточно прав. Требуется ранг 4+.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute("DELETE FROM rep_rating WHERE chat_id = ?", (chat_id,))
            await conn.commit()
        await message.reply("✅ Рейтинг чата обнулён.")
        return True

    m = PROMOTE_STAR_CMD.match(stripped)
    if m:
        target_stars = int(m.group(2))
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
            if row:
                stars = row[0]
                if target_stars > stars:
                    await conn.execute(
                        "UPDATE rep_rating SET stars = ? WHERE chat_id = ? AND user_id = ?",
                        (target_stars, chat_id, user_id)
                    )
                    await conn.commit()
                    await message.reply(f"✅ Ваша звёздность повышена до {target_stars} ⭐")
                else:
                    await message.reply(f"⚠️ Ваша звёздность уже {stars}. Укажите большее значение.")
            else:
                await conn.execute(
                    "INSERT INTO rep_rating (chat_id, user_id, rating, stars, last_tax_rating) VALUES (?, ?, 0, ?, ?)",
                    (chat_id, user_id, target_stars, int(time.time()))
                )
                await conn.commit()
                await message.reply(f"✅ Ваша звёздность установлена на {target_stars} ⭐")
        return True

    m = STAR_USER_CMD.match(stripped)
    if m:
        from utils.mentions import extract_user
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            row = await cursor.fetchone()
        name = await resolve_name(chat_id, target)
        if row:
            await message.reply(f"⭐ <b>Звёздность {name}</b>\nЗвёзды: {row[0]}")
        else:
            await message.reply(f"⭐ <b>Звёздность {name}</b>\nЗвёзды: 0")
        return True

    if MY_STAR_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
        if row:
            await message.reply(f"⭐ <b>Ваша звёздность</b>\nЗвёзды: {row[0]}")
        else:
            await message.reply(f"⭐ <b>Ваша звёздность</b>\nЗвёзды: 0")
        return True

    if STARS_CHAT_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, stars FROM rep_rating WHERE chat_id = ? AND stars > 0 ORDER BY stars DESC LIMIT 10",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("В этом чате пока нет звёзд.")
            return True
        lines = ["⭐ <b>Звёзды чата:</b>\n"]
        for i, (uid, s) in enumerate(rows, 1):
            name = await resolve_name(chat_id, uid)
            lines.append(f"{i}. {name} — {s} ⭐")
        await message.reply("\n".join(lines))
        return True

    if STARS_ALL_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, SUM(stars) as total FROM rep_rating WHERE stars > 0 GROUP BY user_id ORDER BY total DESC LIMIT 10"
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("Пока никто не имеет звёзд.")
            return True
        lines = ["🌌 <b>Общий рейтинг звёздности:</b>\n"]
        for i, (uid, total) in enumerate(rows, 1):
            name = await resolve_name(chat_id, uid)
            lines.append(f"{i}. {name} — {total} ⭐")
        await message.reply("\n".join(lines))
        return True

    if RATING_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, rating FROM rep_rating WHERE chat_id = ? ORDER BY rating DESC LIMIT 10",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("Рейтинг пока пуст.")
            return True
        lines = ["🏆 <b>Рейтинг чата:</b>\n"]
        for i, (uid, r) in enumerate(rows, 1):
            name = await resolve_name(chat_id, uid)
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "•"
            lines.append(f"{emoji} {name} — {r}")
        await message.reply("\n".join(lines))
        return True

    return False
