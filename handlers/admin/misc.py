import re
import time

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

from bot import bot, logger
from db import db
from utils import esc, format_duration
from utils.time_parser import parse_time
from utils.mentions import extract_user
from utils.user_name import resolve_name
from .common import RANK_NAMES, check_rank, get_min_rank, get_reason, call_plugin_hooks

router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('+триггер') or msg.text.strip().lower().startswith('!триггер')))
async def add_trigger_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, 3):
        await message.reply("❌ Недостаточно прав для управления триггерами.")
        return
    parts = text.split()
    if len(parts) < 3:
        await message.reply("❌ Формат: +Триггер <тип> <действие> [время]\nТипы: спам, ссылки, мат, инвайт, капс, флуд, custom")
        return
    ttype_map = {
        'спам': 'spam', 'ссылки': 'links', 'мат': 'mute', 'инвайт': 'invite',
        'упоминания': 'mention', 'капс': 'caps', 'флуд': 'flood', 'custom': 'custom',
    }
    ttype = ttype_map.get(parts[1].lower(), parts[1].lower())
    action = parts[2].lower()
    if action not in ('warn', 'mute', 'ban', 'kick', 'delete'):
        await message.reply("❌ Действие должно быть: warn, mute, ban, kick, delete")
        return
    duration = None
    if len(parts) > 3:
        dur_str = parts[3]
        if dur_str not in ('warn', 'mute', 'ban', 'kick', 'delete'):
            duration = parse_time(dur_str)
    await db.add_trigger(chat_id, ttype, action, duration)
    await message.reply(f"✅ Триггер добавлен: {ttype} → {action}")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('-триггер'))
