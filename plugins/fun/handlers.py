import random
import re
import time

import aiosqlite
from aiogram.types import Message

from db import db
from utils import esc, format_duration
from utils.mentions import extract_user
from utils.user_name import resolve_name

SHIP_CMD = re.compile(r'^шипперим\b', re.IGNORECASE)
OPTOUT_CMD = re.compile(r'^[-+]\s*шип\s+меня\b', re.IGNORECASE)
PAIRING_CMD = re.compile(r'^пейринг\b', re.IGNORECASE)
GLOBAL_PAIRING_CMD = re.compile(r'^общий\s+пейринг\b', re.IGNORECASE)
RESET_PAIRS_CMD = re.compile(r'^!сбросить\s+пейринг\b', re.IGNORECASE)

SAY_CMD = re.compile(r'^!скажи\s+', re.IGNORECASE)
RANDOM_CMD = re.compile(r'^рандом\b', re.IGNORECASE)
INFA_CMD = re.compile(r'^!инфа\s+', re.IGNORECASE)
VIBERI_CMD = re.compile(r'^!выбери\s+(.+?)\s+или\s+(.+)$', re.IGNORECASE)
DANET_CMD = re.compile(r'^!данет\s+', re.IGNORECASE)
ZHREBIY_CMD = re.compile(r'^!жребий\b', re.IGNORECASE)
KTO_CMD = re.compile(r'^!кто\b', re.IGNORECASE)

PING_WORDS = {'пинг', 'кинг', 'пиу', 'бот'}


async def handle_shipping(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    stripped = text.strip()

    if OPTOUT_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            if stripped.startswith('+') or stripped.startswith('+ '):
                await conn.execute(
                    "DELETE FROM fun_shipping_optout WHERE chat_id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
                await conn.commit()
                await message.reply("✅ Теперь вас можно шипперить с другими.")
            else:
                await conn.execute(
                    "INSERT OR IGNORE INTO fun_shipping_optout (chat_id, user_id) VALUES (?, ?)",
                    (chat_id, user_id)
                )
                await conn.commit()
                await message.reply("✅ Вы исключены из шипперинга.")
        return True

    if RESET_PAIRS_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM fun_shipping_pairs WHERE shipper_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            await conn.commit()
        await message.reply("✅ Все ваши пары удалены.")
        return True

    if GLOBAL_PAIRING_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user1_id, user2_id, shipper_id, created_at FROM fun_shipping_pairs ORDER BY created_at DESC LIMIT 30"
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("🌐 Пока нет ни одной зашипперинной пары.")
            return True
        lines = ["🌐 <b>Общий пейринг:</b>\n"]
        for u1, u2, sid, ts in rows:
            d = time.strftime("%d.%m", time.localtime(ts))
            n1 = await resolve_name(chat_id, u1)
            n2 = await resolve_name(chat_id, u2)
            ns = await resolve_name(chat_id, sid)
            lines.append(f"• {n1} + {n2} (от {ns}, {d})")
        await message.reply("\n".join(lines))
        return True

    if PAIRING_CMD.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user1_id, user2_id, shipper_id, created_at FROM fun_shipping_pairs WHERE chat_id = ? ORDER BY created_at DESC LIMIT 30",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("💔 В этом чате пока нет зашипперинных пар.")
            return True
        lines = ["💞 <b>Пейринг чата:</b>\n"]
        for u1, u2, sid, ts in rows:
            d = time.strftime("%d.%m", time.localtime(ts))
            n1 = await resolve_name(chat_id, u1)
            n2 = await resolve_name(chat_id, u2)
            ns = await resolve_name(chat_id, sid)
            lines.append(f"• {n1} + {n2} (от {ns}, {d})")
        await message.reply("\n".join(lines))
        return True

    if SHIP_CMD.match(stripped):
        opts = stripped[len("шипперим"):].strip()
        users = []

        if opts:
            parts = opts.split()
            for p in parts:
                uid = await extract_user(p, message)
                if uid:
                    users.append(uid)
            if len(users) < 2:
                await message.reply("❌ Укажите двух пользователей через пробел.")
                return True
            user1, user2 = users[0], users[1]
        else:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT user_id FROM user_last_message WHERE chat_id = ? ORDER BY RANDOM() LIMIT 2",
                    (chat_id,)
                )
                rows = await cursor.fetchall()
            if len(rows) < 2:
                await message.reply("❌ Недостаточно участников для шипперинга.")
                return True
            user1, user2 = rows[0][0], rows[1][0]

        for uid in (user1, user2):
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT 1 FROM fun_shipping_optout WHERE chat_id = ? AND user_id = ?",
                    (chat_id, uid)
                )
                if await cursor.fetchone():
                    uname = await resolve_name(chat_id, uid)
                    await message.reply(f"❌ Пользователь {uname} исключил себя из шипперинга.")
                    return True

        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO fun_shipping_pairs (chat_id, user1_id, user2_id, shipper_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user1, user2, user_id, int(time.time()))
            )
            await conn.commit()

        n1 = await resolve_name(chat_id, user1)
        n2 = await resolve_name(chat_id, user2)

        await message.reply(f"💞 {n1} + {n2} = ❤️ Шипперинг состоялся!")
        return True

    return False


