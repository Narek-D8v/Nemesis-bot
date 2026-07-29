import asyncio
import re
import time

import aiosqlite
from aiogram.types import Message, ChatPermissions, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus

from bot import bot, logger
from db import db
from utils import esc
from utils.mentions import extract_user, cache_user_from_member

JOIN_LEAVE_RE = re.compile(
    r'^[+-]?(входы|выходы|входы-выходы|входывыходы)\b',
    re.IGNORECASE
)
AUTOKICK_RE = re.compile(
    r'^[+-]?автокик\b',
    re.IGNORECASE
)
AUTOKICK_SILENT_RE = re.compile(
    r'^[+-]?автокик\s+молчунов\b',
    re.IGNORECASE
)
CHAT_TOGGLE_RE = re.compile(
    r'^[+-]?чат\b',
    re.IGNORECASE
)
TOPIC_TOGGLE_RE = re.compile(
    r'^[+-]?топик\b',
    re.IGNORECASE
)
TGADMIN_RE = re.compile(
    r'^[+-]?тг\s+админ\b',
    re.IGNORECASE
)
TGRIGHTS_RE = re.compile(
    r'^тг\s+права\b',
    re.IGNORECASE
)
TAG_RE = re.compile(
    r'^[+-]?тг\s+тег\b',
    re.IGNORECASE
)
CHANNELS_RE = re.compile(
    r'^[+-]?каналы\b',
    re.IGNORECASE
)
MINREG_RE = re.compile(
    r'^[+-]?минрег\b',
    re.IGNORECASE
)
AUTOJOIN_RE = re.compile(
    r'^[+-]?автозаявки\b',
    re.IGNORECASE
)
RULES_RE = re.compile(
    r'^[+-]?правила\b',
    re.IGNORECASE
)
GREETING_RE = re.compile(
    r'^[+-]?приветствие\b',
    re.IGNORECASE
)
CHECK_CHAT_RE = re.compile(
    r'^проверить\s+в\s+чате\b',
    re.IGNORECASE
)

ADMIN_CMDS = (
    JOIN_LEAVE_RE, AUTOKICK_RE, AUTOKICK_SILENT_RE,
    CHAT_TOGGLE_RE, TOPIC_TOGGLE_RE, TGADMIN_RE,
    TGRIGHTS_RE, TAG_RE, CHANNELS_RE, MINREG_RE,
    AUTOJOIN_RE, RULES_RE, GREETING_RE,
)


async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


def _fmt_text(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = text.split("\n")
    out = []
    in_block = False
    for line in lines:
        if line.startswith("&gt; "):
            if not in_block:
                out.append("<blockquote>")
                in_block = True
            out.append(line[5:])
        else:
            if in_block:
                out.append("</blockquote>")
                in_block = False
            out.append(line)
    if in_block:
        out.append("</blockquote>")
    return "<br>".join(out)


async def handle_group_command(
    message: Message, chat_id: int, user_id: int, text: str, settings: dict
) -> bool:
    stripped = text.strip().lower()
    if not any(pat.match(stripped) for pat in ADMIN_CMDS):
        return False

    if not await is_admin(chat_id, user_id):
        return False

    if RULES_RE.match(stripped):
        await _handle_rules(message, chat_id, user_id, text)
        return True
    if GREETING_RE.match(stripped):
        await _handle_greeting(message, chat_id, user_id, text)
        return True
    if AUTOKICK_SILENT_RE.match(stripped):
        await _handle_autokick_silent(message, chat_id, user_id, text)
        return True
    if AUTOKICK_RE.match(stripped):
        await _handle_autokick(message, chat_id, user_id, text, settings)
        return True
    if CHAT_TOGGLE_RE.match(stripped):
        await _handle_chat_toggle(message, chat_id, user_id, text)
        return True
    if TOPIC_TOGGLE_RE.match(stripped):
        await _handle_topic_toggle(message, chat_id, user_id, text)
        return True
    if TGADMIN_RE.match(stripped):
        await _handle_tgadmin(message, chat_id, user_id, text)
        return True
    if TGRIGHTS_RE.match(stripped):
        await _handle_tgrights(message, chat_id, user_id, text)
        return True
    if TAG_RE.match(stripped):
        await _handle_tag(message, chat_id, user_id, text)
        return True
    if CHANNELS_RE.match(stripped):
        await _handle_channels(message, chat_id, user_id, text, settings)
        return True
    if JOIN_LEAVE_RE.match(stripped):
        await _handle_join_leave(message, chat_id, user_id, text, settings)
        return True
    if MINREG_RE.match(stripped):
        await _handle_minreg(message, chat_id, user_id, text, settings)
        return True
    if AUTOJOIN_RE.match(stripped):
        await _handle_autojoin(message, chat_id, user_id, text)
        return True
    if CHECK_CHAT_RE.match(stripped):
        await _handle_check_chat(message, chat_id)
        return True
    return False


async def _handle_rules(message: Message, chat_id: int, user_id: int, text: str):
    cmd = text.strip()
    if cmd.startswith("+Правила") or cmd.startswith("+правила"):
        rules_text = cmd[len("+правила"):].strip() if cmd.startswith("+правила") else cmd[len("+Правила"):].strip()
        if rules_text.startswith("\n"):
            rules_text = rules_text[1:]
        if not rules_text:
            await message.reply("❌ Укажите текст правил после команды.")
            return
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO group_rules (chat_id, text) VALUES (?, ?)",
                (chat_id, rules_text)
            )
            await conn.commit()
        await message.reply("✅ Правила установлены!")
        logger.info(f"Rules set in {chat_id} by {user_id}")
    elif cmd.startswith("-Правила") or cmd.startswith("-правила"):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO group_rules (chat_id, text) VALUES (?, '')",
                (chat_id,)
            )
            await conn.commit()
        await message.reply("✅ Правила удалены.")
    else:
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT text FROM group_rules WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
        if row and row[0]:
            await message.reply(f"📜 Правила чата:\n\n{_fmt_text(row[0])}")
        else:
            await message.reply("📜 Правила не установлены.")