async def remove_trigger_handler(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, 3):
        await message.reply("❌ Недостаточно прав.")
        return
    parts = text.split()
    if len(parts) < 2:
        await message.reply("❌ Укажите тип триггера.")
        return
    ttype_map = {
        'спам': 'spam', 'ссылки': 'links', 'мат': 'mute', 'инвайт': 'invite',
        'упоминания': 'mention', 'капс': 'caps', 'флуд': 'flood', 'custom': 'custom',
    }
    ttype = ttype_map.get(parts[1].lower(), parts[1].lower())
    await db.remove_trigger(chat_id, ttype)
    await message.reply(f"✅ Триггер {ttype} удалён.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and ((msg.text.strip().split()[0].lower() if msg.text.strip().split() else '') == 'триггеры' or msg.text.strip().lower().startswith('!triggers')))
async def list_triggers_handler(message: Message):
    chat_id = message.chat.id
    triggers = await db.get_triggers(chat_id)
    if not triggers:
        await message.reply("Нет активных триггеров.")
        return
    lines = ["⚡ <b>Триггеры:</b>\n"]
    for tt, act, dur, ct, rr in triggers:
        dur_str = f" {format_duration(dur)}" if dur else ""
        lines.append(f"• {tt} → {act}{dur_str}")
    await message.reply("\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('+завещание') or msg.text.strip().lower().startswith('+наследство')))
async def add_inheritance_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)
    if not await check_rank(chat_id, user_id, 3):
        await message.reply("❌ Недостаточно прав.")
        return
    if not target_id:
        await message.reply("❌ Укажите наследника (ответом или @username).")
        return
    await db.add_inheritance(chat_id, user_id, target_id)
    tname = await resolve_name(chat_id, target_id)
    await message.reply(f"✅ Завещание оставлено на пользователя {tname}.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('моё завещание') or msg.text.strip().lower().startswith('мое завещание')))
async def my_inheritance_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    inh = await db.get_inheritance(chat_id, user_id)
    if inh:
        hname = await resolve_name(chat_id, inh[0])
        ts = time.strftime("%d.%m.%Y", time.localtime(inh[1]))
        await message.reply(f"📜 Ваше завещание: {hname} (от {ts})")
    else:
        await message.reply("У вас нет завещания.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('-завещание'))
async def remove_inheritance_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await db.remove_inheritance(chat_id, user_id)
    await message.reply("✅ Завещание аннулировано.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('вступить в наследство'))
async def claim_inheritance_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)
    if not target_id:
        await message.reply("❌ Укажите пользователя, от которого вступаете в наследство.")
        return
    inh = await db.get_inheritance(chat_id, target_id)
    if not inh or inh[0] != user_id:
        await message.reply("❌ Вы не указаны как наследник этого пользователя.")
        return
    trank = await db.get_user_rank(chat_id, target_id)
    await db.set_user_rank(chat_id, user_id, trank, target_id)
    await db.remove_inheritance(chat_id, target_id)
    await db.remove_moderator(chat_id, target_id)
    await db.add_moderator_log(chat_id, user_id, "promote", user_id, f"наследство ранг {trank}")
    await message.reply(f"✅ Вы вступили в наследство. Ваш ранг: {RANK_NAMES.get(trank, trank)}.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('!передать создателя'))
async def transfer_creator_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await extract_user(text, message)
    if not await check_rank(chat_id, user_id, 5):
        await message.reply("❌ Только создатель может передать права.")
        return
    if not target_id:
        await message.reply("❌ Укажите пользователя.")
        return
    try:
        cm = await bot.get_chat_member(chat_id, user_id)
        if cm.status != ChatMemberStatus.CREATOR:
            await message.reply("❌ Вы не являетесь создателем чата.")
            return
    except Exception:
        await message.reply("❌ Не удалось проверить статус.")
        return
    await db.set_user_rank(chat_id, target_id, 5, user_id)
    await db.set_user_rank(chat_id, user_id, 4, user_id)
    tname = await resolve_name(chat_id, target_id)
    await message.reply(f"✅ Права создателя переданы {tname}.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('восстановить создателя'))
async def restore_creator_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        me = await bot.get_chat_member(chat_id, user_id)
        if me.status == ChatMemberStatus.CREATOR:
            await db.set_user_rank(chat_id, user_id, 5, user_id)
            await message.reply("✅ Вы восстановлены как создатель.")
            return
    except Exception:
        pass
    inh = await db.get_inheritance(chat_id, user_id)
    if inh and inh[0]:
        await message.reply("❌ Вы не создатель чата. Указанный в завещании наследник может вступить в наследство.")
    else:
        await message.reply("❌ Вы не создатель чата.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('+мой онлайн') or msg.text.strip().lower().startswith('!мой онлайн') or msg.text.strip().lower().startswith('+online')))
async def online_on_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await db.set_online_status(chat_id, user_id, True)
    await message.reply("✅ Ваш онлайн включён.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('-мой онлайн') or msg.text.strip().lower().startswith('-online')))
async def online_off_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await db.set_online_status(chat_id, user_id, False)
    await message.reply("✅ Ваш онлайн выключен.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('+модер теги') or msg.text.strip().lower().startswith('!модер теги')))
async def tags_on_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, 5):
        await message.reply("❌ Только создатель может изменить эту настройку.")
        return
    settings = await db.get_settings(chat_id)
    settings["show_moderator_tags"] = True
    await db.save_settings(chat_id, settings)
    await message.reply("✅ Отображение тегов включено.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and msg.text.strip().lower().startswith('-модер теги'))
async def tags_off_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await check_rank(chat_id, user_id, 5):
        await message.reply("❌ Только создатель может изменить эту настройку.")
        return
    settings = await db.get_settings(chat_id)
    settings["show_moderator_tags"] = False
    await db.save_settings(chat_id, settings)
    await message.reply("✅ Отображение тегов выключено.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: msg.text and (msg.text.strip().lower().startswith('дк') or msg.text.strip().lower().startswith('!dk')))
async def command_restriction_handler(message: Message):
    if await call_plugin_hooks(message):
        return
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = text.split()
    if len(parts) < 3:
        await message.reply("❌ Формат: дк <команда> <ранг>\nПример: дк бан 3")
        return
    cmd_type_map = {
        'выдача варнов': 'warn', 'варн': 'warn', 'warn': 'warn',
        'снятие варнов': 'unwarn', 'разварн': 'unwarn',
        'выдача мута': 'mute', 'мут': 'mute', 'mute': 'mute',
        'снятие мута': 'unmute', 'размут': 'unmute',
        'выдача бана': 'ban', 'бан': 'ban', 'ban': 'ban',
        'снятие бана': 'unban', 'разбан': 'unban',
        'кик': 'kick', 'kick': 'kick',
        'амнистия': 'amnesty', 'банлист': 'banlist',
        'кто админ': 'admin_list', 'вызов админов': 'admin_call',
        'повышение': 'promote', 'понижение': 'demote',
    }
    cmd_key = ' '.join(parts[1:-1]).lower()
    cmd_type = cmd_type_map.get(cmd_key, parts[1].lower())
    try:
        min_rank = int(parts[-1])
    except ValueError:
        await message.reply("❌ Ранг должен быть числом (0-5).")
        return
    if min_rank < 0 or min_rank > 5:
        await message.reply("❌ Ранг от 0 до 5.")
        return
    await db.set_command_restriction(chat_id, cmd_type, min_rank)
    await message.reply(f"✅ Для команды {cmd_type} установлен минимальный ранг {min_rank}.")