async def handle_text_games(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    stripped = text.strip()

    m = SAY_CMD.match(stripped)
    if m:
        reply_text = stripped[m.end():].strip()
        if reply_text:
            na = re.match(r'рандом\s+(\d+)(?:\s+(\d+))?', reply_text, re.IGNORECASE)
            if na:
                a = int(na.group(1))
                b = int(na.group(2)) if na.group(2) else 0
                lo, hi = (a, b) if b else (0, a)
                if lo > hi:
                    lo, hi = hi, lo
                result = random.randint(lo, hi)
                await message.reply(f"🎲 {result}")
                return True
            await message.reply(reply_text)
        return True

    m = RANDOM_CMD.match(stripped)
    if m:
        rest = stripped[m.end():].strip()
        parts = rest.split()
        if len(parts) >= 1:
            try:
                a = int(parts[0])
                b = int(parts[1]) if len(parts) > 1 else 0
                lo, hi = (a, b) if b else (0, a)
                if lo > hi:
                    lo, hi = hi, lo
                result = random.randint(lo, hi)
                await message.reply(f"🎲 {result}")
            except ValueError:
                await message.reply("❌ Укажите числа.")
        else:
            result = random.randint(0, 100)
            await message.reply(f"🎲 {result}")
        return True

    m = INFA_CMD.match(stripped)
    if m:
        chance = random.randint(0, 100)
        await message.reply(f"🎯 Шанс: {chance}%")
        return True

    m = VIBERI_CMD.match(stripped)
    if m:
        choice = random.choice([m.group(1).strip(), m.group(2).strip()])
        await message.reply(f"🤔 Я выбираю: <b>{esc(choice)}</b>")
        return True

    m = DANET_CMD.match(stripped)
    if m:
        answers = ["Да ✅", "Нет ❌", "Возможно 🤷", "Скорее всего 🤔", "Вряд ли 😕",
                    "Абсолютно точно 💯", "Никогда 🚫", "Спроси позже ⏳"]
        await message.reply(f"🎱 {random.choice(answers)}")
        return True

    m = ZHREBIY_CMD.match(stripped)
    if m:
        rest = stripped[m.end():].strip()
        candidates = []
        for token in re.findall(r'@(\w+)|(\d{5,})', rest):
            candidates.append(token[0] or token[1])
        if not candidates:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT user_id FROM user_last_message WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1",
                    (chat_id,)
                )
                row = await cursor.fetchone()
            if row:
                candidates.append(str(row[0]))
        if candidates:
            picked = random.choice(candidates)
            await message.reply(f"🎯 Жребий пал на: <b>{esc(picked)}</b>")
        else:
            await message.reply("❌ Некого выбирать.")
        return True

    m = KTO_CMD.match(stripped)
    if m:
        from handlers.admin import is_mod_cmd
        if is_mod_cmd(stripped):
            return False
        question = stripped[m.end():].strip()
        if not question:
            return False
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM user_last_message WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1",
                (chat_id,)
            )
            row = await cursor.fetchone()
        if row:
            name = await resolve_name(chat_id, row[0])
            await message.reply(f"👤 {esc(question)} — это <b>{name}</b>")
        else:
            await message.reply(f"👤 {esc(question)} — это <b>никто</b>")
        return True

    return False


