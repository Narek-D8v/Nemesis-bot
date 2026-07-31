import asyncio
import html
import json
import re
import time

import aiosqlite
from aiogram.types import Message, ChatPermissions, ChatJoinRequest, MessageEntity
from aiogram.enums import ChatMemberStatus, MessageEntityType

from bot import bot, logger
from db import db
from utils import esc
from utils.mentions import extract_user

MAX_RULES_LENGTH = 3000

JOIN_LEAVE_RE = re.compile(
    r'^[+-]?(входы|выходы|входы-выходы|входывыходы)\b', re.IGNORECASE
)
AUTOKICK_RE = re.compile(r'^[+-]?автокик\b', re.IGNORECASE)
AUTOKICK_SILENT_RE = re.compile(
    r'^[+-]?автокик\s+молчунов\b', re.IGNORECASE
)
CHAT_TOGGLE_RE = re.compile(r'^[+-]?чат\b', re.IGNORECASE)
TOPIC_TOGGLE_RE = re.compile(r'^[+-]?топик\b', re.IGNORECASE)
TGADMIN_RE = re.compile(r'^[+-]?тг\s+админ\b', re.IGNORECASE)
TGRIGHTS_RE = re.compile(r'^тг\s+права\b', re.IGNORECASE)
TAG_RE = re.compile(r'^[+-]?тг\s+тег\b', re.IGNORECASE)
CHANNELS_RE = re.compile(r'^[+-]?каналы\b', re.IGNORECASE)
MINREG_RE = re.compile(r'^[+-]?минрег\b', re.IGNORECASE)
AUTOJOIN_RE = re.compile(r'^[+-]?автозаявки\b', re.IGNORECASE)
RULES_RE = re.compile(r'^[+-]?правила\b', re.IGNORECASE)
GREETING_RE = re.compile(r'^[+-]?приветствие\b', re.IGNORECASE)
CHECK_CHAT_RE = re.compile(r'^проверить\s+в\s+чате\b', re.IGNORECASE)

ADMIN_CMDS = (
    JOIN_LEAVE_RE, AUTOKICK_RE, AUTOKICK_SILENT_RE,
    CHAT_TOGGLE_RE, TOPIC_TOGGLE_RE, TGADMIN_RE,
    TGRIGHTS_RE, TAG_RE, CHANNELS_RE, MINREG_RE,
    AUTOJOIN_RE, RULES_RE, GREETING_RE, CHECK_CHAT_RE,
)

PERMS_ALLOW = ChatPermissions(
    can_send_messages=True, can_send_media_messages=True,
    can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_change_info=False,
    can_invite_users=True, can_pin_messages=False,
)

PERMS_DENY = ChatPermissions(
    can_send_messages=False, can_send_media_messages=False,
    can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False, can_change_info=False,
    can_invite_users=False, can_pin_messages=False,
)

USER_REQUIRED_MSG = "❌ Укажите пользователя (ссылка, @username или ответ)"


async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


def _utf16_len(s: str) -> int:
    return len(s.encode('utf-16-le')) // 2


def _extract_content(text: str, cmd_lower: str) -> tuple[str | None, int | None]:
    cmd_len = len(cmd_lower)
    lower_idx = text.lower().find(cmd_lower)
    if lower_idx == -1:
        return None, None
    after = text[lower_idx + cmd_len:]
    content = after.lstrip()
    if not content:
        return None, None
    content_start = lower_idx + cmd_len + (len(after) - len(content))
    return content, content_start


def _adjust_entities_json(message: Message, content: str, content_start: int, full_text: str | None = None) -> str:
    entities = message.entities or message.caption_entities or []
    cs_u = _utf16_len(full_text[:content_start]) if full_text else content_start
    end_u = cs_u + _utf16_len(content)
    result = []
    for e in entities:
        if e.offset >= cs_u and e.offset + e.length <= end_u:
            d = {
                "type": str(e.type),
                "offset": e.offset - cs_u,
                "length": e.length,
            }
            if str(e.type) == "text_link" and hasattr(e, "url") and e.url:
                d["url"] = e.url
            elif str(e.type) == "text_mention" and hasattr(e, "user") and e.user:
                d["type"] = "text_link"
                d["url"] = f"tg://user?id={e.user.id}"
            result.append(d)
    return json.dumps(result, ensure_ascii=False)


