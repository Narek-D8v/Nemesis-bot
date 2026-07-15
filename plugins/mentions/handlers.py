import asyncio
import re
import time

import aiosqlite
from aiogram.types import Message

from bot import bot, logger
from db import db
from utils import esc
from utils.mentions import extract_user

CALL_LURKERS = re.compile(r'^(позвать|созвать)\s+молчунов\b', re.IGNORECASE)
CALL_USERS = re.compile(r'^позвать\b', re.IGNORECASE)
CALL_ALL = re.compile(r'^(созвать\s+всех|общий\s+сбор)\b', re.IGNORECASE)
CALL_ONLINE = re.compile(r'^созвать\s+онлайн\b', re.IGNORECASE)

LURKER_DAYS = 14
MENTION_LIMIT = 50


async def _get_restriction(chat_id: int, cmd_type: str) -> int:
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT min_rank FROM mention_restrictions WHERE chat_id = ? AND command_type = ?",
            (chat_id, cmd_type)
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def handle_mention_commands(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    stripped = text.strip()

    dk_m = re.match(r'^дк\s+(.+?)\s+(\d+)$', stripped, re.IGNORECASE)
    if dk_m:
        cmd_key = dk_m.group(1).strip().lower()
        restrict_map = {
            'олды': 'old', 'новички': 'new', 'актив': 'active',
            'стата': 'stats', 'чат инфо': 'chat_info',
            'код беседы': 'chat_code', 'общий сбор': 'mass_mention',
        }
        cmd_type = restrict_map.get(cmd_key)
        if cmd_type:
            ur = await db.get_user_rank(chat_id, user_id) or 0
            if ur < 4:
                await message.reply("❌ Недостаточно прав. Требуется ранг 4+.")
                return True
            min_r = int(dk_m.group(2))
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO mention_restrictions (chat_id, command_type, min_rank) VALUES (?, ?, ?)",
                    (chat_id, cmd_type, min_r)
                )
                await conn.commit()
            await message.reply(f"✅ {cmd_key}: минимальный ранг {min_r}.")
            return True

    m = CALL_ALL.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'mass_mention')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            await message.reply("❌ Недостаточно прав для общего сбора.")
            return True

        newline_idx = text.find('\n')
        call_text = text[newline_idx:].strip() if newline_idx >= 0 else "Внимание, общий сбор!"

        try:
            admins = await bot.get_chat_administrators(chat_id)
        except Exception as e:
            await message.reply(f"❌ Ошибка получения списка участников: {e}")
            return True

        mentions = []
        for admin in admins:
            if not admin.user.is_bot:
                mentions.append(f"<a href='tg://user?id={admin.user.id}'>\u2060</a>")
        if not mentions:
            await message.reply("Некого созывать.")
            return True

        for batch_start in range(0, min(len(mentions), MENTION_LIMIT), 10):
            batch = mentions[batch_start:batch_start + 10]
            try:
                await message.answer(f"📢 {esc(call_text)}\n{' '.join(batch)}")
            except Exception as e:
                logger.warning(f"Call all send error: {e}")
                break
            await asyncio.sleep(0.5)
        try:
            await message.delete()
        except Exception:
            pass
        return True

    m = CALL_ONLINE.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'mass_mention')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            await message.reply("❌ Недостаточно прав.")
            return True

        newline_idx = text.find('\n')
        call_text = text[newline_idx:].strip() if newline_idx >= 0 else "Онлайн участники!"

        cutoff = int(time.time()) - 86400
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM user_last_message WHERE chat_id = ? AND last_msg_at > ? ORDER BY RANDOM() LIMIT ?",
                (chat_id, cutoff, MENTION_LIMIT)
            )
            rows = await cursor.fetchall()

        if not rows:
            await message.reply("Нет активных пользователей для созыва.")
            return True

        mentions = []
        for (uid,) in rows:
            mentions.append(f"<a href='tg://user?id={uid}'>\u2060</a>")

        for batch_start in range(0, len(mentions), 10):
            batch = mentions[batch_start:batch_start + 10]
            try:
                await message.answer(f"📢 {esc(call_text)}\n{' '.join(batch)}")
            except Exception as e:
                logger.warning(f"Call online send error: {e}")
                break
            await asyncio.sleep(0.5)
        try:
            await message.delete()
        except Exception:
            pass
        return True

    m = CALL_LURKERS.match(stripped)
    if m:
        cutoff = int(time.time()) - LURKER_DAYS * 86400
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, COALESCE(last_msg_at, 0) FROM user_last_message WHERE chat_id = ? AND last_msg_at < ? ORDER BY last_msg_at ASC LIMIT 30",
                (chat_id, cutoff)
            )
            rows = await cursor.fetchall()

        if not rows:
            await message.reply("Молчунов нет! 🎉")
            return True

        mentions = []
        for (uid, last_active) in rows:
            try:
                member = await bot.get_chat_member(chat_id, uid)
                if member.status != "left" and not member.user.is_bot:
                    mentions.append(f"<a href='tg://user?id={uid}'>\u2060</a>")
            except Exception:
                pass

        if not mentions:
            await message.reply("Молчунов нет! 🎉")
            return True

        for batch_start in range(0, min(len(mentions), MENTION_LIMIT), 10):
            batch = mentions[batch_start:batch_start + 10]
            try:
                await message.answer(f"📢 Просыпайтесь, молчуны! {' '.join(batch)}")
            except Exception as e:
                logger.warning(f"Call lurkers send error: {e}")
                break
            await asyncio.sleep(0.5)
        try:
            await message.delete()
        except Exception:
            pass
        return True

    m = CALL_USERS.match(stripped)
    if m:
        rest = stripped[m.end():].strip()
        if not rest and message.reply_to_message:
            ref_text = message.reply_to_message.text or message.reply_to_message.caption or ""
            users = re.findall(r'@(\w+)', ref_text)
            if not users:
                await message.reply("❌ В цитируемом сообщении нет упоминаний.")
                return True
            mentions = [f"@{u}" for u in users[:MENTION_LIMIT]]
        elif rest:
            parts = rest.split()
            mentions = []
            for p in parts:
                uid = await extract_user(p, message)
                if uid:
                    mentions.append(f"<a href='tg://user?id={uid}'>\u2060</a>")
            if not mentions:
                await message.reply("❌ Укажите пользователей (@username или ссылка).")
                return True
            mentions = mentions[:MENTION_LIMIT]
        else:
            await message.reply("❌ Укажите пользователей или ответьте на сообщение с упоминаниями.")
            return True

        for batch_start in range(0, len(mentions), 10):
            batch = mentions[batch_start:batch_start + 10]
            try:
                await message.answer(f"📢 Вас зовут! {' '.join(batch)}")
            except Exception as e:
                logger.warning(f"Call users send error: {e}")
                break
            await asyncio.sleep(0.5)
        try:
            await message.delete()
        except Exception:
            pass
        return True

    return False
