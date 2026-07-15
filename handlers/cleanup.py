import re
import time
import asyncio

from aiogram import Router, F
from aiogram.types import Message

from bot import bot
from db import db
from utils import esc
from utils.time_parser import parse_time
from utils.mentions import extract_user
from utils.chat_utils import delete_messages, get_messages_above, get_messages_below, kick_user
from utils.user_name import resolve_name

router = Router()

CLEANUP_PATTERNS = [
    r'^-смс\b',
    r'^!пург\b',
    r'^кик\b',
    r'^кто\s+удалён\b',
    r'^кто\s+собака\b',
]


def is_cleanup_cmd(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    for p in CLEANUP_PATTERNS:
        if re.match(p, t, re.IGNORECASE):
            return True
    return False


def get_reason(text: str) -> str:
    parts = text.split('\n', 1)
    return parts[1].strip() if len(parts) > 1 else ""


async def check_rank(chat_id: int, user_id: int, required_rank: int) -> bool:
    if required_rank == 0:
        return True
    rank = await db.get_user_rank(chat_id, user_id)
    return rank >= required_rank


async def get_min_rank(chat_id: int, cmd_type: str) -> int:
    return await db.get_command_restriction(chat_id, cmd_type)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, lambda msg: is_cleanup_cmd(msg.text))
