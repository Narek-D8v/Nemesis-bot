import re
import time

import aiosqlite
from aiogram.types import Message


from db import db
from utils import esc
from utils.mentions import extract_user
from utils.user_name import resolve_name

ADD_BOOKMARK_CMD = re.compile(r'^\+закладка\s+', re.IGNORECASE)
SHOW_BOOKMARK_CMD = re.compile(r'^закладка\s+(\d+)$', re.IGNORECASE)
CHATBOOK_CMD = re.compile(r'^чатбук\b', re.IGNORECASE)
MY_BOOKMARKS_CMD = re.compile(r'^мои\s+закладки\b', re.IGNORECASE)
USER_BOOKMARKS_CMD = re.compile(r'^закладки\s+', re.IGNORECASE)
DEL_BOOKMARK_CMD = re.compile(r'^(удалить\s+закладку|-закладка)\s+(\d+)$', re.IGNORECASE)
HIDE_BOOKMARK_CMD = re.compile(r'^(исключить\s+закладку|убрать\s+закладку)\s+(\d+)$', re.IGNORECASE)
ADD_CLADMEN_CMD = re.compile(r'^\+кладмен\s+', re.IGNORECASE)
REM_CLADMEN_CMD = re.compile(r'^-кладмен\s+', re.IGNORECASE)

ITEMS_PER_PAGE = 10


