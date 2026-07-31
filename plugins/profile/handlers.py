import asyncio
import io
import json
import os
import re
import tempfile
import time
from datetime import datetime

import aiosqlite
from aiogram.types import Message, FSInputFile

from bot import bot, logger
from db import db
from utils import esc
from utils.mentions import extract_user
from utils.user_name import resolve_name

CITIES_BASE_URL = "https://iris-tg.ru/cities/{}"
_CITY_INDEX: dict[str, dict] = {}
try:
    _cities_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cities.json")
    with open(_cities_path, encoding="utf-8") as _f:
        for _c in json.load(_f):
            _CITY_INDEX[_c["name"].lower()] = _c
except Exception as e:
    logger.warning(f"Cities database failed to load: {e}")

ANKETA_CMD = re.compile(r'^(моя\s+)?анкета\b', re.IGNORECASE)
TOGGLE_ANKETA = re.compile(r'^[+-]анкета\b', re.IGNORECASE)
MY_GENDER = re.compile(r'^мой\s+пол\s+(.+)$', re.IGNORECASE)
RM_GENDER = re.compile(r'^-мой\s+пол\b', re.IGNORECASE)
MY_CITY = re.compile(r'^!?мой\s+город\s+(.+)$', re.IGNORECASE)
RM_CITY = re.compile(r'^-мой\s+город\b', re.IGNORECASE)
MY_BDAY = re.compile(r'^мой\s+др\s+(\d{1,2}\.\d{1,2}\.\d{2,4})(?:\s+(вс[её]|месяц|год))?$', re.IGNORECASE)
RM_BDAY = re.compile(r'^-мой\s+др\b', re.IGNORECASE)

KTO_YA = re.compile(r'^(!?кто\s+я|!роль|профиль|хто\s+я)$', re.IGNORECASE)
KTO_TY = re.compile(r'^(!?кто\s+ты|профиль)\s+', re.IGNORECASE)
MY_STATA = re.compile(r'^моя\s+стата\b', re.IGNORECASE)

O_SEBE = re.compile(r'^о\s+себе\b', re.IGNORECASE)
RM_O_SEBE = re.compile(r'^-о\s+себе\b', re.IGNORECASE)
DESCR_USER = re.compile(r'^описание\s+', re.IGNORECASE)
ADMIN_SET_DESCR = re.compile(r'^!назначить\s+описание\s+', re.IGNORECASE)
ADMIN_RM_DESCR = re.compile(r'^!удалить\s+описание\s+', re.IGNORECASE)

SET_NICK = re.compile(r'^[+!](ник|nick)\s+', re.IGNORECASE)
SHOW_NICK = re.compile(r'^ник\b', re.IGNORECASE)
RM_NICK = re.compile(r'^(ник\s+удалить|-ник)\b', re.IGNORECASE)
ADMIN_SET_NICK = re.compile(r'^!назначить\s+ник\s+', re.IGNORECASE)
ADMIN_RM_NICK = re.compile(r'^!удалить\s+ник\s+', re.IGNORECASE)

SET_TITLE = re.compile(r'^[+!]звание\s+', re.IGNORECASE)
SHOW_TITLE = re.compile(r'^звание\b', re.IGNORECASE)
RM_TITLE = re.compile(r'^(звание\s+удалить|-звание)\b', re.IGNORECASE)
ADMIN_SET_TITLE = re.compile(r'^!назначить\s+звание\s+', re.IGNORECASE)
ADMIN_RM_TITLE = re.compile(r'^!удалить\s+звание\s+', re.IGNORECASE)

SET_MOTTO = re.compile(r'^[+]девиз\s+', re.IGNORECASE)
RM_MOTTO = re.compile(r'^-девиз\b', re.IGNORECASE)
SHOW_MOTTO = re.compile(r'^!девиз\b', re.IGNORECASE)

ADD_CITIZEN = re.compile(r'^[+]гражданство\b', re.IGNORECASE)
ALL_CITIZENS = re.compile(r'^(все\s+граждане|кто\s+гражданин|кто\s+граждане)$', re.IGNORECASE)

MY_ACHIEVES = re.compile(r'^мои\s+ачивки\b', re.IGNORECASE)
TOGGLE_ACHIEVES = re.compile(r'^[+-]ачивки\b', re.IGNORECASE)
USER_ACHIEVES = re.compile(r'^(твои\s+ачивки|покажи\s+ачивки)\s+', re.IGNORECASE)

SUBSCRIBE = re.compile(r'^[+]подписка\s+', re.IGNORECASE)
UNSUBSCRIBE = re.compile(r'^-подписка\s+', re.IGNORECASE)
CALL_SUBS = re.compile(r'^(созвать\s+своих|позвать\s+своих)$', re.IGNORECASE)
ALL_SABS = re.compile(r'^все\s+сабы\b', re.IGNORECASE)
CHAT_SABS = re.compile(r'^сабы\s+чата\b', re.IGNORECASE)
MY_SUBS = re.compile(r'^мои\s+подписки\b', re.IGNORECASE)
MY_SABS = re.compile(r'^мои\s+сабы\b', re.IGNORECASE)
USER_SUBS = re.compile(r'^подписки\s+', re.IGNORECASE)

REG_CMD = re.compile(r'^(!регистрация|!рег)\s+', re.IGNORECASE)
ID_CMD = re.compile(r'^(!ид|!id)\s+', re.IGNORECASE)

