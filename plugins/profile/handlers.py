import asyncio
import io
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
        city = m.group(1).strip()
        if len(city) > CITY_MAX:
            await message.reply(f"❌ Город слишком длинный (макс. {CITY_MAX} символов).")
            return True
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, city) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET city = ?",
                (user_id, city, city)
            )
            await conn.commit()
        await message.reply(f"✅ Город установлен: {esc(city)}")
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

_CHART_BG = "#1a1a2e"
_CHART_TEXT = "#e0e0e0"
_CHART_BAR = "#e94560"
_CHART_BAR_DIM = "#3a3a5e"


def _fmt_day(d: int) -> str:
    return f"{d % 100:02d}.{(d // 100) % 100:02d}"


def _interp(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return (
        f"#{int(r1 + (r2 - r1) * t):02x}"
        f"{int(g1 + (g2 - g1) * t):02x}"
        f"{int(b1 + (b2 - b1) * t):02x}"
    )


def _make_activity_chart(data: list[tuple[int, int]], days: int = 14) -> bytes | None:
    if not _HAS_MPL or len(data) < 2:
        return None
    days_lbl = [_fmt_day(d) for d, _ in data]
    values = [v for _, v in data]
    max_v = max(values) or 1
    today_idx = len(data) - 1

    colors = [
        _CHART_BAR if i == today_idx else _interp(_CHART_BAR_DIM, _CHART_BAR, values[i] / max_v)
        for i in range(len(values))
    ]

    fig, ax = plt.subplots(figsize=(max(6.0, days * 0.42), 3.6))
    fig.patch.set_facecolor(_CHART_BG)
    ax.set_facecolor(_CHART_BG)
    ax.bar(range(len(values)), values, color=colors, width=0.65, edgecolor="none")

    avg = sum(values) / len(values)
    if avg > 0:
        ax.axhline(avg, color=_CHART_TEXT, linestyle="--", linewidth=1, alpha=0.5)
        ax.text(
            len(values) - 0.3, avg + max_v * 0.02,
            f"среднее: {avg:.1f}", fontsize=7, color=_CHART_TEXT, va="bottom", ha="right"
        )

    tick_positions = list(range(len(days_lbl)))
    tick_labels = days_lbl
    if days > 14:
        tick_positions = [i for i in range(len(days_lbl)) if i % 2 == 0]
        tick_labels = [days_lbl[i] for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=7, color=_CHART_TEXT, rotation=45, ha="right")

    for i, v in enumerate(values):
        if v > 0:
            ax.text(i, v + max_v * 0.02, str(v), fontsize=6, color=_CHART_TEXT, ha="center", va="bottom")

    ax.set_ylabel("Сообщений", fontsize=7, color=_CHART_TEXT)
    ax.tick_params(axis="y", colors=_CHART_TEXT, labelsize=7)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.yaxis.grid(True, alpha=0.15, color=_CHART_TEXT)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.6, len(values) - 0.4)
    for spine in ax.spines.values():
        spine.set_visible(False)
    plt.subplots_adjust(bottom=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

def _bar(value: int, max_val: int = 100, size: int = 10) -> str:
    filled = min(int(value / max(max_val, 1) * size), size)
    return "█" * filled + "░" * (size - filled)

def _card_caption(name: str, target_id: int, pcr, pgr, repr_, subs: int, warns: int, awards: int, mcnt: int) -> str:
    lines = [f"👤 <b>{name}</b>  <code>{target_id}</code>"]

    if pcr:
        info = []
        if pcr[0]:
            info.append(f"📛 {esc(pcr[0])}")
        if pcr[1]:
            info.append(f"🎖️ {esc(pcr[1])}")
        if pcr[2]:
            info.append("🏡 Гражданин")
        if info:
            lines.append(" | ".join(info))

    if pgr:
        info2 = []
        if pgr[0]:
            info2.append(f"⚤ {esc(pgr[0])}")
        if pgr[1]:
            info2.append(f"🏙️ {esc(pgr[1])}")
        bday_raw = pgr[2]
        bday_vis = _normalize_vis(pgr[3])
        if bday_raw:
            if bday_vis == 'full':
                info2.append(f"🎂 {bday_raw}")
            elif bday_vis == 'месяц':
                info2.append(f"🎂 {'.'.join(bday_raw.split('.')[1:])}")
            elif bday_vis == 'год':
                info2.append(f"🎂 {bday_raw.split('.')[-1]}")
        if info2:
            lines.append(" | ".join(info2))
        descr = pgr[4]
        if descr:
            lines.append(f"📝 {esc(descr[:300])}{'…' if len(descr) > 300 else ''}")
        motto = pgr[5]
        if motto:
            lines.append(f"💬 «{esc(motto)}»")
        reg = pgr[7]
        if reg:
            dt = time.strftime("%d.%m.%Y", time.localtime(reg))
            delta = int(time.time()) - reg
            months = delta // (86400 * 30)
            days = (delta % (86400 * 30)) // 86400
            dur = f"{months} мес {days} дн" if months else f"{days} дн"
            lines.append(f"⏱️ Во вселенной Немесис: <b>с {dt}</b> ({dur})")

    rating = repr_[0] if repr_ else 0
    stars = repr_[1] if repr_ else 0
    lines.append("📊 <b>Статистика</b>")
    lines.append(f"⭐ Рейтинг: {rating}  {_bar(rating, max(rating, 100))}")
    lines.append(f"🌟 Звёзды: {stars}  {_bar(stars, max(stars, 20))}")
    tail = f"👥 Подписчики: {subs}  |  ⚠️ Варны: {warns}  |  🎖️ Награды: {awards}"
    tail += f"  |  💬 Сообщений: {mcnt}"
    lines.append(tail)
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
        wc = await conn.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ? AND is_active = 1",
            (chat_id, target_id)
        )
        warns = (await wc.fetchone())[0]
        ac = await conn.execute(
            "SELECT COUNT(*) FROM awards_medals WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        )
        awards = (await ac.fetchone())[0]
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

    if pcr and not pcr[3] and not is_own:
        await message.reply("🔒 Пользователь скрыл свою анкету.")
        return

    if is_pm:
        name = esc(message.from_user.first_name or "Пользователь")
    else:
        name = await resolve_name(chat_id, target_id)

    text = _card_caption(name, target_id, pcr, pgr, repr_, subs, warns, awards, mcnt)
    anketa_visible = not (pcr and not pcr[3])
    kb = _card_keyboard(target_id, is_own, is_subbed, anketa_visible)

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
