import re
import time

import aiosqlite
from aiogram.types import Message

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
    'дк гражданство': 'citizenship', 'дк кто добавил': 'who_added',
    'дк рег': 'reg', 'дк ид': 'id_cmd', 'дк девиз': 'motto',
}

NICK_MAX = 30
TITLE_MAX = 30
MOTTO_MAX = 100
DESCR_MAX = 3800
MAX_SUBS = 50
VIP_CALL_LIMIT = 120
NONVIP_CALL_LIMIT = 20


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
        await message.reply(f"✅ Ачивки {'открыты' if visible else 'скрыты'} для просмотра.")
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
                await message.reply("🔒 Пользователь скрыл свои ачивки.")
                return True
            cursor = await conn.execute(
                "SELECT title, description, unlocked_at FROM profile_achievements WHERE user_id = ? ORDER BY unlocked_at DESC LIMIT 20",
                (target,)
            )
            rows = await cursor.fetchall()
        tn = await resolve_name(chat_id, target)
        if not rows:
            await message.reply(f"У {tn} пока нет ачивок.")
            return True
        lines = [f"🏆 <b>Ачивки {tn}:</b>\n"]
        for title, desc, ts in rows:
            d = time.strftime("%d.%m.%Y", time.localtime(ts))
            lines.append(f"• <b>{esc(title)}</b> — {esc(desc)} ({d})")
        await message.reply("\n".join(lines))
        return True

    if MY_ACHIEVES.match(stripped):
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM profile_achievements WHERE user_id = ?",
                (user_id,)
            )
            total = (await cursor.fetchone())[0]
            cursor = await conn.execute(
                "SELECT title, description, unlocked_at FROM profile_achievements WHERE user_id = ? ORDER BY unlocked_at DESC LIMIT 20",
                (user_id,)
            )
            rows = await cursor.fetchall()
        nm = esc(message.from_user.first_name or "Пользователь")
        if not rows:
            await message.reply(f"У вас пока нет ачивок. Всего: {total}")
            return True
        lines = [f"🏆 <b>Ачивки {nm}:</b> ({total} всего)\n"]
        for title, desc, ts in rows:
            d = time.strftime("%d.%m.%Y", time.localtime(ts))
            lines.append(f"• <b>{esc(title)}</b> — {esc(desc)} ({d})")
        await message.reply("\n".join(lines))
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
                "SELECT COUNT(*) FROM profile_achievements WHERE user_id = ?",
                (user_id,)
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
            f"🏆 Ачивки: {achievements}"
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
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute("SELECT motto FROM profile_global WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        motto = row[0] if row and row[0] else "не установлен"
        await message.reply(f"💬 <b>Ваш девиз:</b> {esc(motto)}")
        return True

    m = MY_BDAY.match(stripped)
    if m:
        bday = m.group(1)
        vis = m.group(2) or 'full'
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


async def _show_card(message: Message, chat_id: int, target_id: int):
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

    if pcr and not pcr[3]:
        await message.reply("🔒 Пользователь скрыл свою анкету.")
        return

    name = await resolve_name(chat_id, target_id)

    lines = [f"👤 <b>{name}</b>"]
    if pcr:
        if pcr[0]:
            lines.append(f"📛 Ник: {esc(pcr[0])}")
        if pcr[1]:
            lines.append(f"🎖️ Звание: {esc(pcr[1])}")
        if pcr[2]:
            lines.append("🏡 Гражданин чата")
    if pgr:
        gender = pgr[0]
        city = pgr[1]
        bday_raw = pgr[2]
        bday_vis = pgr[3]
        motto = pgr[5]
        reg = pgr[7]
        if gender:
            lines.append(f"⚤ Пол: {esc(gender)}")
        if city:
            lines.append(f"🏙️ Город: {esc(city)}")
        if bday_raw:
            if bday_vis == 'full':
                lines.append(f"🎂 ДР: {bday_raw}")
            elif bday_vis == 'месяц' or bday_vis == 'месяц':
                lines.append(f"🎂 ДР: {'.'.join(bday_raw.split('.')[1:])}")
            elif bday_vis == 'год':
                lines.append(f"🎂 ДР: {bday_raw.split('.')[-1]}")
        if motto:
            lines.append(f"💬 Девиз: {esc(motto)}")
        if reg:
            dt = time.strftime("%d.%m.%Y", time.localtime(reg))
            lines.append(f"📅 Регистрация: {dt}")
    if repr_:
        lines.append(f"⭐ Рейтинг: {repr_[0]} | 🌟 {repr_[1]}")
    if subs:
        lines.append(f"👥 Подписчики: {subs}")

    await message.reply("\n".join(lines))


async def _handle_pm_commands(message: Message, chat_id: int, user_id: int, text: str) -> bool:
    stripped = text.strip().lower()
    if stripped in ("профиль", "анкета", "!роль", "кто я", "хто я", "моя анкета"):
        async with aiosqlite.connect(db.db_path) as conn:
            pg = await conn.execute(
                "SELECT gender, city, birthday, birthday_visibility, motto, registered_at FROM profile_global WHERE user_id = ?",
                (user_id,)
            )
            pgr = await pg.fetchone()
        name = esc(message.from_user.first_name or "Пользователь")
        lines = [f"👤 <b>{name}</b>"]
        if pgr:
            if pgr[0]:
                lines.append(f"⚤ Пол: {esc(pgr[0])}")
            if pgr[1]:
                lines.append(f"🏙️ Город: {esc(pgr[1])}")
            if pgr[2]:
                vis = pgr[3] or 'full'
                bday = pgr[2]
                if vis == 'full':
                    lines.append(f"🎂 ДР: {bday}")
                elif vis in ('месяц',):
                    lines.append(f"🎂 ДР: {'.'.join(bday.split('.')[1:])}")
                elif vis == 'год':
                    lines.append(f"🎂 ДР: {bday.split('.')[-1]}")
            if pgr[4]:
                lines.append(f"💬 Девиз: {esc(pgr[4])}")
            if pgr[5]:
                dt = time.strftime("%d.%m.%Y", time.localtime(pgr[5]))
                lines.append(f"📅 Регистрация: {dt}")
        else:
            lines.append("Анкета не заполнена.")
        await message.reply("\n".join(lines))
        return True
    return False