RESTRICT_CMDS = {
    'дк профиль': 'profile', 'дк анкета': 'anketa',
    'дк установить ник': 'set_nick', 'дк ники': 'nicks', 'дк показать ник': 'show_nick',
    'дк показать свой ник': 'show_my_nick',
    'дк установить звание': 'set_title', 'дк вызвать звание': 'show_title',
    'дк установить описание': 'set_descr', 'дк вызвать описание': 'show_descr',
    'дк подписчики пользователя': 'subscribers',
    'дк гражданство': 'citizenship', 'дк рег': 'reg', 'дк ид': 'id_cmd', 'дк девиз': 'motto',
}

NICK_MAX = 30
TITLE_MAX = 30
MOTTO_MAX = 100
DESCR_MAX = 3800
GENDER_MAX = 20
CITY_MAX = 50
MAX_SUBS = 50
VIP_CALL_LIMIT = 120
NONVIP_CALL_LIMIT = 20


def _normalize_bday(raw: str) -> str | None:
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return None


def _normalize_vis(vis: str | None) -> str:
    if not vis:
        return "full"
    if vis.lower() in ("все", "всё"):
        return "full"
    return vis.lower()


def _resolve_city(raw: str):
    key = re.sub(r"\s+", " ", raw.strip().lower())
    if not key:
        return None
    if key in _CITY_INDEX:
        c = _CITY_INDEX[key]
        return c["name"], c["id"]
    matches = [c for name, c in _CITY_INDEX.items() if name.startswith(key)]
    if len(matches) == 1:
        c = matches[0]
        return c["name"], c["id"]
    return None


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    n1 = n % 10
    if 10 < n < 20:
        return many
    if 1 < n1 < 5:
        return few
    if n1 == 1:
        return one
    return many


def _kfmt(n: int) -> str:
    if n >= 1000:
        s = f"{n / 1000:.1f}k".replace(".", ",")
        return s[:-3] + "k" if s.endswith(",0k") else s
    return str(n)


def _age_str(bday: str) -> str:
    try:
        d = datetime.strptime(bday, "%d.%m.%Y").date()
    except ValueError:
        return ""
    today = datetime.now().date()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    if age < 0:
        age = 0
    return f"({age} {_plural(age, 'год', 'года', 'лет')})"


def _duration_str(reg_ts: int) -> str:
    reg = datetime.fromtimestamp(reg_ts)
    now = datetime.now()
    months = (now.year - reg.year) * 12 + (now.month - reg.month)
    if now.day < reg.day:
        months -= 1
    if months < 0:
        months = 0
    m_total = reg.month - 1 + months
    anchor = datetime(reg.year + m_total // 12, m_total % 12 + 1, min(reg.day, 28))
    days = (now.date() - anchor.date()).days
    parts = []
    if months:
        parts.append(f"{months} {_plural(months, 'месяц', 'месяца', 'месяцев')}")
    if days:
        parts.append(f"{days} {_plural(days, 'день', 'дня', 'дней')}")
    return " ".join(parts) or "0 дней"


def _last_seen_str(ts: int) -> str:
    if not ts:
        return ""
    d = int(time.time()) - ts
    if d < 300:
        return "был только что"
    if d < 3600:
        return "был недавно"
    if d < 86400:
        return "был сегодня"
    if d < 172800:
        return "был вчера"
    if d < 604800:
        return f"был {d // 86400} дн. назад"
    return "был давно"


STAR_LEVELS = [
    (0, "🙂", "Ноунейм"),
    (5, "🌱", "Новичок"),
    (15, "🤝", "Знакомый"),
    (30, "😎", "Свой"),
    (60, "🔥", "Продвинутый"),
    (120, "💎", "Легенда"),
    (300, "👑", "Бог Вселенной"),
]


def _star_level(stars: int):
    emoji, name = STAR_LEVELS[0][1], STAR_LEVELS[0][2]
    for limit, e, n in STAR_LEVELS:
        if stars >= limit:
            emoji, name = e, n
    return emoji, name


def _medal_maps():
    try:
        from plugins.awards.handlers import MEDAL_EMOJIS, MEDAL_NAMES
        return MEDAL_EMOJIS, MEDAL_NAMES
    except ImportError:
        return (
            {1: "🥉", 2: "🥈", 3: "🥇", 4: "🏅", 5: "🎖️", 6: "🏆", 7: "💎", 8: "👑"},
            {1: "Бронза", 2: "Серебро", 3: "Золото", 4: "Медаль", 5: "Орден", 6: "Кубок", 7: "Алмаз", 8: "Корона"},
        )


async def _format_medals(chat_id: int, target_id: int) -> str | None:
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT id, degree, description, created_at, expires_at FROM awards_medals "
            "WHERE chat_id = ? AND user_id = ? ORDER BY degree DESC, created_at DESC LIMIT 20",
            (chat_id, target_id)
        )
        rows = await cursor.fetchall()
    if not rows:
        return None
    medals, mnames = _medal_maps()
    lines = []
    for aid, degree, desc, created_at, expires_at in rows:
        emoji = medals.get(degree, "🎖️")
        name = mnames.get(degree, f"Степень {degree}")
        duration = ""
        if expires_at:
            left = max(0, expires_at - int(time.time()))
            if left > 0:
                duration = f" (ещё {left // 86400} д)"
        lines.append(f"{emoji} <b>{name}</b> #{aid}{duration}\n{esc(desc or '')}")
    return "\n\n".join(lines)