async def _handle_greeting(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    if cmd_text.startswith("+Приветствие") or cmd_text.startswith("+приветствие"):
        greeting_text = cmd_text[len("+приветствие"):].strip() if cmd_text.startswith("+приветствие") else cmd_text[len("+Приветствие"):].strip()
        if greeting_text.startswith("\n"):
            greeting_text = greeting_text[1:]
        if not greeting_text:
            await message.reply("❌ Укажите текст приветствия после команды.")
            return
        settings = await db.get_settings(chat_id)
        settings.setdefault("greeting", {})["text"] = greeting_text
        settings["greeting"]["enabled"] = True
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Приветствие установлено!")
        logger.info(f"Greeting set in {chat_id} by {user_id}")
    elif cmd_text.startswith("-Приветствие") or cmd_text.startswith("-приветствие"):
        settings = await db.get_settings(chat_id)
        settings["greeting"]["enabled"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Приветствие выключено.")
    else:
        g = settings.get("greeting", {})
        if g.get("text"):
            await message.reply(f"👋 Текущее приветствие:\n{_fmt_text(g['text'])}")
        else:
            await message.reply("👋 Приветствие не установлено.")


async def _handle_autokick(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip()
    if cmd_text.startswith("+Автокик") or cmd_text.startswith("+автокик"):
        parts = cmd_text.split()[1:]
        if len(parts) >= 3:
            try:
                count = int(parts[0])
                minutes = int(parts[1])
                action = parts[2].lower()
                if action not in ("kick", "кик", "ban", "бан"):
                    await message.reply("❌ Действие: кик или бан")
                    return
                if action in ("ban", "бан"):
                    action = "ban"
                else:
                    action = "kick"
            except ValueError:
                await message.reply("❌ Использование: +Автокик {число} {минуты} {кик/бан}")
                return
            settings["autokick_on_exit"] = True
            settings["autokick_exit_count"] = count
            settings["autokick_exit_time"] = minutes
            settings["autokick_action"] = action
            await db.save_settings(chat_id, settings)
            await message.reply(f"✅ Автокик: {count} выходов за {minutes} мин -> {action}")
        else:
            settings["autokick_on_exit"] = True
            settings["autokick_exit_count"] = 3
            settings["autokick_exit_time"] = 60
            settings["autokick_action"] = "kick"
            await db.save_settings(chat_id, settings)
            await message.reply("✅ Автокик включён (3 выхода за 60 мин -> кик)")
        logger.info(f"Autokick set in {chat_id} by {user_id}")
    elif cmd_text.startswith("-Автокик") or cmd_text.startswith("-автокик"):
        settings["autokick_on_exit"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Автокик выключен.")


async def _handle_autokick_silent(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    if cmd_text.startswith("+Автокик молчунов") or cmd_text.startswith("+автокик молчунов"):
        parts = cmd_text.split()
        if len(parts) >= 3:
            try:
                days = int(parts[-1])
            except ValueError:
                await message.reply("❌ Укажите количество дней. Пример: +Автокик молчунов 7")
                return
        else:
            await message.reply("❌ Укажите количество дней. Пример: +Автокик молчунов 7")
            return
        settings = await db.get_settings(chat_id)
        settings["autokick_silent_days"] = days
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Автокик молчунов включён: {days} дней без сообщений -> кик")
        logger.info(f"Autokick silent set {days}d in {chat_id} by {user_id}")
    elif cmd_text.startswith("-Автокик молчунов") or cmd_text.startswith("-автокик молчунов"):
        settings = await db.get_settings(chat_id)
        settings.pop("autokick_silent_days", None)
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Автокик молчунов выключен.")


async def _handle_chat_toggle(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    try:
        if cmd_text.startswith("-Чат") or cmd_text.startswith("-чат"):
            await bot.set_chat_permissions(
                chat_id,
                ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                )
            )
            await message.reply("✅ Чат закрыт. Писать могут только администраторы.")
            logger.info(f"Chat closed in {chat_id} by {user_id}")
        elif cmd_text.startswith("+Чат") or cmd_text.startswith("+чат"):
            await bot.set_chat_permissions(
                chat_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=False,
                    can_invite_users=True,
                    can_pin_messages=False,
                )
            )
            await message.reply("✅ Чат открыт. Участники могут писать.")
            logger.info(f"Chat opened in {chat_id} by {user_id}")
        else:
            await message.reply("Использование: +Чат (открыть) / -Чат (закрыть)")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        logger.warning(f"Chat toggle failed in {chat_id}: {e}")


async def _handle_topic_toggle(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    if not message.is_topic_message:
        await message.reply("❌ Это не топик.")
        return
    try:
        if cmd_text.startswith("-Топик") or cmd_text.startswith("-топик"):
            await bot.restrict_chat_member(
                chat_id, message.message_thread_id,
                ChatPermissions(can_send_messages=False),
                until_date=0
            )
            await message.reply("✅ Топик закрыт.")
        elif cmd_text.startswith("+Топик") or cmd_text.startswith("+топик"):
            await bot.restrict_chat_member(
                chat_id, message.message_thread_id,
                ChatPermissions(can_send_messages=True),
                until_date=0
            )
            await message.reply("✅ Топик открыт.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        logger.warning(f"Topic toggle failed in {chat_id}: {e}")


async def _handle_tgadmin(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    target_id = await extract_user(cmd_text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя (ссылка, @username или ответ на сообщение)")
        return
    try:
        if cmd_text.startswith("+Тг админ") or cmd_text.startswith("+тг админ"):
            title_match = re.search(r'\[([^\]]+)\]', cmd_text)
            title = title_match.group(1) if title_match else "Администратор"
            await bot.promote_chat_member(
                chat_id, target_id,
                can_delete_messages=True,
                can_restrict_members=True,
                can_invite_users=True,
                can_pin_messages=True,
                can_promote_members=False,
            )
            await message.reply(f"✅ {esc(message.from_user.first_name)}, пользователь назначен администратором с должностью «{title}».")
            logger.info(f"Promoted {target_id} to admin in {chat_id} by {user_id}")
        elif cmd_text.startswith("-Тг админ") or cmd_text.startswith("-тг админ"):
            await bot.promote_chat_member(
                chat_id, target_id,
                can_delete_messages=False,
                can_restrict_members=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_promote_members=False,
                is_anonymous=False,
            )
            await message.reply("✅ Права администратора сняты.")
            logger.info(f"Demoted {target_id} in {chat_id} by {user_id}")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        logger.warning(f"TG admin cmd failed in {chat_id}: {e}")


async def _handle_tgrights(message: Message, chat_id: int, user_id: int, text: str):
    target_id = await extract_user(text.strip(), message)
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.reply("❌ Пользователь не является администратором.")
            return
        rights = member
        txt = (
            f"👤 Права {esc(member.user.full_name)}:\n"
            f"Удаление сообщений: {'✅' if rights.can_delete_messages else '❌'}\n"
            f"Блокировка: {'✅' if rights.can_restrict_members else '❌'}\n"
            f"Приглашение: {'✅' if rights.can_invite_users else '❌'}\n"
            f"Закрепление: {'✅' if rights.can_pin_messages else '❌'}\n"
            f"Назначение админов: {'✅' if rights.can_promote_members else '❌'}"
        )
        await message.reply(txt)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


async def _handle_tag(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    target_id = await extract_user(cmd_text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя (ссылка, @username или ответ)")
        return
    if cmd_text.startswith("+Тг тег") or cmd_text.startswith("+тг тег"):
        tag_match = re.search(r'\+тг тег\s+(.+?)(?:\s|$)', cmd_text, re.IGNORECASE)
        if not tag_match:
            await message.reply("❌ Укажите текст тега. Пример: +Тг тег Модератор @username")
            return
        tag_text = tag_match.group(1).strip()
        tag_text = re.sub(r'\s+@\S+$', '', tag_text).strip()
        tag_text = re.sub(r'\s+id[=:]\d+$', '', tag_text).strip()
        if len(tag_text) > 16:
            await message.reply("❌ Тег слишком длинный (макс. 16 символов).")
            return
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO group_tags (chat_id, user_id, tag) VALUES (?, ?, ?)",
                (chat_id, target_id, tag_text)
            )
            await conn.commit()
        await message.reply(f"✅ Тег «{esc(tag_text)}» установлен для пользователя.")
    elif cmd_text.startswith("-Тг тег") or cmd_text.startswith("-тг тег"):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM group_tags WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_id)
            )
            await conn.commit()
        await message.reply("✅ Тег удалён.")


async def _handle_channels(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip()
    if cmd_text.startswith("+Каналы") or cmd_text.startswith("+каналы"):
        settings["block_channels"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Сообщения от каналов разрешены.")
    elif cmd_text.startswith("-Каналы") or cmd_text.startswith("-каналы"):
        settings["block_channels"] = True
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Сообщения от каналов заблокированы.")


async def _handle_join_leave(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip().lower()
    is_join = "вход" in cmd_text
    is_leave = "выход" in cmd_text
    is_enable = not cmd_text.startswith("-")
    if is_join and is_leave:
        settings["show_join_leave"] = True
        settings["show_join"] = is_enable
        settings["show_leave"] = is_enable
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Уведомления о входах/выходах {'включены' if is_enable else 'выключены'}.")
    elif is_join:
        settings["show_join"] = is_enable
        await db.save_settings(chat_id, settings)
        await message.reply(f"✅ Уведомления о входах {'включены' if is_enable else 'выключены'}.")
    elif is_leave:
        parts = cmd_text.split()
        threshold = None
        if len(parts) >= 2 and parts[-1].isdigit():
            threshold = int(parts[-1])
        settings["show_leave"] = True if is_enable else False
        if threshold is not None:
            settings["leave_threshold"] = threshold
            await message.reply(f"✅ Уведомления о выходах включены (порог: {threshold} сообщений).")
        else:
            await message.reply(f"✅ Уведомления о выходах {'включены' if is_enable else 'выключены'}.")
        await db.save_settings(chat_id, settings)


async def _handle_minreg(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip().lower()
    if cmd_text.startswith("+минрег"):
        parts = cmd_text.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            days = int(parts[-1])
            settings["min_account_age_days"] = days
            await db.save_settings(chat_id, settings)
            await message.reply(f"✅ Минимальная регистрация: {days} дней.")
        else:
            await message.reply("❌ Укажите количество дней. Пример: +Минрег 7")
    elif cmd_text.startswith("-минрег"):
        settings["min_account_age_days"] = 0
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Минимальная регистрация отключена.")
    else:
        days = settings.get("min_account_age_days", 0)
        if days > 0:
            await message.reply(f"📊 Минимальная регистрация: {days} дней.")
        else:
            await message.reply("📊 Минимальная регистрация не установлена.")


async def _handle_autojoin(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip().lower()
    async with aiosqlite.connect(db.db_path) as conn:
        if cmd_text.startswith("+автозаявки"):
            await conn.execute(
                "INSERT OR REPLACE INTO auto_join_requests (chat_id, enabled) VALUES (?, 1)",
                (chat_id,)
            )
            await conn.commit()
            await message.reply("✅ Автозаявки включены.")
            logger.info(f"Auto-join enabled in {chat_id} by {user_id}")
        elif cmd_text.startswith("-автозаявки"):
            await conn.execute(
                "INSERT OR REPLACE INTO auto_join_requests (chat_id, enabled) VALUES (?, 0)",
                (chat_id,)
            )
            await conn.commit()
            await message.reply("✅ Автозаявки выключены.")
        else:
            cursor = await conn.execute(
                "SELECT enabled FROM auto_join_requests WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            status = "включены" if row and row[0] else "выключены"
            await message.reply(f"📊 Автозаявки: {status}")


async def _handle_check_chat(message: Message, chat_id: int):
    target_id = await extract_user(message.text.strip(), message)
    if not target_id:
        await message.reply("❌ Укажите пользователя (ссылка, @username или ответ)")
        return
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.reply(f"✅ Пользователь {esc(member.user.full_name)} присутствует в чате.")
        else:
            await message.reply(f"❌ Пользователь отсутствует в чате (статус: {member.status}).")
    except Exception:
        await message.reply("❌ Пользователь не найден в чате.")


async def on_chat_join_request(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user_id = event.from_user.id
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT enabled FROM auto_join_requests WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                await bot.approve_chat_join_request(chat_id, user_id)
            except Exception as e:
                logger.warning(f"Auto-join approve failed: {e}")


async def on_user_join(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user = event.new_chat_member.user
    await cache_user_from_member(chat_id, user.id, user.username)
    settings = await db.get_settings(chat_id)

    now = int(time.time())
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO user_first_seen (user_id, first_seen_at) VALUES (?, ?)",
            (user.id, now)
        )
        await conn.commit()

    minreg = settings.get("min_account_age_days", 0)
    if minreg > 0:
        cursor = await conn.execute(
            "SELECT first_seen_at FROM user_first_seen WHERE user_id = ?", (user.id,)
        )
        row = await cursor.fetchone()
        if row:
            first_seen = row[0]
            if first_seen > 0 and (now - first_seen) < minreg * 86400:
                try:
                    await bot.ban_chat_member(chat_id, user.id)
                    await bot.unban_chat_member(chat_id, user.id)
                except Exception:
                    pass
                try:
                    await bot.send_message(
                        chat_id,
                        f"⛔ Пользователь {esc(user.full_name)} кикнут (меньше {minreg} дней в боте)."
                    )
                except Exception:
                    pass
                return


async def on_user_leave(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user = event.old_chat_member.user
    settings = await db.get_settings(chat_id)

    if settings.get("autokick_on_exit", False):
        await db.add_exit_event(chat_id, user.id)
        exit_data = await db.get_exit_count(chat_id, user.id)
        if exit_data:
            count, last = exit_data
            max_count = settings.get("autokick_exit_count", 3)
            max_time = settings.get("autokick_exit_time", 60)
            action = settings.get("autokick_action", "kick")
            if count >= max_count and (time.time() - last) <= max_time * 60:
                if action == "ban":
                    try:
                        await bot.ban_chat_member(chat_id, user.id)
                        await bot.send_message(chat_id, f"⛔ {esc(user.full_name)} забанен (автокик)")
                    except Exception:
                        pass
                else:
                    try:
                        await bot.ban_chat_member(chat_id, user.id)
                        await bot.unban_chat_member(chat_id, user.id)
                        await bot.send_message(chat_id, f"👋 {esc(user.full_name)} кикнут (автокик)")
                    except Exception:
                        pass

    if settings.get("show_join_leave", True) and settings.get("show_leave", False):
        leave_threshold = settings.get("leave_threshold", 0)
        if leave_threshold > 0:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT msg_count FROM user_last_message WHERE chat_id = ? AND user_id = ?",
                    (chat_id, user.id)
                )
                row = await cursor.fetchone()
                msg_count = row[0] if row else 0
            if msg_count < leave_threshold:
                return
        try:
            await bot.send_message(chat_id, f"👋 {esc(user.full_name)} покинул(а) чат.")
        except Exception:
            pass


async def _autokick_silent_loop():
    while True:
        try:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT chat_id FROM group_settings WHERE json_extract(config, '$.autokick_silent_days') IS NOT NULL"
                )
                rows = await cursor.fetchall()
            for (chat_id,) in rows:
                try:
                    settings = await db.get_settings(chat_id)
                    days = settings.get("autokick_silent_days")
                    if not days:
                        continue
                    cutoff = int(time.time()) - days * 86400
                    admins = await bot.get_chat_administrators(chat_id)
                    admin_ids = {a.user.id for a in admins}
                    async with conn.execute(
                        "SELECT DISTINCT user_id FROM activity_daily WHERE user_id NOT IN (SELECT user_id FROM user_first_seen WHERE first_seen_at > ?)",
                        (cutoff,)
                    ) as c:
                        active = {row[0] for row in await c.fetchall()}
                    async with conn.execute(
                        "SELECT user_id FROM user_last_message WHERE chat_id = ? AND last_msg_at < ?",
                        (chat_id, cutoff)
                    ) as c:
                        silent = [row[0] for row in await c.fetchall() if row[0] not in admin_ids and row[0] not in active]
                    for uid in silent[:20]:
                        try:
                            await bot.ban_chat_member(chat_id, uid)
                            await bot.unban_chat_member(chat_id, uid)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Autokick silent check failed for {chat_id}: {e}")
        except Exception as e:
            logger.warning(f"Autokick silent loop error: {e}")
        await asyncio.sleep(3600)