async def cleanup_handler(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await db.get_settings(chat_id)
    show_tags = settings.get("show_moderator_tags", True)
    first_word = text.split()[0].lower() if text.split() else ""

    # ---- MESSAGE DELETION ----
    if text.lower().startswith('-смс') or text.lower().startswith('!смс'):
        min_rank = await get_min_rank(chat_id, "cleanup_messages")
        if not await check_rank(chat_id, user_id, min_rank):
            await message.reply("❌ Недостаточно прав.")
            return

        silent = 'тихо' in text.lower()
        parts = text.split()
        if len(parts) >= 2 and parts[1].lstrip('-').isdigit():
            count = int(parts[1])
            if not message.reply_to_message:
                await message.reply("❌ Ответьте на сообщение, относительно которого удалять.")
                return
            from_id = message.reply_to_message.message_id
            try:
                await message.delete()
            except Exception:
                pass
            msg_ids = await get_messages_above(chat_id, from_id, count)
            deleted = await delete_messages(chat_id, msg_ids, silent)
            if not silent:
                resp = f"🗑 Удалено сообщений: {deleted}"
                if show_tags:
                    resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
                await message.answer(resp)
        else:
            if message.reply_to_message:
                try:
                    await message.delete()
                    await message.reply_to_message.delete()
                    if not silent:
                        resp = f"🗑 Сообщение удалено."
                        if show_tags:
                            resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
                        await message.answer(resp)
                except Exception as e:
                    await message.answer("❌ Не удалось удалить сообщение.")
            else:
                await message.reply("❌ Ответьте на сообщение для удаления.")
        return

    if text.lower().startswith('!пург') or text.lower().startswith('!purge'):
        min_rank = await get_min_rank(chat_id, "purge")
        if not await check_rank(chat_id, user_id, min_rank):
            await message.reply("❌ Недостаточно прав.")
            return
        if not message.reply_to_message:
            await message.reply("❌ Ответьте на сообщение, ниже которого удалять.")
            return
        silent = 'тихо' in text.lower()
        parts = text.split()
        limit = None
        if len(parts) >= 2 and parts[1].isdigit():
            limit = int(parts[1])
        is_premium = await db.is_premium_group(chat_id)
        batch_limit = 1000 if is_premium else 100
        if limit and limit > batch_limit:
            limit = batch_limit
        from_id = message.reply_to_message.message_id
        try:
            await message.delete()
        except Exception:
            pass
        msg_ids = await get_messages_below(chat_id, from_id, limit)
        deleted = await delete_messages(chat_id, msg_ids, silent)
        if not silent:
            resp = f"🗑 Очищено сообщений: {deleted}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.answer(resp)
        return

    # ---- KICK COMMANDS ----
    if re.match(r'^кик\b', text, re.IGNORECASE) or first_word == 'кик':
        rest = text[3:].strip() if text.lower().startswith('кик') else ""
        rest_lower = rest.lower()

        # Kick specific user
        target_id = await extract_user(text, message)
        if not rest_lower.startswith(('неактив', 'актив', 'нов', 'удалён', 'молч', 'по', 'собак')):
            if not target_id:
                await message.reply("❌ Укажите пользователя (ответом или @username).")
                return
            min_rank = await get_min_rank(chat_id, "kick")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав для кика.")
                return
            reason = get_reason(text) or "Кик"
            await db.add_kick(chat_id, target_id, user_id, reason)
            await db.add_moderator_log(chat_id, user_id, "kick", target_id, reason)
            if await kick_user(chat_id, target_id):
                tname = await resolve_name(chat_id, target_id)
                resp = f"👢 Пользователь {tname} кикнут."
                if show_tags:
                    resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
                await message.reply(resp)
            else:
                await message.reply("❌ Не удалось кикнуть (возможно, админ).")
            return

        # ---- KICK INACTIVE ----
        if rest_lower.startswith('неактив') or rest_lower.startswith('inactive'):
            min_rank = await get_min_rank(chat_id, "kick_inactive")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            silent = 'тихо' in rest_lower
            parts = rest.split()
            days = 30
            limit = None
            for p in parts:
                pd = parse_time(p)
                if pd:
                    minutes = pd
                    if minutes < 1440:
                        await message.reply("❌ Минимальный период: 24 часа (1д).")
                        return
                    days = max(1, minutes // 1440)
                    break
            for p in parts:
                if p.lstrip('-').isdigit():
                    limit = int(p)
                    break

            cutoff = int(time.time()) - days * 86400
            lurkers = await db.get_lurkers(chat_id, cutoff, limit)
            kicked = 0
            for lurker_id, last_msg_at in lurkers:
                if await kick_user(chat_id, lurker_id, "Неактивность"):
                    kicked += 1
                    await db.add_kick(chat_id, lurker_id, user_id, f"Неактив {days}д", silent)
                    await asyncio.sleep(0.3)
            resp = f"👢 Исключено неактивных: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        # ---- KICK ACTIVE ----
        if rest_lower.startswith('актив') or rest_lower.startswith('active'):
            min_rank = await get_min_rank(chat_id, "kick_active")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            minutes = 1
            for p in rest.split():
                pd = parse_time(p)
                if pd:
                    minutes = min(pd, 10)
                    break
            cutoff = int(time.time()) - minutes * 60
            recent = await db.get_users_by_msg_count(chat_id, min_count=0, since=cutoff)
            kicked = 0
            for rid, rcount, rtime in recent:
                if rid == message.from_user.id:
                    continue
                if await kick_user(chat_id, rid, "Активность"):
                    await db.add_kick(chat_id, rid, user_id, f"Актив {minutes}мин", False)
                    kicked += 1
                    await asyncio.sleep(0.3)
            resp = f"👢 Исключено активных: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        # ---- KICK NEWCOMERS ----
        if rest_lower.startswith('нов') or rest_lower.startswith('new'):
            min_rank = await get_min_rank(chat_id, "kick_newcomers")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            hours = 10
            max_msgs = 3
            for p in rest.split():
                pd = parse_time(p)
                if pd:
                    hours = max(1, pd // 60)
                    break
            cutoff = int(time.time()) - hours * 3600
            newcomers = await db.get_users_by_msg_count(chat_id, min_count=0, max_count=max_msgs, since=cutoff)
            kicked = 0
            for nid, ncount, ntime in newcomers:
                if await kick_user(chat_id, nid, "Новичок"):
                    await db.add_kick(chat_id, nid, user_id, f"Новичок {hours}ч", False)
                    kicked += 1
                    await asyncio.sleep(0.3)
            resp = f"👢 Исключено новичков: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        # ---- KICK DELETED ACCOUNTS ----
        if rest_lower.startswith('удалён') or rest_lower.startswith('deleted') or rest_lower.startswith('собак'):
            min_rank = await get_min_rank(chat_id, "kick_deleted")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            users = await db.get_users_by_msg_count(chat_id, min_count=0)
            kicked = 0
            for did, dcount, dtime in users:
                try:
                    member = await bot.get_chat_member(chat_id, did)
                    if member.user.is_deleted:
                        if await kick_user(chat_id, did, "Удалённый аккаунт"):
                            await db.add_kick(chat_id, did, user_id, "Удалённый аккаунт", False)
                            kicked += 1
                            await asyncio.sleep(0.3)
                except Exception:
                    pass
            resp = f"👢 Исключено удалённых аккаунтов: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        # ---- KICK LURKERS ----
        if rest_lower.startswith('молч') or rest_lower.startswith('lurk'):
            min_rank = await get_min_rank(chat_id, "kick_lurkers")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            days = 30
            for p in rest.split():
                pd = parse_time(p)
                if pd:
                    days = max(1, pd // 1440)
                    break
            cutoff = int(time.time()) - days * 86400
            lurkers = await db.get_lurkers(chat_id, cutoff)
            kicked = 0
            for lid, ltime in lurkers:
                if await kick_user(chat_id, lid, "Молчун"):
                    await db.add_kick(chat_id, lid, user_id, f"Молчун {days}д", False)
                    kicked += 1
                    await asyncio.sleep(0.3)
            resp = f"👢 Исключено молчунов: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        # ---- KICK BY MESSAGE COUNT ----
        if rest_lower.startswith('по смс') or rest_lower.startswith('by msg'):
            min_rank = await get_min_rank(chat_id, "kick_by_msgs")
            if not await check_rank(chat_id, user_id, min_rank):
                await message.reply("❌ Недостаточно прав.")
                return
            parts = rest.split()
            min_msgs = 5
            days = 7
            for p in parts:
                if p.lstrip('-').isdigit() and not any(c in p for c in ('м', 'ч', 'д', 'н', 'мес', 'г')):
                    min_msgs = int(p)
                pd = parse_time(p)
                if pd:
                    days = max(1, pd // 1440)
                    break
            cutoff = int(time.time()) - days * 86400
            users = await db.get_users_by_msg_count(chat_id, min_count=0, max_count=min_msgs, since=cutoff)
            kicked = 0
            for uid, ucount, utime in users:
                if await kick_user(chat_id, uid, f"Мало сообщений"):
                    await db.add_kick(chat_id, uid, user_id, f"<{min_msgs} смс за {days}д", False)
                    kicked += 1
                    await asyncio.sleep(0.3)
            resp = f"👢 Исключено по лимиту сообщений: {kicked}"
            if show_tags:
                resp += f"\n👮 {esc(message.from_user.first_name)} (ID:{user_id})"
            await message.reply(resp)
            return

        return

    # ---- LIST DELETED ACCOUNTS ----
    if re.match(r'^(кто\s+удалён|кто\s+собака)', text, re.IGNORECASE):
        users = await db.get_users_by_msg_count(chat_id, min_count=0)
        deleted_list = []
        for did, dcount, dtime in users:
            dname = await resolve_name(chat_id, did)
            try:
                member = await bot.get_chat_member(chat_id, did)
                if member.user.is_deleted:
                    deleted_list.append(dname)
            except Exception:
                pass
        if deleted_list:
            await message.reply("👻 <b>Удалённые аккаунты:</b>\n" + "\n".join(deleted_list[:20]))
        else:
            await message.reply("Удалённые аккаунты не найдены.")
        return

    return