async def _get_restriction(chat_id: int, cmd_type: str) -> int:
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT min_rank FROM profile_restrictions WHERE chat_id = ? AND command_type = ?",
            (chat_id, cmd_type)
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def handle_profile_commands(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        if message.chat.type == "private":
            return await _handle_pm_commands(message, chat_id, user_id, text)
        return False

    stripped = text.strip()

    dk_m = re.match(r'^дк\s+(.+?)\s+(\d+)$', stripped, re.IGNORECASE)
    if dk_m:
        cmd_key = dk_m.group(1).strip().lower()
        cmd_type = RESTRICT_CMDS.get(cmd_key)
        if cmd_type:
            ur = await db.get_user_rank(chat_id, user_id) or 0
            if ur < 4:
                await message.reply("❌ Недостаточно прав. Требуется ранг 4+.")
                return True
            min_r = int(dk_m.group(2))
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO profile_restrictions (chat_id, command_type, min_rank) VALUES (?, ?, ?)",
                    (chat_id, cmd_type, min_r)
                )
                await conn.commit()
            await message.reply(f"✅ {cmd_key}: минимальный ранг {min_r}.")
            return True

    m = ID_CMD.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'id_cmd')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        target = await extract_user(stripped, message)
        if target:
            await message.reply(f"🆔 ID: <code>{target}</code>")
        else:
            await message.reply("❌ Укажите пользователя.")
        return True

    m = REG_CMD.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'reg')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute("SELECT registered_at FROM profile_global WHERE user_id = ?", (target,))
            row = await cursor.fetchone()
        if row and row[0]:
            dt = time.strftime("%d.%m.%Y %H:%M", time.localtime(row[0]))
            tname = await resolve_name(chat_id, target)
            await message.reply(f"📅 Регистрация {tname}: {dt}")
        else:
            await message.reply("📅 Пользователь не найден в системе.")
        return True

    m = USER_SUBS.match(stripped)
    if m:
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT subscriber_id FROM profile_subscriptions WHERE target_id = ? ORDER BY created_at DESC LIMIT 20",
                (target,)
            )
            rows = await cursor.fetchall()
        tn = await resolve_name(chat_id, target)
        if not rows:
            await message.reply(f"У {tn} пока нет подписчиков.")
            return True
        names = []
        for (sid,) in rows:
            names.append(await resolve_name(chat_id, sid))
        await message.reply(f"📋 <b>Подписки {tn}:</b>\n" + ", ".join(names))
        return True

    if MY_SABS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT subscriber_id FROM profile_subscriptions WHERE target_id = ? ORDER BY created_at DESC LIMIT 20",
                (user_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("На вас пока никто не подписан.")
            return True
        names = []
        for (sid,) in rows:
            names.append(await resolve_name(chat_id, sid))
        await message.reply(f"📋 <b>Ваши подписчики:</b>\n" + ", ".join(names))
        return True

    if MY_SUBS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT target_id FROM profile_subscriptions WHERE subscriber_id = ? ORDER BY created_at DESC LIMIT 20",
                (user_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("Вы ни на кого не подписаны.")
            return True
        names = []
        for (tid,) in rows:
            names.append(await resolve_name(chat_id, tid))
        await message.reply(f"📋 <b>Ваши подписки:</b>\n" + ", ".join(names))
        return True

    if CHAT_SABS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT pc.user_id, COUNT(ps.subscriber_id) as cnt FROM profile_chat pc "
                "LEFT JOIN profile_subscriptions ps ON pc.user_id = ps.target_id "
                "WHERE pc.chat_id = ? GROUP BY pc.user_id ORDER BY cnt DESC LIMIT 10",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("В этом чате пока нет инфлюенсеров.")
            return True
        lines = ["📊 <b>Сабы чата:</b>\n"]
        for i, (uid, cnt) in enumerate(rows, 1):
            nm = await resolve_name(chat_id, uid)
            lines.append(f"{i}. {nm} — {cnt}")
        await message.reply("\n".join(lines))
        return True

    if ALL_SABS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT target_id, COUNT(subscriber_id) as cnt FROM profile_subscriptions "
                "GROUP BY target_id ORDER BY cnt DESC LIMIT 10"
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("Вселенная Ириса пока не имеет инфлюенсеров.")
            return True
        lines = ["🌍 <b>Все сабы Вселенной:</b>\n"]
        for i, (uid, cnt) in enumerate(rows, 1):
            nm = await resolve_name(chat_id, uid)
            lines.append(f"{i}. {nm} — {cnt} подписчиков")
        await message.reply("\n".join(lines))
        return True

    if CALL_SUBS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT subscriber_id FROM profile_subscriptions WHERE target_id = ? ORDER BY RANDOM()",
                (user_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("У вас пока нет подписчиков.")
            return True
        is_vip = await db.is_premium_user(user_id)
        limit = VIP_CALL_LIMIT if is_vip else NONVIP_CALL_LIMIT
        mentions = []
        for (sid,) in rows[:limit]:
            try:
                sm = await bot.get_chat_member(chat_id, sid)
                mentions.append(f"<a href='tg://user?id={sid}'>\u2060</a>")
            except Exception:
                pass
        if mentions:
            await message.answer("📢 Созыв подписчиков! " + " ".join(mentions))
            await message.delete()
        else:
            await message.reply("Не удалось созвать подписчиков.")
        return True

    m = SUBSCRIBE.match(stripped)
    if m:
        target = await extract_user(stripped, message)
        if not target or target == user_id or target == (await bot.get_me()).id:
            await message.reply("❌ Укажите корректного пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM profile_subscriptions WHERE subscriber_id = ?",
                (user_id,)
            )
            cnt = (await cursor.fetchone())[0]
            if cnt >= MAX_SUBS:
                await message.reply(f"❌ Максимум {MAX_SUBS} подписок.")
                return True
            await conn.execute(
                "INSERT OR IGNORE INTO profile_subscriptions (subscriber_id, target_id, created_at) VALUES (?, ?, ?)",
                (user_id, target, int(time.time()))
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Вы подписались на пользователя {tname}.")
        return True

    m = UNSUBSCRIBE.match(stripped)
    if m:
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM profile_subscriptions WHERE subscriber_id = ? AND target_id = ?",
                (user_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Вы отписались от пользователя {tname}.")
        return True

    if TOGGLE_ACHIEVES.match(stripped):
        visible = stripped.startswith('+')
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, achievements_visible) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET achievements_visible = ?",
                (user_id, int(visible), int(visible))
            )
            await conn.commit()
        await message.reply(f"✅ Награды {'открыты' if visible else 'скрыты'} для просмотра.")
        return True

    m = USER_ACHIEVES.match(stripped)
    if m:
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT achievements_visible FROM profile_global WHERE user_id = ?",
                (target,)
            )
            row = await cursor.fetchone()
            if row and not row[0]:
                await message.reply("🔒 Пользователь скрыл свои награды.")
                return True
        tn = await resolve_name(chat_id, target)
        medals_text = await _format_medals(chat_id, target)
        if not medals_text:
            await message.reply(f"У {tn} пока нет наград.")
            return True
        await message.reply(f"🎖️ <b>Награды {tn}:</b>\n" + medals_text)
        return True

    if MY_ACHIEVES.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM awards_medals WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            total = (await cursor.fetchone())[0]
        nm = esc(message.from_user.first_name or "Пользователь")
        medals_text = await _format_medals(chat_id, user_id)
        if not medals_text:
            await message.reply(f"У вас пока нет наград. Всего: {total}")
            return True
        await message.reply(f"🎖️ <b>Награды {nm}:</b> ({total} всего)\n" + medals_text)
        return True

    if ADD_CITIZEN.match(stripped):
        mr = await _get_restriction(chat_id, 'citizenship')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, citizenship) VALUES (?, ?, 1) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET citizenship = 1",
                (chat_id, user_id)
            )
            await conn.commit()
        await message.reply(f"✅ Вы получили гражданство чата {esc(message.chat.title or '')}! 🏡")
        return True

    if ALL_CITIZENS.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM profile_chat WHERE chat_id = ? AND citizenship = 1 ORDER BY user_id",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await message.reply("В этом чате пока нет граждан.")
            return True
        names = []
        for (uid,) in rows:
            names.append(await resolve_name(chat_id, uid))
        await message.reply(f"🏡 <b>Граждане чата:</b>\n" + ", ".join(names))
        return True

    m = ADMIN_RM_DESCR.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_descr')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, description) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET description = ''",
                (target,)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Описание пользователя {tname} удалено.")
        return True

    m = ADMIN_SET_DESCR.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_descr')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        newline_idx = text.find('\n')
        if newline_idx < 0:
            await message.reply("❌ Укажите описание после переноса строки.")
            return True
        first_line = text[:newline_idx].strip()
        descr_text = text[newline_idx:].strip()
        target = await extract_user(first_line, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        if len(descr_text) > DESCR_MAX:
            await message.reply(f"❌ Описание слишком длинное (макс. {DESCR_MAX} символов).")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, description) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET description = ?",
                (target, descr_text, descr_text)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Описание пользователя {tname} обновлено.")
        return True

    if RM_O_SEBE.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, description) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET description = ''",
                (user_id,)
            )
            await conn.commit()
        await message.reply("✅ Описание удалено.")
        return True

    if O_SEBE.match(stripped):
        newline_idx = text.find('\n')
        if newline_idx >= 0:
            descr_text = text[newline_idx:].strip()
            if len(descr_text) > DESCR_MAX:
                await message.reply(f"❌ Описание слишком длинное (макс. {DESCR_MAX} символов).")
                return True
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute(
                    "INSERT INTO profile_global (user_id, description) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET description = ?",
                    (user_id, descr_text, descr_text)
                )
                await conn.commit()
            await message.reply("✅ Описание сохранено!")
        else:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT description FROM profile_global WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
            descr = row[0] if row and row[0] else "Описание не задано."
            await message.reply(f"📝 <b>Ваше описание:</b>\n{esc(descr[:500])}")
        return True

    m = DESCR_USER.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'show_descr')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT description FROM profile_global WHERE user_id = ?",
                (target,)
            )
            row = await cursor.fetchone()
        tn = await resolve_name(chat_id, target)
        descr = row[0] if row and row[0] else "Описание не задано."
        await message.reply(f"📝 <b>Описание {tn}:</b>\n{esc(descr[:500])}")
        return True

    m = MY_STATA.match(stripped)
    if m:
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT rating, stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            rep = await cursor.fetchone()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1",
                (chat_id, user_id)
            )
            warns = (await cursor.fetchone())[0]
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM profile_subscriptions WHERE target_id = ?",
                (user_id,)
            )
            subs = (await cursor.fetchone())[0]
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM profile_subscriptions WHERE subscriber_id = ?",
                (user_id,)
            )
            following = (await cursor.fetchone())[0]
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM awards_medals WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            achievements = (await cursor.fetchone())[0]
        nm = esc(message.from_user.first_name or "Пользователь")
        rating_str = str(rep[0]) if rep else "0"
        stars_str = str(rep[1]) if rep else "0"
        await message.reply(
            f"📊 <b>Статистика {nm}</b>\n"
            f"⭐ Рейтинг: {rating_str}\n"
            f"🌟 Звёзды: {stars_str}\n"
            f"⚠️ Варны: {warns}\n"
            f"👥 Подписчики: {subs}\n"
            f"📋 Подписки: {following}\n"
            f"🎖️ Награды: {achievements}"
        )
        return True

    if KTO_TY.match(stripped):
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        await _show_card(message, chat_id, target)
        return True

    if KTO_YA.match(stripped):
        await _show_card(message, chat_id, user_id)
        return True

    m = SET_NICK.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_nick')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        nick = stripped[m.end():].strip()[:NICK_MAX]
        if not nick:
            await message.reply("❌ Укажите ник.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, nickname) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET nickname = ?",
                (chat_id, user_id, nick, nick)
            )
            await conn.commit()
        await message.reply(f"✅ Ник установлен: {esc(nick)}")
        return True

    if RM_NICK.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, nickname) VALUES (?, ?, '') "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET nickname = ''",
                (chat_id, user_id)
            )
            await conn.commit()
        await message.reply("✅ Ник удалён.")
        return True

    if SHOW_NICK.match(stripped):
        mr = await _get_restriction(chat_id, 'show_nick')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        rest = stripped[m.end():].strip()
        if rest and rest.lower() != 'удалить':
            if ur < mr:
                return False
            target = await extract_user(stripped, message) or await extract_user("@" + rest, message)
            if not target:
                await message.reply("❌ Укажите пользователя.")
                return True
        else:
            if ur < (await _get_restriction(chat_id, 'show_my_nick')):
                return False
            target = user_id
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT nickname FROM profile_chat WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            row = await cursor.fetchone()
        tn = await resolve_name(chat_id, target)
        nick = row[0] if row and row[0] else "не установлен"
        await message.reply(f"👤 <b>Ник {tn}:</b> {esc(nick)}")
        return True

    m = ADMIN_SET_NICK.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_nick')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        rest = stripped[m.end():]
        newline_idx = rest.find('\n')
        if newline_idx >= 0:
            target_str = rest[:newline_idx].strip()
            nick = rest[newline_idx:].strip()[:NICK_MAX]
        else:
            parts = rest.rsplit(None, 1)
            if len(parts) == 2:
                target_str = parts[1]
                nick = parts[0]
            else:
                await message.reply("❌ Формат: !Назначить ник {ник} {ссылка}")
                return True
        target = await extract_user(target_str, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, nickname) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET nickname = ?",
                (chat_id, target, nick, nick)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Ник {tname} установлен: {esc(nick)}")
        return True

    m = ADMIN_RM_NICK.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'nick_manage')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, nickname) VALUES (?, ?, '') "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET nickname = ''",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Ник {tname} удалён.")
        return True

    m = SET_TITLE.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_title')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        title = stripped[m.end():].strip()[:TITLE_MAX]
        if not title:
            await message.reply("❌ Укажите звание.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, title) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET title = ?",
                (chat_id, user_id, title, title)
            )
            await conn.commit()
        await message.reply(f"✅ Звание установлено: {esc(title)}")
        return True

    if RM_TITLE.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, title) VALUES (?, ?, '') "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET title = ''",
                (chat_id, user_id)
            )
            await conn.commit()
        await message.reply("✅ Звание удалено.")
        return True

    if SHOW_TITLE.match(stripped):
        mr = await _get_restriction(chat_id, 'show_title')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        rest = stripped[m.end():].strip()
        if rest and rest.lower() != 'удалить':
            target = await extract_user(stripped, message) or await extract_user("@" + rest, message)
            if not target:
                await message.reply("❌ Укажите пользователя.")
                return True
        else:
            target = user_id
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT title FROM profile_chat WHERE chat_id = ? AND user_id = ?",
                (chat_id, target)
            )
            row = await cursor.fetchone()
        tn = await resolve_name(chat_id, target)
        t = row[0] if row and row[0] else "не установлено"
        await message.reply(f"🎖️ <b>Звание {tn}:</b> {esc(t)}")
        return True

    m = ADMIN_SET_TITLE.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'set_title')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        rest = stripped[m.end():]
        parts = rest.rsplit(None, 1)
        if len(parts) == 2:
            target_str = parts[1]
            title = parts[0][:TITLE_MAX]
        else:
            await message.reply("❌ Формат: !Назначить звание {звание} {ссылка}")
            return True
        target = await extract_user(target_str, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, title) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET title = ?",
                (chat_id, target, title, title)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Звание {tname} установлено: {esc(title)}")
        return True

    m = ADMIN_RM_TITLE.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'title_manage')
        ur = await db.get_user_rank(chat_id, user_id) or 0
        if ur < mr or ur < 2:
            await message.reply("❌ Недостаточно прав.")
            return True
        target = await extract_user(stripped, message)
        if not target:
            await message.reply("❌ Укажите пользователя.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, title) VALUES (?, ?, '') "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET title = ''",
                (chat_id, target)
            )
            await conn.commit()
        tname = await resolve_name(chat_id, target)
        await message.reply(f"✅ Звание {tname} удалено.")
        return True

    m = SET_MOTTO.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'motto')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        motto = stripped[m.end():].strip()[:MOTTO_MAX]
        if not motto:
            await message.reply("❌ Укажите девиз.")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, motto) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET motto = ?",
                (user_id, motto, motto)
            )
            await conn.commit()
        await message.reply(f"✅ Девиз установлен: {esc(motto)}")
        return True

    if RM_MOTTO.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, motto) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET motto = ''",
                (user_id,)
            )
            await conn.commit()
        await message.reply("✅ Девиз удалён.")
        return True

    if SHOW_MOTTO.match(stripped):
        mr = await _get_restriction(chat_id, 'motto')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute("SELECT motto FROM profile_global WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        motto = row[0] if row and row[0] else "не установлен"
        await message.reply(f"💬 <b>Ваш девиз:</b> {esc(motto)}")
        return True

    m = MY_BDAY.match(stripped)
    if m:
        normalized = _normalize_bday(m.group(1))
        if normalized is None:
            await message.reply("❌ Неверная дата. Формат: ДД.ММ.ГГГГ (например, 01.01.2000)")
            return True
        bday = normalized
        vis = _normalize_vis(m.group(2) or 'full')
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, birthday, birthday_visibility) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET birthday = ?, birthday_visibility = ?",
                (user_id, bday, vis, bday, vis)
            )
            await conn.commit()
        await message.reply(f"✅ ДР установлен: {bday} (видимость: {vis})")
        return True

    if RM_BDAY.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, birthday) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET birthday = ''",
                (user_id,)
            )
            await conn.commit()
        await message.reply("✅ Дата рождения удалена.")
        return True

    m = MY_CITY.match(stripped)
    if m:
        raw = m.group(1).strip()
        if len(raw) > CITY_MAX:
            await message.reply(f"❌ Город слишком длинный (макс. {CITY_MAX} символов).")
            return True
        found = _resolve_city(raw)
        if not found:
            await message.reply(f"❌ Город «{esc(raw)}» не найден в базе. Проверьте название или напишите город полностью.")
            return True
        city, city_id = found
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, city) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET city = ?",
                (user_id, city, city)
            )
            await conn.commit()
        await message.reply(f"✅ Город установлен: {esc(city)} ({CITIES_BASE_URL.format(city_id)})")
        return True

    if RM_CITY.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, city) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET city = ''",
                (user_id,)
            )
            await conn.commit()
        await message.reply("✅ Город удалён.")
        return True

    m = MY_GENDER.match(stripped)
    if m:
        gender = m.group(1).strip()
        if len(gender) > GENDER_MAX:
            await message.reply(f"❌ Пол слишком длинный (макс. {GENDER_MAX} символов).")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, gender) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET gender = ?",
                (user_id, gender, gender)
            )
            await conn.commit()
        await message.reply(f"✅ Пол установлен: {esc(gender)}")
        return True

    if RM_GENDER.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, gender) VALUES (?, '') "
                "ON CONFLICT(user_id) DO UPDATE SET gender = ''",
                (user_id,)
            )
            await conn.commit()
        await message.reply("✅ Пол удалён.")
        return True

    if TOGGLE_ANKETA.match(stripped):
        visible = stripped.startswith('+')
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, profile_visible) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET profile_visible = ?",
                (chat_id, user_id, int(visible), int(visible))
            )
            await conn.commit()
        await message.reply(f"✅ Анкета {'включена' if visible else 'скрыта'}.")
        return True

    m = ANKETA_CMD.match(stripped)
    if m:
        mr = await _get_restriction(chat_id, 'anketa')
        if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
            return False
        target = None
        if not m.group(1):
            rest = stripped[m.end():].strip()
            if rest:
                target = await extract_user(stripped, message)
        if not target:
            target = user_id
        await _show_card(message, chat_id, target)
        return True

    return False