async def handle_ping(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    lower = text.strip().lower()
    if lower == "пинг":
        await message.reply("Понг 🏓")
        return True
    if lower == "кинг":
        await message.reply("Конг 🦍")
        return True
    if lower == "пиу":
        await message.reply("Пау 🕷️")
        return True
    if lower in ("бот", "iris", "ирис"):
        await message.reply("На месте ✅")
        return True

    return False


# === моя статья (УК РФ) ===

from .criminal_data import CRIMINAL_ARTICLES


def _get_user_link(message: Message) -> str:
    user = message.from_user
    name = esc(user.first_name or "Пользователь")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def handle_criminal_article(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    stripped = text.strip().lower()
    if stripped != "моя статья":
        return False

    if message.chat.type == "private":
        await message.reply("😊 Эта команда работает только в группах!")
        return True

    if message.chat.type not in ("group", "supergroup"):
        return False

    now = int(time.time())
    user_link = _get_user_link(message)

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT article_num, article_title, created_at FROM fun_criminal_record WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        row = await cursor.fetchone()

        if row and (now - row[2]) < 43200:
            await message.reply(
                f"🤷‍♂️ Сегодня в отношении {user_link} уже вынесен приговор по статье <b>{row[0]}</b>.\n"
                f"<blockquote>{row[1]}</blockquote>"
            )
            return True

    num, title = random.choice(CRIMINAL_ARTICLES)

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO fun_criminal_record (user_id, chat_id, article_num, article_title, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, num, title, now)
        )
        await conn.commit()

    await message.reply(
        f"🤷‍♂️ Сегодня {user_link} приговаривается к статье <b>{num}</b>.\n"
        f"<blockquote>{title}</blockquote>"
    )
    return True


# === мой грех ===

from .sins_data import SINS


async def handle_sin(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    stripped = text.strip().lower()
    if stripped != "мой грех":
        return False

    if message.chat.type == "private":
        await message.reply("😇 Эта команда работает только в группах!")
        return True

    if message.chat.type not in ("group", "supergroup"):
        return False

    now = int(time.time())
    user_link = _get_user_link(message)

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT sin_name, sin_desc, created_at FROM fun_sins_record WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        row = await cursor.fetchone()

        if row and (now - row[2]) < 43200:
            await message.reply(
                f"😈 {user_link} ваш сегодняшний грех уже был определён:\n"
                f"<b>{row[0]}</b>\n"
                f"<blockquote>{row[1]}</blockquote>"
            )
            return True

    sin_name, sin_desc = random.choice(SINS)

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO fun_sins_record (user_id, chat_id, sin_name, sin_desc, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, sin_name, sin_desc, now)
        )
        await conn.commit()

    await message.reply(
        f"😈 {user_link} ваш сегодняшний грех:\n"
        f"<b>{sin_name}</b>\n"
        f"<blockquote>{sin_desc}</blockquote>"
    )
    return True


# === моя зависимость ===

from .addictions_data import ADDICTIONS


async def handle_addiction(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    stripped = text.strip().lower()
    if stripped != "моя зависимость":
        return False

    if message.chat.type == "private":
        await message.reply("😌 Эта команда работает только в группах!")
        return True

    if message.chat.type not in ("group", "supergroup"):
        return False

    now = int(time.time())
    user_link = _get_user_link(message)

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT addiction_name, addiction_desc, created_at FROM fun_addictions_record WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        row = await cursor.fetchone()

        if row and (now - row[2]) < 43200:
            await message.reply(
                f"🚬 Сегодня в отношении {user_link} уже определена зависимость:\n"
                f"<b>{row[0]}</b>\n"
                f"<blockquote>{row[1]}</blockquote>"
            )
            return True

    addiction_name, addiction_desc = random.choice(ADDICTIONS)

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO fun_addictions_record (user_id, chat_id, addiction_name, addiction_desc, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, addiction_name, addiction_desc, now)
        )
        await conn.commit()

    await message.reply(
        f"🚬 {user_link} ваша сегодняшняя зависимость:\n"
        f"<b>{addiction_name}</b>\n"
        f"<blockquote>{addiction_desc}</blockquote>"
    )
    return True


# === моё состояние ===

from .states_data import STATES


async def handle_state(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    stripped = text.strip().lower()
    if stripped != "моё состояние":
        return False

    if message.chat.type == "private":
        await message.reply("😊 Эта команда работает только в группах!")
        return True

    if message.chat.type not in ("group", "supergroup"):
        return False

    now = int(time.time())
    user_link = _get_user_link(message)

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT state_name, state_desc, created_at FROM fun_states_record WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        row = await cursor.fetchone()

        if row and (now - row[2]) < 43200:
            await message.reply(
                f"🌀 {user_link} ваше сегодняшнее психологическое состояние уже было определено:\n"
                f"<b>{row[0]}</b>\n"
                f"<blockquote>{row[1]}</blockquote>"
            )
            return True

    state_name, state_desc = random.choice(STATES)

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO fun_states_record (user_id, chat_id, state_name, state_desc, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, state_name, state_desc, now)
        )
        await conn.commit()

    await message.reply(
        f"🌀 {user_link} ваше сегодняшнее психологическое состояние:\n"
        f"<b>{state_name}</b>\n"
        f"<blockquote>{state_desc}</blockquote>"
    )
    return True


# === моя философия ===

from .philosophies_data import PHILOSOPHIES


async def handle_philosophy(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    stripped = text.strip().lower()
    if stripped != "моя философия":
        return False

    if message.chat.type == "private":
        await message.reply("😊 Эта команда работает только в группах!")
        return True

    if message.chat.type not in ("group", "supergroup"):
        return False

    now = int(time.time())
    user_link = _get_user_link(message)

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT philosophy_name, philosophy_desc, created_at FROM fun_philosophies_record WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        row = await cursor.fetchone()

        if row and (now - row[2]) < 43200:
            await message.reply(
                f"🏛️ {user_link} ваша сегодняшняя философия уже была определена:\n"
                f"<b>{row[0]}</b>\n"
                f"<blockquote>{row[1]}</blockquote>"
            )
            return True

    philosophy_name, philosophy_desc = random.choice(PHILOSOPHIES)

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO fun_philosophies_record (user_id, chat_id, philosophy_name, philosophy_desc, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, philosophy_name, philosophy_desc, now)
        )
        await conn.commit()

    await message.reply(
        f"🏛️ {user_link} ваша сегодняшняя философия:\n"
        f"<b>{philosophy_name}</b>\n"
        f"<blockquote>{philosophy_desc}</blockquote>"
    )
    return True
