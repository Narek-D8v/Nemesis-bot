import re
import time
import random
import asyncio
import aiosqlite

from collections import OrderedDict

from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.filters import (
    Command,
    ChatMemberUpdatedFilter,
    JOIN_TRANSITION,
    LEAVE_TRANSITION,
)
from bot import bot, logger
from db import db
from utils import (
    has_url, has_invite_link, has_mention_all, contains_mat,
    replace_mat, has_mask, is_account_old_enough,
    has_bot_command, esc,
)
from keyboards import captcha_correct_keyboard
from bayes import BayesClassifier

router = Router()

last_messages: OrderedDict = OrderedDict()

NEMUSYA_REPLIES = [
    "Мур-мур! 🐱",
    "Ты меня звал(а)? Я здесь! 💕",
    "Нуся-Нуся, я тут! 😘",
    "Ой, кто это меня позвал? Я! 😊",
    "Здравствуй, мой хороший! 🌸",
    "Ты чего, соскучился(лась)? 🥰",
    "Я всегда рядом! 🤗",
    "Мяу! Что случилось? 😸",
    "О, это я! Приятно, что меня помнят 💖",
    "Нуся-Нуся, я твой личный котик-модератор! 😻",
    "Да-да, я здесь! Чем могу помочь? 💫",
    "Ах, как приятно слышать своё имя! 😊",
    "Ты знаешь, что я люблю, когда меня так называют ❤️",
    "Нуся всегда на связи! 📱",
    "Ой, кто это? Это я! Привет! 🌟",
    "Мурлыкаю от радости! 🐾",
    "Ты сделал(а) мой день! 😍",
    "Ах, Немуся... Как мило! 😘",
    "Ты думал(а), я не отвечу? А вот и я! 😜",
    "Люблю, когда меня так зовут! 💕",
    "Я твой маленький модератор-ангел! 👼",
    "Нуся-Нуся, я весь внимание! 🧡",
    "Слушаю тебя, мой хороший! 🎧",
    "Какое приятное слово! 😊",
    "Ты знаешь, что я за тобой слежу? Но по-доброму! 😇",
    "Ой, меня позвали? Я тут как тут! 🏃‍♀️",
    "Нуся всегда рада тебя слышать! 🌺",
    "Ты мой любимый пользователь! 💗",
    "Нуся-Нуся, мур-мур! 😽",
    "Я тебя обнимаю мысленно! 🤗",
]


@router.message(lambda msg: msg.text and msg.text.lower().strip() == 'немуся')
async def nemusya_reply(message: Message):
    if message.from_user is None:
        return
    if message.from_user.is_bot:
        return
    username = esc(message.from_user.first_name or "дорогой пользователь")
    reply = random.choice(NEMUSYA_REPLIES)
    logger.info(f"Easter egg triggered: 'Немуся' by {message.from_user.id} in {message.chat.id}")
    await message.reply(f"{reply} {username}!")


async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


async def is_whitelisted(chat_id: int, user_id: int, settings: dict) -> bool:
    whitelist = settings.get("whitelist", [])
    return user_id in whitelist


async def is_blacklisted(chat_id: int, user_id: int, settings: dict) -> bool:
    blacklist = settings.get("blacklist", [])
    return user_id in blacklist


async def mute_user(chat_id: int, user_id: int, duration_minutes: int, reason: str):
    try:
        until_date = int(time.time()) + duration_minutes * 60
        await bot.restrict_chat_member(
            chat_id, user_id,
            can_send_messages=False,
            until_date=until_date,
        )
        await db.add_log(chat_id, user_id, "mute", reason)
        logger.info(f"Muted {user_id} in {chat_id} for {duration_minutes}min: {reason}")
    except Exception as e:
        logger.warning(f"Mute failed: {e}")


async def ban_user(chat_id: int, user_id: int, reason: str):
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await db.add_log(chat_id, user_id, "ban", reason)
        logger.info(f"Banned {user_id} in {chat_id}: {reason}")
    except Exception as e:
        logger.warning(f"Ban failed: {e}")