try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

def _fmt_day(d: int) -> str:
    return f"{d % 100:02d}.{(d // 100) % 100:02d}"


def _make_activity_chart(data: list[tuple[int, int]], days: int = 14) -> bytes | None:
    if not _HAS_MPL or len(data) < 2:
        return None
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch

    days_lbl = [_fmt_day(d) for d, _ in data]
    values = [v for _, v in data]
    max_v = max(values) or 1
    today_idx = len(data) - 1
    width = 0.6
    top = max_v * 1.4 + 1

    fig, ax = plt.subplots(figsize=(max(6.0, days * 0.42), 3.4))
    fig.patch.set_facecolor("#ffffff")

    bg_cmap = LinearSegmentedColormap.from_list("bg", ["#ffffff", "#e6edff"])
    ax.imshow(
        np.linspace(1, 0, 256)[:, None],
        extent=(-0.7, len(values) - 0.3, 0, top),
        aspect="auto", cmap=bg_cmap, zorder=0,
    )

    bar_cmap = LinearSegmentedColormap.from_list("bars", ["#5b8cff", "#9d7bff", "#ff7bd0"])
    for i, v in enumerate(values):
        if v <= 0:
            continue
        color = "#22c55e" if i == today_idx else bar_cmap(v / max_v)
        rounding = min(width * 0.4, max(v * 0.12, 0.04))
        patch = FancyBboxPatch(
            (i - width / 2, 0), width, v,
            boxstyle=f"round,pad=0,rounding_size={rounding}",
            fc=color, ec="white", lw=0.8, zorder=3,
        )
        ax.add_patch(patch)
        ax.text(
            i, v + top * 0.03, str(v),
            ha="center", va="bottom", fontsize=6.5, fontweight="bold",
            color="#334155", zorder=4,
        )

    avg = sum(values) / len(values)
    if avg > 0:
        ax.axhline(avg, color="#94a3b8", linestyle=(0, (4, 3)), linewidth=1, alpha=0.9, zorder=2)
        ax.text(
            len(values) - 0.3, avg + top * 0.05,
            f"среднее {avg:.0f}", fontsize=6.5, color="#64748b", ha="right", va="bottom", zorder=4,
        )

    tick_positions = list(range(len(days_lbl)))
    tick_labels = days_lbl
    if days > 14:
        tick_positions = [i for i in range(len(days_lbl)) if i % 2 == 0]
        tick_labels = [days_lbl[i] for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=7, color="#64748b", rotation=45, ha="right")
    for lab in ax.get_xticklabels():
        if lab.get_text() == days_lbl[today_idx]:
            lab.set_color("#16a34a")
            lab.set_fontweight("bold")

    ax.set_ylim(0, top)
    ax.set_xlim(-0.7, len(values) - 0.3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.tick_params(axis="y", colors="#64748b", labelsize=7)
    ax.yaxis.grid(True, color="#d8e2f8", linewidth=0.8, alpha=0.7, zorder=1)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    plt.subplots_adjust(bottom=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor="#ffffff")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


async def _make_activity_chart_bytes(target_id: int, days: int = 14) -> bytes | None:
    activity = await db.get_daily_activity(target_id, days)
    act = dict(activity or [])
    now_ts = int(time.time())
    days_full = []
    for i in range(days - 1, -1, -1):
        d = int(time.strftime("%Y%m%d", time.localtime(now_ts - i * 86400)))
        days_full.append((d, act.get(d, 0)))
    if sum(v for _, v in days_full) == 0:
        return None
    try:
        return await asyncio.to_thread(_make_activity_chart, days_full, days)
    except Exception as e:
        logger.warning(f"Chart generation failed: {e}")
        return None

def _card_caption(name: str, username: str | None, target_id: int, pgr, last_seen: int, act: tuple, stars: int) -> str:
    if username:
        name_html = f'<a href="https://t.me/{esc(username)}">{esc(name)}</a>'
    else:
        name_html = esc(name)
    seen = _last_seen_str(last_seen)
    lines = [f"👤 Это {name_html}{f' ({seen})' if seen else ''}"]
    lines.append(f"🆔 @{target_id}")
    lines.append("")

    reg = pgr[7] if pgr else 0
    if reg:
        dt = time.strftime("%d.%m.%Y", time.localtime(reg))
        lines.append(f"⏱️ Во вселенной Немесиса: <b>с {dt}</b> ({_duration_str(reg)})")

    gender = pgr[0] if pgr and pgr[0] else "не указан"
    lines.append(f"👨 Пол: {esc(gender)}")

    bday = pgr[2] if pgr else ""
    if bday:
        vis = _normalize_vis(pgr[3] if pgr else "full")
        if vis == "месяц":
            btxt = ".".join(bday.split(".")[1:])
        elif vis == "год":
            btxt = bday.split(".")[-1]
        else:
            btxt = bday
        age = _age_str(bday)
        lines.append(f"📆 Дата рождения: {esc(btxt)} {age}".strip())
    else:
        lines.append("📆 Дата рождения: не указана")

    city = pgr[1] if pgr else ""
    if city:
        cinfo = _CITY_INDEX.get(city.strip().lower())
        if cinfo:
            lines.append(f"🗺 Город: {esc(cinfo['name'])} ({CITIES_BASE_URL.format(cinfo['id'])})")
        else:
            lines.append(f"🗺 Город: {esc(city)}")
    else:
        lines.append("🗺 Город: не указан")

    day, week, month, total = act
    lines.append(f"📊 Активность (день|нед|мес|всего): {_kfmt(day)} | {_kfmt(week)} | {_kfmt(month)} | {_kfmt(total)}")

    emoji, sname = _star_level(stars)
    lines.append(f"✨ Звёздность: [{stars}] {emoji} {sname} ({stars})")

    motto = pgr[5] if pgr else ""
    if motto:
        lines.append(f"🗓 Девиз: {esc(motto)}")
    return "\n".join(lines)


def _card_keyboard(target_id: int, is_own: bool, is_subbed: bool, anketa_visible: bool):
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    if is_own:
        b.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"pr:edit:{target_id}"))
    else:
        label = "➖ Отписаться" if is_subbed else "➕ Подписаться"
        b.row(InlineKeyboardButton(text=label, callback_data=f"pr:subtoggle:{target_id}"))
    b.row(
        InlineKeyboardButton(text="📈 Активность", callback_data=f"pr:actmenu:{target_id}"),
        InlineKeyboardButton(text="🎖️ Награды", callback_data=f"pr:awards:{target_id}"),
    )
    if is_own:
        ank = "🔒 Скрыть анкету" if anketa_visible else "🔓 Показать анкету"
        b.row(
            InlineKeyboardButton(text="👥 Подписки", callback_data=f"pr:subs:{target_id}"),
            InlineKeyboardButton(text=ank, callback_data=f"pr:anketa:{target_id}"),
        )
    b.row(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"pr:refresh:{target_id}"))
    return b.as_markup()