def _entities_from_json(data: list[dict]) -> list[MessageEntity]:
    entities = []
    for d in data:
        try:
            etype = d["type"]
            kwargs = {
                "type": etype,
                "offset": d["offset"],
                "length": d["length"],
            }
            if "url" in d:
                kwargs["url"] = d["url"]
            entities.append(MessageEntity(**kwargs))
        except Exception:
            pass
    return entities


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
    elif GREETING_RE.match(stripped):
        await _handle_greeting(message, chat_id, user_id, text)
    elif AUTOKICK_SILENT_RE.match(stripped):
        await _handle_autokick_silent(message, chat_id, user_id, text)
    elif AUTOKICK_RE.match(stripped):
        await _handle_autokick(message, chat_id, user_id, text, settings)
    elif CHAT_TOGGLE_RE.match(stripped):
        await _handle_chat_toggle(message, chat_id, user_id, text)
    elif TOPIC_TOGGLE_RE.match(stripped):
        await _handle_topic_toggle(message, chat_id, user_id, text)
    elif TGADMIN_RE.match(stripped):
        await _handle_tgadmin(message, chat_id, user_id, text)
    elif TGRIGHTS_RE.match(stripped):
        await _handle_tgrights(message, chat_id, user_id, text)
    elif TAG_RE.match(stripped):
        await _handle_tag(message, chat_id, user_id, text)
    elif CHANNELS_RE.match(stripped):
        await _handle_channels(message, chat_id, user_id, text, settings)
    elif JOIN_LEAVE_RE.match(stripped):
        await _handle_join_leave(message, chat_id, user_id, text, settings)
    elif MINREG_RE.match(stripped):
        await _handle_minreg(message, chat_id, user_id, text, settings)
    elif AUTOJOIN_RE.match(stripped):
        await _handle_autojoin(message, chat_id, user_id, text)
    elif CHECK_CHAT_RE.match(stripped):
        await _handle_check_chat(message, chat_id)
    return True