async def warn_and_check(chat_id: int, user_id: int, reason: str, settings: dict):
    await db.add_warn(chat_id, user_id, 0, reason)
    warnings = await db.get_active_warns(chat_id, user_id)
    warn_limit = settings.get("auto_mute_after_warns", 3)
    if len(warnings) >= warn_limit:
        mute_duration = settings.get("auto_mute_durations", {}).get("mute", 10)
        await mute_user(chat_id, user_id, mute_duration, f"Превышение лимита предупреждений ({reason})")
        await db.clear_warns(chat_id, user_id)
        return True
    await db.add_log(chat_id, user_id, "warn", reason)
    return False


async def send_captcha(chat_id: int, user_id: int):
    captcha_type = (await db.get_settings(chat_id)).get("captcha", {}).get("type", "button")
    try:
        if captcha_type == "math":
            a, b = random.randint(1, 10), random.randint(1, 10)
            answer = a + b
            msg = await bot.send_message(
                chat_id,
                f"🧩 <b>Капча для новичка!</b>\n\n"
                f"{user_id}, реши пример: {a} + {b} = ?\n"
                f"У вас есть 60 секунд.",
            )
            await db.add_log(chat_id, user_id, "captcha", f"math:{answer}")
        else:
            msg = await bot.send_message(
                chat_id,
                f"🧩 <b>Капча для новичка!</b>\n\n"
                f"{user_id}, нажми кнопку, чтобы подтвердить, что ты не робот.",
                reply_markup=captcha_correct_keyboard(),
            )
    except Exception as e:
        logger.warning(f"Captcha send failed: {e}")
        return

    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO captcha_pending (user_id, chat_id, message_id, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, msg.message_id, int(time.time())),
        )
        await conn.commit()


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user = event.new_chat_member.user

    settings = await db.get_settings(chat_id)

    username_display = f"@{user.username}" if user.username else user.full_name

    is_premium_group = await db.is_premium_group(chat_id)

    if is_premium_group:
        if await is_blacklisted(chat_id, user.id, settings):
            await ban_user(chat_id, user.id, "Чёрный список")
            try:
                await bot.send_message(
                    chat_id,
                    f"⛔ {username_display} забанен (в чёрном списке)"
                )
            except Exception:
                pass
            return

    if settings.get("min_account_age_days", 3) > 0:
        join_date = event.new_chat_member.joined_date or 0
        if not is_account_old_enough(join_date, settings["min_account_age_days"]):
            await ban_user(chat_id, user.id, "Аккаунт слишком новый")
            try:
                await bot.send_message(
                    chat_id,
                    f"⛔ {username_display} забанен (аккаунт младше {settings['min_account_age_days']} дней)"
                )
            except Exception:
                pass
            return

    if settings.get("block_no_avatar", False):
        if not user.photo:
            await ban_user(chat_id, user.id, "Нет аватарки")
            try:
                await bot.send_message(
                    chat_id,
                    f"⛔ {username_display} забанен (нет аватарки)"
                )
            except Exception:
                pass
            return

    if settings.get("captcha", {}).get("enabled", True):
        await send_captcha(chat_id, user.id)

    if settings.get("greeting", {}).get("enabled", True):
        greeting_text = settings["greeting"]["text"]
        greeting_text = greeting_text.replace("{username}", esc(username_display))
        try:
            await bot.send_message(chat_id, greeting_text)
        except Exception:
            pass


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_user_leave(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user = event.old_chat_member.user
    settings = await db.get_settings(chat_id)

    await db.add_exit_event(chat_id, user.id)

    autokick = settings.get("autokick_on_exit", False)
    if autokick:
        exit_data = await db.get_exit_count(chat_id, user.id)
        if exit_data:
            count, last = exit_data
            max_count = settings.get("autokick_exit_count", 3)
            max_time = settings.get("autokick_exit_time", 60)
            if count >= max_count and int(time.time()) - last < max_time * 60:
                action = settings.get("autokick_exit_action", "ban")
                try:
                    if action == "ban":
                        await bot.ban_chat_member(chat_id, user.id)
                        logger.info(f"Autoban {user.id} in {chat_id} (exit limit)")
                    else:
                        await bot.ban_chat_member(chat_id, user.id)
                        await bot.unban_chat_member(chat_id, user.id)
                        logger.info(f"Autokick {user.id} in {chat_id} (exit limit)")
                except Exception as e:
                    logger.warning(f"Autokick on exit failed: {e}")

    if settings.get("farewell", {}).get("enabled", True):
        username_display = f"@{user.username}" if user.username else user.full_name
        farewell_text = settings["farewell"]["text"]
        farewell_text = farewell_text.replace("{username}", esc(username_display))
        try:
            await bot.send_message(chat_id, farewell_text)
        except Exception:
            pass


async def _resolve_target_text(message: Message) -> str | None:
    await asyncio.sleep(0.5)
    if message.reply_to_message:
        return message.reply_to_message.text or message.reply_to_message.caption

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()

    return None


async def _train_bayes(message: Message, is_spam: bool):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Эта команда работает только в группах.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только администраторы могут обучать бота.")
        return

    is_prem = await db.is_premium_group(chat_id) or await db.is_premium_user(user_id)
    if not is_prem:
        await message.reply("⚠️ Эта функция доступна только для Премиум-подписчиков.")
        return

    text = await _resolve_target_text(message)
    if text:
        bayes_settings = await db.get_bayes_settings(chat_id)
        classifier = BayesClassifier(db.db_path, bayes_settings['model_name'])
        await classifier.train(text, is_spam=is_spam)
        stats = await classifier.get_stats()
        label = "спам" if is_spam else "хорошее (HAM)"
        await message.reply(
            f"✅ <b>Модель обучена!</b>\n\n"
            f"Сообщение отмечено как <b>{label}</b> и добавлено в модель.\n"
            f"Спам: {stats['spam_total']} | Хам: {stats['ham_total']}\n"
            f"Словарь: {stats['vocab_size']} слов"
        )
        logger.info(f"Bayes trained {'spam' if is_spam else 'ham'} by {user_id} in {chat_id}")
    else:
        cmd = "/markspam" if is_spam else "/markham"
        await message.reply(
            f"ℹ️ Ответьте на сообщение или напишите:\n"
            f"<code>{cmd} текст_сообщения</code>"
        )


@router.message(Command("markspam"))
async def cmd_markspam(message: Message):
    await _train_bayes(message, is_spam=True)


@router.message(Command("markham"))
async def cmd_markham(message: Message):
    await _train_bayes(message, is_spam=False)


@router.message(Command("report"))
async def cmd_report(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Эта команда работает только в группах.")
        return

    chat_id = message.chat.id
    settings = await db.get_settings(chat_id)
    if not settings.get("report_enabled", True):
        await message.answer("Репорты отключены в этом чате.")
        return

    if not message.reply_to_message:
        await message.answer("ℹ️ Ответьте на сообщение нарушителя командой /report")
        return

    text = message.text or ""
    reason = re.sub(r'^/report\s*', '', text, flags=re.IGNORECASE).strip()
    if not reason:
        reason = "Пользователь отправил жалобу на сообщение"

    reporter = message.from_user
    if reporter is None:
        return

    offender = message.reply_to_message.from_user if message.reply_to_message else None

    await db.add_report(chat_id, reporter.id, offender.id if offender else 0, reason)
    logger.info(f"Report from {reporter.id} on {offender.id if offender else 'unknown'} in {chat_id}")

    link_chat_id = str(chat_id)
    if link_chat_id.startswith("-100"):
        link_chat_id = link_chat_id[4:]
    msg_link = f"https://t.me/c/{link_chat_id}/{message.reply_to_message.message_id}"

    reporter_name = esc(reporter.first_name or "Пользователь")
    offender_name = esc(offender.first_name or "Пользователь") if offender else "Неизвестно"
    offender_id = offender.id if offender else 0

    notification = (
        f"📢 <b>Новая жалоба!</b>\n\n"
        f"От: {reporter_name} (<code>{reporter.id}</code>)\n"
        f"На: {offender_name} (<code>{offender_id}</code>)\n"
        f"Сообщение: <a href='{msg_link}'>ссылка</a>\n"
        f"Причина: {esc(reason)}"
    )

    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                try:
                    await bot.send_message(admin.user.id, notification)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to send report to admins: {e}")

    await message.reply("✅ Жалоба отправлена администраторам!")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("clear"))
async def cmd_clear(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id):
        await message.answer("❌ Только администраторы могут использовать эту команду.")
        return

    settings = await db.get_settings(chat_id)
    if not settings.get("clear_chat_enabled", True):
        await message.answer("Очистка чата отключена.")
        return

    try:
        cutoff = int(time.time()) - 3600
        deleted = 0
        async for msg in bot.get_chat_history(chat_id, limit=100):
            if msg.date.timestamp() >= cutoff and not msg.is_topic_message:
                try:
                    await msg.delete()
                    deleted += 1
                except Exception:
                    pass
        await message.answer(f"🧹 Удалено {deleted} сообщений за последний час.")
    except Exception as e:
        logger.warning(f"Clear chat failed: {e}")
        await message.answer("❌ Не удалось очистить чат. Проверьте права бота.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def message_handler(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text
    settings = await db.get_settings(chat_id)

    await db.track_message(chat_id, user_id)

    if await is_admin(chat_id, user_id):
        return

    is_premium_group = await db.is_premium_group(chat_id)

    if is_premium_group and await is_whitelisted(chat_id, user_id, settings):
        return

    bayes_settings = await db.get_bayes_settings(chat_id)
    if bayes_settings['enabled']:
        try:
            classifier = BayesClassifier(db.db_path, bayes_settings['model_name'])
            is_spam, confidence = await classifier.classify(text)
            if is_spam and confidence >= bayes_settings['threshold']:
                await message.delete()
                await db.add_log(chat_id, user_id, "bayes_spam", f"conf:{confidence:.2f}")
                logger.info(f"Bayes spam deleted from {user_id} in {chat_id} (conf={confidence:.2f})")
                return
        except Exception as e:
            logger.warning(f"Bayes classify error: {e}")

    if settings.get("block_bot_commands", True) and text.startswith("/"):
        if has_bot_command(text) and text not in ("/start", "/help", "/report"):
            try:
                await message.delete()
                await db.add_log(chat_id, user_id, "delete", "Команда другого бота")
                warn = await message.answer(
                    f"🚫 {esc(message.from_user.first_name)}, команды других ботов запрещены."
                )
                await asyncio.sleep(5)
                await warn.delete()
            except Exception:
                pass
            return

    if settings.get("duplicate_block", True):
        global last_messages
        key = (chat_id, user_id)
        if key not in last_messages:
            last_messages[key] = []
            if len(last_messages) > 10000:
                last_messages.pop(next(iter(last_messages)))
        last_messages[key].append(text)
        last_messages[key] = last_messages[key][-5:]
        if len(last_messages[key]) >= 3 and len(set(last_messages[key][-3:])) == 1:
            try:
                await message.delete()
                await mute_user(chat_id, user_id, 5, "Повтор сообщений")
                await db.add_log(chat_id, user_id, "mute", "Повтор сообщений")
                warn = await message.answer(
                    f"🔇 {esc(message.from_user.first_name)}, мут 5 мин за повтор сообщений."
                )
                await asyncio.sleep(5)
                await warn.delete()
            except Exception:
                pass
            return

    if settings.get("mention_block", True) and has_mention_all(text):
        try:
            await message.delete()
            warn = await message.answer(
                f"🚫 {esc(message.from_user.first_name)}, массовые упоминания запрещены."
            )
            await asyncio.sleep(5)
            await warn.delete()
            await db.add_log(chat_id, user_id, "delete", "Массовое упоминание")
        except Exception:
            pass
        return

    async def handle_link_violation(link_type: str):
        action = settings.get("filter_links", {}).get("action", "delete")
        try:
            await message.delete()
            await db.add_log(chat_id, user_id, "delete", link_type)
            if action == "warn":
                await warn_and_check(chat_id, user_id, link_type, settings)
                await message.answer(
                    f"⚠️ {esc(message.from_user.first_name)}, {link_type} запрещены!"
                )
            elif action == "mute":
                await mute_user(chat_id, user_id, 15, link_type)
            elif action == "warn_mute":
                warned = await warn_and_check(chat_id, user_id, link_type, settings)
                if warned:
                    await mute_user(chat_id, user_id, 30, link_type)
                await message.answer(
                    f"⚠️ {esc(message.from_user.first_name)}, {link_type} запрещены!"
                )
            elif action == "ban":
                await ban_user(chat_id, user_id, link_type)
        except Exception:
            pass

    if settings.get("invite_block", True) and has_invite_link(text):
        await handle_link_violation("Инвайт-ссылка")
        return

    if settings.get("filter_links", {}).get("enabled", True) and has_url(text):
        await handle_link_violation("Внешняя ссылка")
        return

    if settings.get("mask_check", True) and has_mask(text):
        try:
            await message.delete()
            await db.add_log(chat_id, user_id, "delete", "Маскировка символов")
            captcha_susp = settings.get("captcha_for_suspicious", settings.get("captcha", {}).get("suspicious", True))
            if captcha_susp:
                await send_captcha(chat_id, user_id)
        except Exception:
            pass
        return

    blacklist_words = settings.get("blacklist_words", [])
    if blacklist_words:
        text_lower = text.lower()
        for word in blacklist_words:
            if word in text_lower:
                try:
                    await message.delete()
                    await db.add_log(chat_id, user_id, "delete", f"Чёрный список: {word}")
                    warn = await message.answer(
                        f"🚫 {esc(message.from_user.first_name)}, это слово запрещено."
                    )
                    await asyncio.sleep(5)
                    await warn.delete()
                except Exception:
                    pass
                return

    mute_filter = settings.get("filter_mute", {})
    if mute_filter.get("enabled", True) and contains_mat(text):
        if mute_filter.get("replace_with_stars", False):
            try:
                await message.edit_text(replace_mat(text))
                await db.add_log(chat_id, user_id, "edit", "Замена мата")
            except Exception:
                pass
        else:
            try:
                await message.delete()
                warns = await db.get_active_warns(chat_id, user_id)
                mat_warns = [w for w in warns if "мат" in w[1]]
                if len(mat_warns) >= 2:
                    await mute_user(chat_id, user_id, 10, "Мат (3+ предупреждения)")
                    await db.clear_warns(chat_id, user_id)
                    await message.answer(
                        f"🔇 {esc(message.from_user.first_name)}, мут 10 мин за мат."
                    )
                else:
                    await db.add_warn(chat_id, user_id, 0, "мат")
                    await db.add_log(chat_id, user_id, "warn", "мат")
                    warn = await message.answer(
                        f"⚠️ {esc(message.from_user.first_name)}, мат запрещён! "
                        f"(предупреждение {len(mat_warnings) + 1}/3)"
                    )
                    await asyncio.sleep(5)
                    await warn.delete()
            except Exception:
                pass
        return

    if settings.get("forward_block", True) and (message.forward_from or message.forward_from_chat or message.forward_sender_name):
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            joined_date = member.joined_date or 0
            if time.time() - joined_date < 86400:
                await message.delete()
                await db.add_log(chat_id, user_id, "delete", "Форвард новичка")
                warn = await message.answer(
                    f"🚫 {esc(message.from_user.first_name)}, пересылка запрещена в первые 24 часа."
                )
                await asyncio.sleep(5)
                await warn.delete()
        except Exception:
            pass
        return

    if settings.get("virus_total_enabled", False) and is_premium_group:
        from utils.virustotal import extract_urls, check_url_safety
        urls = extract_urls(text)
        for url in urls:
            stats = await check_url_safety(url)
            if stats and (stats.get("malicious", 0) + stats.get("suspicious", 0)) >= 1:
                try:
                    await message.delete()
                    await db.add_log(chat_id, user_id, "virus_total", f"Malicious URL: {url}")
                    logger.info(f"Deleted malicious URL from {user_id} in {chat_id}: {url}")
                    warn = await message.answer(
                        f"🛡️ {esc(message.from_user.first_name)}, ваше сообщение удалено "
                        f"(обнаружена вредоносная ссылка: {stats.get('malicious', 0)} malicious, "
                        f"{stats.get('suspicious', 0)} suspicious)"
                    )
                    await asyncio.sleep(5)
                    await warn.delete()
                except Exception:
                    pass
                return