async def _show_card(message: Message, chat_id: int, target_id: int, viewer_id: int | None = None):
    viewer_id = viewer_id or (message.from_user.id if message.from_user else target_id)
    is_pm = message.chat.type == "private"
    is_own = target_id == viewer_id

    async with aiosqlite.connect(db.db_path) as conn:
        pc = await conn.execute(
            "SELECT nickname, title, citizenship, profile_visible FROM profile_chat WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        )
        pcr = await pc.fetchone()
        pg = await conn.execute(
            "SELECT gender, city, birthday, birthday_visibility, description, motto, achievements_visible, registered_at FROM profile_global WHERE user_id = ?",
            (target_id,)
        )
        pgr = await pg.fetchone()
        rep = await conn.execute(
            "SELECT rating, stars FROM rep_rating WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        )
        repr_ = await rep.fetchone()
        subsc = await conn.execute(
            "SELECT COUNT(*) FROM profile_subscriptions WHERE target_id = ?",
            (target_id,)
        )
        subs = (await subsc.fetchone())[0]
        mq = await conn.execute(
            "SELECT COALESCE(SUM(msg_count), 0) FROM user_last_message WHERE user_id = ?",
            (target_id,)
        )
        mcnt = (await mq.fetchone())[0]
        sb = await conn.execute(
            "SELECT 1 FROM profile_subscriptions WHERE subscriber_id = ? AND target_id = ?",
            (viewer_id, target_id)
        )
        is_subbed = bool(await sb.fetchone())
        ls = await conn.execute(
            "SELECT MAX(last_msg_at) FROM user_last_message WHERE user_id = ?",
            (target_id,)
        )
        last_seen = (await ls.fetchone())[0]
        ad = await conn.execute(
            "SELECT day, msg_count FROM activity_daily WHERE user_id = ?",
            (target_id,)
        )
        activity_rows = await ad.fetchall()

    if pcr and not pcr[3] and not is_own:
        await message.reply("🔒 Пользователь скрыл свою анкету.")
        return

    if is_pm:
        name = message.from_user.first_name or "Пользователь"
        username = message.from_user.username
    else:
        name = await resolve_name(chat_id, target_id)
        username = None
        try:
            cm = await bot.get_chat_member(chat_id, target_id)
            if cm and cm.user:
                username = cm.user.username
        except Exception as e:
            logger.warning(f"Username fetch failed: {e}")

    today = int(time.strftime("%Y%m%d"))
    day = sum(v for d, v in activity_rows if d == today)
    week = sum(v for d, v in activity_rows if today - 7 < d <= today)
    month = sum(v for d, v in activity_rows if today - 30 < d <= today)
    stars = repr_[1] if repr_ else 0
    act = (day, week, month, mcnt)

    text = _card_caption(name, username, target_id, pgr, last_seen, act, stars)
    anketa_visible = not (pcr and not pcr[3])
    kb = _card_keyboard(target_id, is_own, is_subbed, anketa_visible)

    chart_bytes = await _make_activity_chart_bytes(target_id, 14)
    if chart_bytes:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(chart_bytes)
        tmp.close()
        try:
            await message.reply_photo(FSInputFile(tmp.name), caption=text, reply_markup=kb)
            return
        except Exception as e:
            logger.warning(f"Chart photo failed: {e}")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    try:
        photos = await bot.get_user_profile_photos(target_id, limit=1)
        if photos.photos:
            file_id = photos.photos[0][-1].file_id
            await message.reply_photo(file_id, caption=text, reply_markup=kb)
            return
    except Exception as e:
        logger.warning(f"Avatar fetch failed: {e}")

    await message.reply(text, reply_markup=kb)


async def send_activity_chart(message: Message, target_id: int, days: int = 14):
    activity = await db.get_daily_activity(target_id, days)
    act = dict(activity or [])
    days_full = []
    for i in range(days - 1, -1, -1):
        d = int(time.strftime("%Y%m%d", time.localtime(time.time() - i * 86400)))
        days_full.append((d, act.get(d, 0)))

    total = sum(v for _, v in days_full)
    best_day, best_val = max(days_full, key=lambda x: x[1])

    if total == 0:
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(msg_count), 0) FROM user_last_message WHERE user_id = ?",
                (target_id,)
            )
            all_total = (await cursor.fetchone())[0]
        extra = f"\nВсего сообщений за всё время: {all_total}" if all_total else ""
        await message.answer(f"📈 За последние {days} дн. сообщений не было.{extra}")
        return

    try:
        chart_bytes = await asyncio.to_thread(_make_activity_chart, days_full, days)
        if not chart_bytes:
            await message.answer("📈 Не удалось построить график.")
            return
        avg = round(total / days, 1)
        caption = (
            f"📈 <b>Активность за {days} дн.</b>\n"
            f"Всего: {total} · в среднем {avg}/день\n"
            f"Лучший день: {_fmt_day(best_day)} ({best_val})"
        )
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(chart_bytes)
        tmp.close()
        try:
            await message.answer_photo(FSInputFile(tmp.name), caption=caption)
        finally:
            os.unlink(tmp.name)
    except Exception as e:
        logger.warning(f"Chart generation failed: {e}")
        await message.answer("📈 Не удалось построить график.")


async def _handle_pm_commands(message: Message, chat_id: int, user_id: int, text: str) -> bool:
    stripped = text.strip().lower()
    if stripped in ("профиль", "анкета", "!роль", "кто я", "хто я", "моя анкета"):
        await _show_card(message, chat_id, user_id)
        return True
    return False