async def _handle_rules(message: Message, chat_id: int, user_id: int, text: str):
    stripped = text.strip()
    is_enable = stripped.startswith("+")
    is_disable = stripped.startswith("-")
    if is_enable:
        content, content_start = _extract_content(text, "+правила")
        if content is None:
            content, content_start = _extract_content(text, "правила")
        if content is None:
            await message.reply("❌ Укажите текст правил после команды.")
            return
        if len(content) > MAX_RULES_LENGTH:
            await message.reply(
                f"❌ Текст слишком длинный! Максимум {MAX_RULES_LENGTH} символов.\n"
                f"Сейчас {len(content)} символов. Пожалуйста, сократите."
            )
            return
        entities_json = _adjust_entities_json(message, content, content_start, text)
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO group_rules (chat_id, text, entities_json) VALUES (?, ?, ?)",
                (chat_id, content, entities_json)
            )
            await conn.commit()
        settings = await db.get_settings(chat_id)
        settings.setdefault("daily_rules", {})["text"] = content
        settings.setdefault("daily_rules", {})["entities_json"] = entities_json
        settings.setdefault("daily_rules", {})["enabled"] = True
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Правила установлены!")
        logger.info(f"Rules set in {chat_id} by {user_id}")
    elif is_disable:
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO group_rules (chat_id, text, entities_json) VALUES (?, '', '')",
                (chat_id, '', '')
            )
            await conn.commit()
        settings = await db.get_settings(chat_id)
        settings.setdefault("daily_rules", {})["enabled"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Правила удалены.")
    else:
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT text, entities_json FROM group_rules WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
        rules_text = row[0] if row and row[0] else None
        entities_json = row[1] if row and len(row) > 1 else ""
        if not rules_text:
            settings = await db.get_settings(chat_id)
            dr = settings.get("daily_rules", {})
            rules_text = dr.get("text")
            if not rules_text:
                await message.reply("📜 Правила не установлены.")
                return
            entities_json = ""
        prefix = "📜 Правила чата:\n\n"
        full_text = prefix + rules_text
        pu = _utf16_len(prefix)
        entities = []
        if entities_json:
            try:
                for e in json.loads(entities_json):
                    kwargs = dict(
                        type=e["type"],
                        offset=e["offset"] + pu,
                        length=e["length"],
                    )
                    if "url" in e:
                        kwargs["url"] = e["url"]
                    entities.append(MessageEntity(**kwargs))
            except Exception:
                entities = []
        await message.reply(full_text, entities=entities or None, parse_mode=None)


async def _handle_greeting(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    is_enable = cmd_text.startswith("+")
    is_disable = cmd_text.startswith("-")
    settings = await db.get_settings(chat_id)
    if is_enable:
        content, content_start = _extract_content(text, "+приветствие")
        if content is None:
            content, content_start = _extract_content(text, "приветствие")
        if content is None:
            await message.reply("❌ Укажите текст приветствия после команды.")
            return
        if len(content) > MAX_RULES_LENGTH:
            await message.reply(
                f"❌ Текст слишком длинный! Максимум {MAX_RULES_LENGTH} символов.\n"
                f"Сейчас {len(content)} символов. Пожалуйста, сократите."
            )
            return
        entities_json = _adjust_entities_json(message, content, content_start, text)
        settings.setdefault("greeting", {})["text"] = content
        settings["greeting"]["entities_json"] = entities_json
        settings["greeting"]["enabled"] = True
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Приветствие установлено!")
        logger.info(f"Greeting set in {chat_id} by {user_id}")
    elif is_disable:
        settings["greeting"]["enabled"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Приветствие выключено.")
    else:
        g = settings.get("greeting", {})
        if g.get("text"):
            raw_text = g["text"]
            entities_json = g.get("entities_json", "")
            prefix = "👋 Текущее приветствие:\n"
            full_text = prefix + raw_text
            pu = _utf16_len(prefix)
            entities = []
            if entities_json:
                try:
                    for e in json.loads(entities_json):
                        kwargs = dict(
                            type=e["type"],
                            offset=e["offset"] + pu,
                            length=e["length"],
                        )
                        if "url" in e:
                            kwargs["url"] = e["url"]
                        entities.append(MessageEntity(**kwargs))
                except Exception:
                    entities = []
            await message.reply(full_text, entities=entities or None, parse_mode=None)
        else:
            await message.reply("👋 Приветствие не установлено.")


async def _handle_autokick(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip()
    is_enable = cmd_text.startswith("+")
    is_disable = cmd_text.startswith("-")
    if is_enable:
        parts = cmd_text.split()[1:]
        if len(parts) >= 3:
            try:
                count = int(parts[0])
                minutes = int(parts[1])
                action = parts[2].lower()
                if action not in ("kick", "кик", "ban", "бан"):
                    await message.reply("❌ Действие: кик или бан")
                    return
                action = "ban" if action in ("ban", "бан") else "kick"
            except ValueError:
                await message.reply(
                    "❌ Использование: +Автокик {число} {минуты} {кик/бан}"
                )
                return
            settings["autokick_on_exit"] = True
            settings["autokick_exit_count"] = count
            settings["autokick_exit_time"] = minutes
            settings["autokick_exit_action"] = action
            settings["autokick_action"] = action
            await db.save_settings(chat_id, settings)
            await message.reply(
                f"✅ Автокик: {count} выходов за {minutes} мин -> {action}"
            )
        else:
            settings["autokick_on_exit"] = True
            settings["autokick_exit_count"] = 3
            settings["autokick_exit_time"] = 60
            settings["autokick_exit_action"] = "kick"
            settings["autokick_action"] = "kick"
            await db.save_settings(chat_id, settings)
            await message.reply(
                "✅ Автокик включён (3 выхода за 60 мин -> кик)"
            )
        logger.info(f"Autokick set in {chat_id} by {user_id}")
    elif is_disable:
        settings["autokick_on_exit"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Автокик выключен.")


async def _handle_autokick_silent(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    if cmd_text.startswith("+"):
        parts = cmd_text.split()
        if len(parts) < 3:
            await message.reply(
                "❌ Укажите количество дней. Пример: +Автокик молчунов 7"
            )
            return
        try:
            days = int(parts[-1])
        except ValueError:
            await message.reply(
                "❌ Укажите количество дней. Пример: +Автокик молчунов 7"
            )
            return
        settings = await db.get_settings(chat_id)
        settings["autokick_silent_days"] = days
        await db.save_settings(chat_id, settings)
        await message.reply(
            f"✅ Автокик молчунов включён: {days} дней без сообщений -> кик"
        )
        logger.info(f"Autokick silent set {days}d in {chat_id} by {user_id}")
    elif cmd_text.startswith("-"):
        settings = await db.get_settings(chat_id)
        settings.pop("autokick_silent_days", None)
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Автокик молчунов выключен.")


async def _handle_chat_toggle(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    try:
        if cmd_text.startswith("-"):
            await bot.set_chat_permissions(chat_id, PERMS_DENY)
            await message.reply("✅ Чат закрыт. Писать могут только администраторы.")
            logger.info(f"Chat closed in {chat_id} by {user_id}")
        elif cmd_text.startswith("+"):
            await bot.set_chat_permissions(chat_id, PERMS_ALLOW)
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
        if cmd_text.startswith("-"):
            await bot.close_forum_topic(chat_id, message.message_thread_id)
            await message.reply("✅ Топик закрыт.")
        elif cmd_text.startswith("+"):
            await bot.reopen_forum_topic(chat_id, message.message_thread_id)
            await message.reply("✅ Топик открыт.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")
        logger.warning(f"Topic toggle failed in {chat_id}: {e}")


async def _handle_tgadmin(message: Message, chat_id: int, user_id: int, text: str):
    cmd_text = text.strip()
    target_id = await extract_user(cmd_text, message)
    if not target_id:
        await message.reply(USER_REQUIRED_MSG)
        return
    try:
        if cmd_text.startswith("+"):
            title_match = re.search(r'\[([^\]]+)\]', cmd_text)
            title = html.escape(title_match.group(1)) if title_match else "Администратор"
            await bot.promote_chat_member(
                chat_id, target_id,
                can_delete_messages=True,
                can_restrict_members=True,
                can_invite_users=True,
                can_pin_messages=True,
                can_promote_members=False,
            )
            first_name = esc(message.from_user.first_name)
            await message.reply(
                f"✅ {first_name}, пользователь назначен администратором "
                f"с должностью «{title}»."
            )
            logger.info(f"Promoted {target_id} to admin in {chat_id} by {user_id}")
        elif cmd_text.startswith("-"):
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
        await message.reply(USER_REQUIRED_MSG)
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
        await message.reply(USER_REQUIRED_MSG)
        return
    if cmd_text.startswith("+"):
        prefix_match = re.match(r'[+-]?тг тег\s+', cmd_text, re.IGNORECASE)
        if not prefix_match:
            await message.reply(
                "❌ Укажите текст тега. Пример: +Тг тег Модератор @username"
            )
            return
        tag_text = cmd_text[prefix_match.end():]
        tag_text = re.sub(r'\s+@\S+$', '', tag_text).strip()
        tag_text = re.sub(r'\s+id[=:]\d+$', '', tag_text).strip()
        if not tag_text:
            await message.reply(
                "❌ Укажите текст тега. Пример: +Тг тег Модератор @username"
            )
            return
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
    elif cmd_text.startswith("-"):
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM group_tags WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_id)
            )
            await conn.commit()
        await message.reply("✅ Тег удалён.")


async def _handle_channels(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip()
    if cmd_text.startswith("+"):
        settings["block_channels"] = False
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Сообщения от каналов разрешены.")
    elif cmd_text.startswith("-"):
        settings["block_channels"] = True
        await db.save_settings(chat_id, settings)
        await message.reply("✅ Сообщения от каналов заблокированы.")


async def _handle_join_leave(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip().lower()
    is_enable = cmd_text.startswith("+")
    is_disable = cmd_text.startswith("-")
    is_both = bool(re.search(r'вход[ы]?[-]?выход[ы]?', cmd_text))
    is_join = bool(re.search(r'\bвход[ы]?\b', cmd_text)) and not is_both
    is_leave = bool(re.search(r'\bвыход[ы]?\b', cmd_text)) and not is_both
    if is_both and (is_enable or is_disable):
        settings["show_join_leave"] = True
        settings["show_join"] = is_enable
        settings["show_leave"] = is_enable
        await db.save_settings(chat_id, settings)
        status = "включены" if is_enable else "выключены"
        await message.reply(f"✅ Уведомления о входах/выходах {status}.")
    elif is_join and (is_enable or is_disable):
        settings["show_join"] = is_enable
        await db.save_settings(chat_id, settings)
        status = "включены" if is_enable else "выключены"
        await message.reply(f"✅ Уведомления о входах {status}.")
    elif is_leave and (is_enable or is_disable):
        parts = cmd_text.split()
        threshold = None
        if len(parts) >= 2 and parts[-1].isdigit():
            threshold = int(parts[-1])
        settings["show_leave"] = is_enable
        if threshold is not None:
            settings["leave_threshold"] = threshold
            await message.reply(
                f"✅ Уведомления о выходах включены (порог: {threshold} сообщений)."
            )
        else:
            status = "включены" if is_enable else "выключены"
            await message.reply(f"✅ Уведомления о выходах {status}.")
        await db.save_settings(chat_id, settings)
    else:
        s = settings.get("show_join_leave", True)
        j = settings.get("show_join", True)
        lv = settings.get("show_leave", True)
        lt = settings.get("leave_threshold", 0)
        await message.reply(
            f"📊 Входы: {'✅' if j else '❌'}, Выходы: {'✅' if lv else '❌'}"
            f"{f' (порог: {lt})' if lt else ''}"
        )


async def _handle_minreg(message: Message, chat_id: int, user_id: int, text: str, settings: dict):
    cmd_text = text.strip().lower()
    if cmd_text.startswith("+"):
        parts = cmd_text.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            days = int(parts[-1])
            settings["min_account_age_days"] = days
            await db.save_settings(chat_id, settings)
            await message.reply(f"✅ Минимальная регистрация: {days} дней.")
        else:
            await message.reply("❌ Укажите количество дней. Пример: +Минрег 7")
    elif cmd_text.startswith("-"):
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
        if cmd_text.startswith("+"):
            await conn.execute(
                "INSERT OR REPLACE INTO auto_join_requests (chat_id, enabled) VALUES (?, 1)",
                (chat_id,)
            )
            await conn.commit()
            await message.reply("✅ Автозаявки включены.")
            logger.info(f"Auto-join enabled in {chat_id} by {user_id}")
        elif cmd_text.startswith("-"):
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
        await message.reply(USER_REQUIRED_MSG)
        return
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        status = member.status
        if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.reply(
                f"✅ Пользователь {esc(member.user.full_name)} присутствует в чате."
            )
        else:
            await message.reply(
                f"❌ Пользователь отсутствует в чате (статус: {status})."
            )
    except Exception:
        await message.reply("❌ Пользователь не найден в чате.")


async def on_chat_join_request(event: ChatJoinRequest):
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


async def _autokick_silent_loop():
    while True:
        try:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT chat_id FROM group_settings "
                    "WHERE json_extract(config, '$.autokick_silent_days') IS NOT NULL"
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
                    async with aiosqlite.connect(db.db_path) as conn2:
                        async with conn2.execute(
                            "SELECT DISTINCT user_id FROM user_last_message "
                            "WHERE chat_id = ? AND last_msg_at > ?",
                            (chat_id, cutoff)
                        ) as c:
                            active = {row[0] for row in await c.fetchall()}
                        async with conn2.execute(
                            "SELECT user_id FROM user_last_message "
                            "WHERE chat_id = ? AND last_msg_at < ?",
                            (chat_id, cutoff)
                        ) as c:
                            all_users = [row[0] for row in await c.fetchall()]
                    silent = [
                        uid for uid in all_users
                        if uid not in admin_ids and uid not in active
                    ]
                    for uid in silent[:20]:
                        try:
                            await bot.ban_chat_member(chat_id, uid)
                            await bot.unban_chat_member(chat_id, uid)
                        except Exception:
                            pass
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(
                        f"Autokick silent check failed for {chat_id}: {e}"
                    )
        except Exception as e:
            logger.warning(f"Autokick silent loop error: {e}")
        await asyncio.sleep(3600)