async def handle_bookmark_commands(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    stripped = text.strip()

    m = ADD_BOOKMARK_CMD.match(stripped)
    if m:
        rest = stripped[m.end():]
        newline_idx = rest.find('\n')
        if newline_idx >= 0:
            title = rest[:newline_idx].strip()
            content = rest[newline_idx:].strip()
            msg_id = None
        elif message.reply_to_message:
            title = rest.strip()
            content = message.reply_to_message.text or message.reply_to_message.caption or ""
            msg_id = message.reply_to_message.message_id
        else:
            await message.reply("❌ Укажите описание после переноса строки или ответьте на сообщение.")
            return True

        if not title:
            await message.reply("❌ Укажите название закладки.")
            return True

        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO bookmarks (chat_id, user_id, title, text_content, message_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, title, content, msg_id, int(time.time()))
            )
            await conn.commit()

        await message.reply(f"✅ Закладка «{esc(title)}» добавлена!")
        return True

    m = DEL_BOOKMARK_CMD.match(stripped)
    if m:
        num = int(m.group(2))
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, user_id FROM bookmarks WHERE chat_id = ? ORDER BY created_at DESC",
                (chat_id,)
            )
            rows = await cursor.fetchall()
            if num <= len(rows):
                bm_id, owner_id = rows[num - 1]
                user_rank = await db.get_user_rank(chat_id, user_id) or 0
                if owner_id != user_id and user_rank < 2:
                    await message.reply("❌ Вы не можете удалить чужую закладку.")
                    return True
                await conn.execute("DELETE FROM bookmarks WHERE id = ?", (bm_id,))
                await conn.commit()
                await message.reply(f"✅ Закладка #{num} удалена.")
            else:
                await message.reply("❌ Закладка с таким номером не найдена.")
        return True

    m = HIDE_BOOKMARK_CMD.match(stripped)
    if m:
        num = int(m.group(2))
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, user_id FROM bookmarks WHERE chat_id = ? ORDER BY created_at DESC",
                (chat_id,)
            )
            rows = await cursor.fetchall()
            if num <= len(rows):
                bm_id, owner_id = rows[num - 1]
                user_rank = await db.get_user_rank(chat_id, user_id) or 0
                if owner_id != user_id and user_rank < 2:
                    await message.reply("❌ Вы не можете исключить чужую закладку.")
                    return True
                await conn.execute("UPDATE bookmarks SET is_hidden = 1 WHERE id = ?", (bm_id,))
                await conn.commit()
                await message.reply(f"✅ Закладка #{num} исключена из чатбука.")
            else:
                await message.reply("❌ Закладка с таким номером не найдена.")
        return True

    m = SHOW_BOOKMARK_CMD.match(stripped)
    if m:
        num = int(m.group(1))
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT title, text_content, user_id, message_id, created_at FROM bookmarks WHERE chat_id = ? AND is_hidden = 0 ORDER BY created_at DESC",
                (chat_id,)
            )
            rows = await cursor.fetchall()
            if num <= len(rows):
                title, content, owner_id, msg_id, created_at = rows[num - 1]
                owner_name = await resolve_name(chat_id, owner_id)
                d = time.strftime("%d.%m.%Y", time.localtime(created_at))
                link = ""
                if msg_id:
                    chat_link = str(chat_id)
                    if chat_link.startswith("-100"):
                        chat_link = chat_link[4:]
                    link = f"\n🔗 <a href='https://t.me/c/{chat_link}/{msg_id}'>Перейти к сообщению</a>"
                await message.reply(
                    f"📌 <b>{esc(title)}</b>\n"
                    f"👤 {owner_name} • {d}{link}\n\n"
                    f"{esc(content[:500])}"
                )
            else:
                await message.reply("❌ Закладка с таким номером не найдена.")
        return True

    m = CHATBOOK_CMD.match(stripped)
    if m:
        page = 1
        rest = stripped[m.end():].strip()
        if rest:
            try:
                page = int(rest)
            except ValueError:
                pass
        offset = (page - 1) * ITEMS_PER_PAGE
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT title, user_id, created_at FROM bookmarks WHERE chat_id = ? AND is_hidden = 0 ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (chat_id, ITEMS_PER_PAGE, offset)
            )
            rows = await cursor.fetchall()
            cursor2 = await conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE chat_id = ? AND is_hidden = 0",
                (chat_id,)
            )
            total = (await cursor2.fetchone())[0]
        if not rows:
            await message.reply("📖 Чатбук пуст.")
            return True
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        lines = [f"📖 <b>Чатбук</b> (стр. {page}/{total_pages}):\n"]
        for i, (title, owner_id, created_at) in enumerate(rows, offset + 1):
            oname = await resolve_name(chat_id, owner_id)
            lines.append(f"{i}. <b>{esc(title)}</b> — {oname}")
        await message.reply("\n".join(lines))
        return True

    m = MY_BOOKMARKS_CMD.match(stripped)
    if m:
        page = 1
        rest = stripped[m.end():].strip()
        if rest:
            try:
                page = int(rest)
            except ValueError:
                pass
        offset = (page - 1) * ITEMS_PER_PAGE
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT title, created_at, is_hidden FROM bookmarks WHERE chat_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (chat_id, user_id, ITEMS_PER_PAGE, offset)
            )
            rows = await cursor.fetchall()
            cursor2 = await conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            total = (await cursor2.fetchone())[0]
        if not rows:
            await message.reply("У вас пока нет закладок.")
            return True
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        lines = [f"📑 <b>Мои закладки</b> (стр. {page}/{total_pages}):\n"]
        for i, (title, created_at, hidden) in enumerate(rows, offset + 1):
            h = " 🔒" if hidden else ""
            lines.append(f"{i}. <b>{esc(title)}</b>{h}")
        await message.reply("\n".join(lines))
        return True

    m = USER_BOOKMARKS_CMD.match(stripped)
    if m:
        page = 1
        rest = stripped[m.end():].strip()
        parts = rest.rsplit(None, 1)
        if len(parts) == 2 and parts[1].isdigit():
            page = int(parts[1])
            rest = parts[0]
        else:
            page = 1
        target = await extract_user(rest, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        offset = (page - 1) * ITEMS_PER_PAGE
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT title, created_at, is_hidden FROM bookmarks WHERE chat_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (chat_id, target, ITEMS_PER_PAGE, offset)
            )
            rows = await cursor.fetchall()
            cursor2 = await conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            total = (await cursor2.fetchone())[0]
        tname = await resolve_name(chat_id, target)
        if not rows:
            await message.reply(f"У {tname} нет закладок.")
            return True
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        lines = [f"📑 <b>Закладки {tname}</b> (стр. {page}/{total_pages}):\n"]
        for i, (title, created_at, hidden) in enumerate(rows, offset + 1):
            h = " 🔒" if hidden else ""
            lines.append(f"{i}. <b>{esc(title)}</b>{h}")
        await message.reply("\n".join(lines))
        return True

    if ADD_CLADMEN_CMD.match(stripped):
        min_rank = await db.get_command_restriction(chat_id, "модерация_закладок")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM bookmarks_banned WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            await conn.execute(
                "UPDATE bookmarks SET is_hidden = 0 WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Закладки пользователя {tname} возвращены в чатбук.")
        return True

    if REM_CLADMEN_CMD.match(stripped):
        min_rank = await db.get_command_restriction(chat_id, "модерация_закладок")
        user_rank = await db.get_user_rank(chat_id, user_id) or 0
        if user_rank < min_rank:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO bookmarks_banned (chat_id, user_id) VALUES (?, ?)",
                (chat_id, target)
            )
            await conn.execute(
                "UPDATE bookmarks SET is_hidden = 1 WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Закладки пользователя {tname} скрыты из чатбука.")
        return True

    return False
