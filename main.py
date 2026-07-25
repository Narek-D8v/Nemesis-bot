import asyncio
import base64
import datetime
import hashlib
import json
import os
import random
import re
import string
import time
import uuid
from collections import defaultdict

import aiohttp
from flask import Flask
from PIL import Image, ImageDraw

from telethon import events
from telethon.errors import FloodWaitError, MessageNotModifiedError
from client import client
from telethon.tl.functions.account import (
    GetAuthorizationsRequest,
)
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import (
    ChannelParticipantsAdmins, ChannelParticipantsBots, InputMediaDice,
    ReactionEmoji,
)

import qrcode

from config import (
    API_ID, API_HASH, PORT, OWNER_ID,
    MEDIA_DIR, MAX_COOLDOWN_ENTRIES,
    MAX_FILE_SIZE_MB, logger,
)
from utils import fmt_time, progress_bar, safe_eval, caesar, morse_enc, gen_pwd, vigenere
from downloaders import run_download, send_and_clean, set_max_file_size
from rp_commands import (
    RP_COMMANDS, format_rp_action, get_all_categories,
    get_category_commands, get_rp_reply,
)
from core import db, state, owner_filter, respond, _get_translator

set_max_file_size(MAX_FILE_SIZE_MB)

_log = logger
command_cooldown = defaultdict(float)
reply_cooldown = {}
_download_lock = asyncio.Lock()
_watch_task = None
_protect_task = None



app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 UserBot работает 24/7!"

def run_web():
    app.run(host='127.0.0.1', port=PORT)

@client.on(events.NewMessage(pattern=r'!sleep$', func=owner_filter))
async def sleep_cmd(e):

    state.toggle_auto_reply(True)
    await respond(e, '💤 Автоответчик **ВКЛЮЧЕН**.')
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!wake$', func=owner_filter))
async def wake_cmd(e):

    state.toggle_auto_reply(False)
    await respond(e, '☀️ Автоответчик **ВЫКЛЮЧЕН**.')
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!setreply(?:\s+(@\w+))?(?:\s+(.+))?', func=owner_filter))
async def setreply_cmd(e):

    g = e.pattern_match
    target, text = g.group(1), g.group(2)
    if target and target.lower() == '@default':
        db.set_default_reply(text or '')
        await respond(e, f"✅ Дефолтный ответ установлен:\n_{text or 'пусто'}_")
    elif target:
        db.set_reply_text(target.lstrip('@'), text or '')
        await respond(e, f"✅ Ответ для {target} установлен:\n_{text or 'пусто'}_")
    elif text:
        state.set_auto_reply_text(text)
        await respond(e, f"✅ Текст автоответчика:\n_{text}_")
    else:
        await respond(e, "ℹ️ `!setreply @username текст` или `!setreply default текст`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!status$', func=owner_filter))
async def status_cmd(e):

    me = await client.get_me()
    dialogs = await client.get_dialogs()
    s = db.all_stats()
    afk_status = f"✅ {state.afk_reason or 'без причины'}" if state.afk_start_time else "❌"
    await respond(e, 
        f"📊 **Статус UserBot**\n\n"
        f"👤 {me.first_name} {me.last_name or ''}\n"
        f"💬 Чатов: `{len(dialogs)}`\n"
        f"🤖 Автоответчик: {'💤 Вкл' if state.auto_reply_enabled else '☀️ Выкл'}\n"
        f"👻 Ghost: {'✅' if state.ghost_mode else '❌'}\n"
        f"🔇 Cover: {'✅' if state.cover_enabled else '❌'}\n"
        f"🤐 Silent: {'✅' if state.silent_enabled else '❌'}\n"
        f"👤 Shadow: {'✅' if state.shadow_enabled else '❌'}\n"
        f"🔒 Lock: {'✅' if state.lock_enabled else '❌'}\n"
        f"🔇 Mute: {'✅' if state.mute_enabled else '❌'}\n"
        f"⌨️ Тайпинг: {'✅' if state.typing_enabled else '❌'}\n"
        f"🗑️ Автоудал: {'✅' if state.autodel_enabled else '❌'}\n"
        f"⏳ Задержка: `{state.reply_delay}с`\n"
        f"👁️ Прочтение: {'✅' if state.readreceipt_enabled else '❌'}\n"
        f"😴 AFK: {afk_status}\n"
        f"👑 Sudo: `{len(state.sudo_users)}`\n"
        f"⏱ Аптайм: `{state.uptime}`\n"
        f"📨 Команд выполнено: `{s.get('cmds', 0)}`"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!time$', func=owner_filter))
async def time_cmd(e):

    now = datetime.datetime.now()
    utc = datetime.datetime.utcnow()
    week_days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    await respond(e, 
        f"🕐 **Время и дата**\n\n"
        f"🏠 Локальное: `{now.strftime('%H:%M:%S')}`\n"
        f"🌍 UTC: `{utc.strftime('%H:%M:%S')}`\n"
        f"📅 Дата: `{now.strftime('%d.%m.%Y')}`\n"
        f"📆 День: **{week_days[now.weekday()]}**"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!ping$', func=owner_filter))
async def ping_cmd(e):

    t0 = time.monotonic()
    await respond(e, "🏓 ...")
    ms = (time.monotonic() - t0) * 1000
    q = "🟢 Отлично" if ms < 150 else "🟡 Нормально" if ms < 400 else "🔴 Высокая"
    await respond(e, f"🏓 **Понг!**\n⚡ Задержка: `{ms:.1f} мс`\n📶 Качество: {q}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!id$', func=owner_filter))
async def id_cmd(e):

    chat = await e.get_chat()
    lines = [f"🆔 **ID чата:** `{chat.id}`"]
    if e.reply_to_msg_id:
        r = await e.get_reply_message()
        lines += [
            f"👤 **ID отправителя:** `{r.sender_id}`",
            f"📨 **ID сообщения:** `{r.id}`",
        ]
        if r.sender and getattr(r.sender, 'username', None):
            lines.append(f"🔖 **Username:** @{r.sender.username}")
    else:
        me = await client.get_me()
        lines.append(f"👤 **Мой ID:** `{me.id}`")
    await respond(e, "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!info$', func=owner_filter))
async def info_cmd(e):

    me = await client.get_me()
    dialogs = await client.get_dialogs()
    await respond(e, 
        f"🚀 **UserBot Info**\n\n"
        f"👤 {me.first_name} {me.last_name or ''}\n"
        f"🆔 ID: `{me.id}`\n"
        f"🔰 @{me.username or 'нет'}\n"
        f"📱 Телефон: `{me.phone or 'скрыт'}`\n"
        f"💬 Чатов: `{len(dialogs)}`\n"
        f"⏱ Аптайм: `{state.uptime}`\n"
        f"⚡ Статус: **Активен** ✅"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!restart$', func=owner_filter))
async def restart_cmd(e):

    await respond(e, '🔄 Перезагрузка...')
    await asyncio.sleep(2)
    await client.disconnect()
    os._exit(0)

@client.on(events.NewMessage(pattern=r'!ghost$', func=owner_filter))
async def ghost_cmd(e):

    state.toggle_ghost()
    if state.ghost_mode:
        await respond(e, "👻 **Ghost-режим ВКЛЮЧЁН** — команды удаляются мгновенно")
        await asyncio.sleep(2)
        await e.delete()
    else:
        await respond(e, "👁 **Ghost-режим ВЫКЛЮЧЕН**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!cover(?:\s+(off|on))?$', func=owner_filter))
async def cover_cmd(e):
    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_cover(False)
        await respond(e, "🛡️ **Cover-режим ВЫКЛЮЧЕН** — команды снова работают.")
    else:
        state.set_cover(True)
        await respond(e, "🛡️ **Cover-режим ВКЛЮЧЁН** — все команды, кроме `!cover off`, игнорируются.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!silent\s*(on|off)?$', func=owner_filter))
async def silent_cmd(e):
    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_silent(False)
        await respond(e, "🔇 **Silent-режим ВЫКЛЮЧЕН** — ответы снова отправляются.")
    else:
        state.set_silent(True)
        await respond(e, "🔇 **Silent-режим ВКЛЮЧЁН** — бот молчит в ЛС.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!shadow(?:\s+(\d+))?$', func=owner_filter))
async def shadow_cmd(e):
    delay = e.pattern_match.group(1)
    if delay:
        d = int(delay)
        state.set_shadow(True, max(1, d))
        await respond(e, f"👤 **Shadow-режим ВКЛЮЧЁН** — удаление через {max(1, d)} сек.")
    elif state.shadow_enabled:
        state.set_shadow(False)
        await respond(e, "👤 **Shadow-режим ВЫКЛЮЧЕН** — автодудаление отключено.")
    else:
        state.set_shadow(True)
        await respond(e, "👤 **Shadow-режим ВКЛЮЧЁН** — удаление через 5 сек.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!lock(?:\s+(on|off))?$', func=owner_filter))
async def lock_cmd(e):
    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_lock(False)
        await respond(e, "🔒 **Lock-режим ВЫКЛЮЧЕН** — ЛС от всех открыты.")
    else:
        state.set_lock(True)
        await respond(e, "🔒 **Lock-режим ВКЛЮЧЁН** — бот отвечает только контактам.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!mute(?:\s+(on|off))?$', func=owner_filter))
async def mute_cmd(e):
    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_mute(False)
        await respond(e, "🔇 **Mute-режим ВЫКЛЮЧЕН** — ЛС принимаются.")
    else:
        state.set_mute(True)
        await respond(e, "🔇 **Mute-режим ВКЛЮЧЁН** — все ЛС игнорируются.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!typing(?:\s+(on|off))?$', func=owner_filter))
async def typing_cmd(e):

    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_typing(False)
        await respond(e, "⌨️ **Тайпинг ВЫКЛЮЧЕН** — индикатор печати не показывается.")
    else:
        state.set_typing(True)
        await respond(e, "⌨️ **Тайпинг ВКЛЮЧЁН** — перед ответом показывается «печатает...».")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!autodel(?:\s+(on|off))?(?:\s+(\d+))?$', func=owner_filter))
async def autodel_cmd(e):

    arg = e.pattern_match.group(1)
    delay_str = e.pattern_match.group(2)
    if arg == 'off':
        state.set_autodel(False)
        await respond(e, "🗑️ **Автоудаление ВЫКЛЮЧЕНО** — сообщения не удаляются.")
    else:
        d = int(delay_str) if delay_str else 10
        state.set_autodel(True, max(3, d))
        await respond(e, f"🗑️ **Автоудаление ВКЛЮЧЕНО** — удаление через {max(3, d)} сек.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!delay\s+(\d+)', func=owner_filter))
async def delay_cmd(e):

    sec = int(e.pattern_match.group(1))
    state.set_reply_delay(min(sec, 30))
    if state.reply_delay > 0:
        await respond(e, f"⏳ **Задержка ответа: {state.reply_delay} сек.**")
    else:
        await respond(e, "⏳ **Задержка ответа ВЫКЛЮЧЕНА.**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!readreceipt(?:\s+(on|off))?$', func=owner_filter))
async def readreceipt_cmd(e):

    arg = e.pattern_match.group(1)
    if arg == 'off':
        state.set_readreceipt(False)
        await respond(e, "👁️ **Прочтение ВЫКЛЮЧЕНО** — сообщения остаются непрочитанными.")
    else:
        state.set_readreceipt(True)
        await respond(e, "👁️ **Прочтение ВКЛЮЧЕНО** — сообщения отмечаются прочитанными.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!sudo(?:\s+(on|off)\s+(\S+))?\s*$', func=owner_filter))
async def sudo_cmd(e):

    g = e.pattern_match
    action = g.group(1)
    target = g.group(2)
    if not action:
        if state.sudo_users:
            lines = ["👑 **Sudo-пользователи:**\n"]
            for uid in list(state.sudo_users):
                try:
                    ent = await client.get_entity(uid)
                    name = getattr(ent, 'first_name', '') or str(uid)
                    uname = f" @{ent.username}" if getattr(ent, 'username', None) else ''
                    lines.append(f"• {name}{uname} (`{uid}`)")
                except Exception:
                    lines.append(f"• `{uid}`")
            await respond(e, "\n".join(lines))
        else:
            await respond(e, "👑 **Sudo-пользователи отсутствуют.**")
        db.bump_stat('cmds')
        return
    try:
        ent = await client.get_entity(target)
    except Exception as ex:
        await respond(e, f"❌ Пользователь {target} не найден: {ex}")
        db.bump_stat('cmds')
        return
    name = getattr(ent, 'first_name', '') or str(ent.id)
    if action == 'on':
        state.add_sudo(ent.id)
        await respond(e, f"👑 **{name}** добавлен в sudo.")
    else:
        state.remove_sudo(ent.id)
        await respond(e, f"👑 **{name}** удалён из sudo.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!status_reset$', func=owner_filter))
async def status_reset_cmd(e):
    state.reset_stealth()
    await respond(e, "🔄 **Все стелс-режимы сброшены**: cover, silent, shadow, lock, mute — выключены.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!me$', func=owner_filter))
async def me_cmd(e):

    me = await client.get_me()
    photos = await client.get_profile_photos(me.id, limit=1)
    await respond(e, 
        f"👤 **Мой профиль**\n\n"
        f"📛 {me.first_name} {me.last_name or ''}\n"
        f"🆔 `{me.id}`\n"
        f"🔰 @{me.username or 'нет'}\n"
        f"📱 `{me.phone or 'скрыт'}`\n"
        f"🖼 Аватар: {'✅' if photos else '❌'}\n"
        f"✔️ Verified: {'✅' if me.verified else '❌'}\n"
        f"🤖 Бот: {'✅' if me.bot else '❌'}"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!avatar$', func=owner_filter))
async def avatar_cmd(e):

    if e.reply_to_msg_id:
        r = await e.get_reply_message()
        uid = r.sender_id
    else:
        uid = (await client.get_me()).id
    photos = await client.get_profile_photos(uid, limit=1)
    if photos:
        await e.reply(file=photos[0])
        await e.delete()
    else:
        await respond(e, "❌ Аватарка не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!name (.+)', func=owner_filter))
async def name_cmd(e):

    n = e.pattern_match.group(1).strip()
    await client.edit_profile(first_name=n)
    await respond(e, f"✅ Имя → **{n}**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!lastname(?:\s+(.+))?$', func=owner_filter))
async def lastname_cmd(e):

    n = (e.pattern_match.group(1) or '').strip()
    await client.edit_profile(last_name=n)
    await respond(e, f"✅ Фамилия → **{n}**" if n else "✅ Фамилия удалена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!bio(?:\s+(.+))?$', func=owner_filter))
async def bio_cmd(e):

    t = (e.pattern_match.group(1) or '').strip()
    await client.edit_profile(about=t)
    await respond(e, f"✅ Био → _{t}_" if t else "✅ Био очищено")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!whois (.+)', func=owner_filter))
async def whois_cmd(e):

    target = e.pattern_match.group(1).strip().lstrip('@')
    try:
        ent = await client.get_entity(target)
        name = f"{getattr(ent, 'first_name', '') or ''} {getattr(ent, 'last_name', '') or ''}".strip() \
               or getattr(ent, 'title', '?')
        uname = f"@{ent.username}" if getattr(ent, 'username', None) else "нет"
        bot_ = "✅" if getattr(ent, 'bot', False) else "❌"
        ver = "✅" if getattr(ent, 'verified', False) else "❌"
        await respond(e, 
            f"🔍 **Информация о пользователе**\n\n"
            f"📛 Имя: **{name}**\n"
            f"🆔 ID: `{ent.id}`\n"
            f"🔰 Username: {uname}\n"
            f"🤖 Бот: {bot_}\n"
            f"✔️ Verified: {ver}"
        )
    except Exception as ex:
        await respond(e, f"❌ Не найден: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!username_check (.+)', func=owner_filter))
async def username_check_cmd(e):

    uname = e.pattern_match.group(1).strip().lstrip('@')
    try:
        ent = await client.get_entity(uname)
        name = getattr(ent, 'first_name', None) or getattr(ent, 'title', '?')
        await respond(e, f"🔍 @{uname}\n✅ **Занят**\n👤 {name}\n🆔 `{ent.id}`")
    except Exception:
        await respond(e, f"🔍 @{uname}\n✅ **Свободен**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!dice$', func=owner_filter))
async def dice_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('🎲'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!dart$', func=owner_filter))
async def dart_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('🎯'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!basket$', func=owner_filter))
async def basket_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('🏀'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!football$', func=owner_filter))
async def football_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('⚽'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!bowling$', func=owner_filter))
async def bowling_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('🎳'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!casino$', func=owner_filter))
async def casino_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, file=InputMediaDice('🎰'))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!coin$', func=owner_filter))
async def coin_cmd(e):

    sides = ["Орёл 🦅", "Решка 💰"]
    r = random.choice(sides)
    flips = random.randint(3, 9)
    await respond(e, f"🪙 Монета вращается {flips} раз...\n\nРезультат: **{r}**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!rand(?:\s+(-?\d+)(?:\s+(-?\d+))?)?$', func=owner_filter))
async def rand_cmd(e):

    g = e.pattern_match
    a, b = g.group(1), g.group(2)
    if a and b:
        lo, hi = sorted([int(a), int(b)])
        await respond(e, f"🎲 `{lo}` … `{hi}` → **{random.randint(lo, hi)}**")
    elif a:
        await respond(e, f"🎲 `1` … `{a}` → **{random.randint(1, int(a))}**")
    else:
        await respond(e, f"🎲 **{random.randint(1, 100)}**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!8ball(?:\s+(.+))?$', func=owner_filter))
async def eightball_cmd(e):

    ANSWERS = {
        'pos': [
            ("Определённо да", "✅", "Вселенная согласна с тобой."),
            ("Без сомнений", "💯", "Это решено раньше, чем ты спросил."),
            ("Скорее всего да", "👍", "Всё складывается в твою пользу."),
            ("Хорошие перспективы", "🌟", "Будущее выглядит светлым."),
            ("Знаки говорят «да»", "🔮", "Мистические силы на твоей стороне."),
            ("Всё указывает на «да»", "💫", "Судьба уже всё решила."),
            ("Да, и поскорее", "🚀", "Не медли — действуй прямо сейчас."),
            ("Абсолютно точно", "🏆", "Лучшего ответа не существует."),
            ("Это неизбежно", "⚡", "Ничто не остановит это."),
            ("Да, если сделаешь шаг", "🦶", "Действие — ключ к результату."),
            ("Вселенная шепчет: да", "🌌", "Даже звёзды кивают."),
            ("Смело иди вперёд", "🎯", "Ты уже знал ответ — я лишь подтверждаю."),
        ],
        'neu': [
            ("Пока не ясно", "🤔", "Туман будущего слишком густой."),
            ("Спроси позже", "⏰", "Момент ещё не настал."),
            ("Не могу предсказать", "🌫", "Слишком много переменных."),
            ("Сосредоточься и повтори", "🧘", "Твой разум мешает ответу."),
            ("Лучше не рассказывать", "🤫", "Некоторые тайны лучше хранить."),
            ("Трудно сказать", "😶", "Даже я не всесилен."),
            ("Возможно, но не сейчас", "🌙", "Подожди подходящего момента."),
            ("Ответ где-то рядом", "🔭", "Смотри внимательнее вокруг себя."),
        ],
        'neg': [
            ("Мой ответ — нет", "🚫", "Прими это спокойно."),
            ("Перспективы не очень", "😕", "Стоит пересмотреть планы."),
            ("Весьма сомнительно", "🙄", "Интуиция говорит «осторожно»."),
            ("Точно нет", "💀", "Даже не думай об этом."),
            ("Не рассчитывай", "❌", "Лучше найди другой путь."),
            ("Категорически нет", "🔴", "Вселенная против."),
            ("Всё против этого", "⛈", "Сейчас не лучшее время."),
            ("Откажись от идеи", "🗑", "Это дорога в никуда."),
            ("Шансы ничтожны", "🎰", "Даже удача отвернулась."),
        ],
    }
    question = (e.pattern_match.group(1) or '').strip()
    spin = ["🎱", "🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘", "🎱"]
    msg = await respond(e, "🎱 Шар вращается...")
    for frame in spin:
        await msg.edit(f"{frame} Шар вращается...")
        await asyncio.sleep(0.15)
    pool_key = random.choices(['pos', 'neu', 'neg'], weights=[38, 27, 35])[0]
    answer, emoji, comment = random.choice(ANSWERS[pool_key])
    color = {"pos": "🟢", "neu": "🟡", "neg": "🔴"}[pool_key]
    label = {"pos": "ПОЗИТИВНЫЙ", "neu": "НЕЙТРАЛЬНЫЙ", "neg": "НЕГАТИВНЫЙ"}[pool_key]
    confidence = random.randint(55, 99)
    bar = progress_bar(confidence, 100, 10)
    q_line = f"❓ _{question}_\n\n" if question else ""
    await msg.edit(
        f"🎱 **Магический шар**\n\n"
        f"{q_line}"
        f"{'─'*22}\n"
        f"{emoji}  **{answer}**\n"
        f"{'─'*22}\n\n"
        f"💬 _{comment}_\n\n"
        f"{color} {label}\n"
        f"[{bar}] **{confidence}%** уверенности"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!rps(?:\s+(.+))?$', func=owner_filter))
async def rps_cmd(e):

    MAP = {'к': '🪨 Камень', 'камень': '🪨 Камень', 'н': '✂️ Ножницы', 'ножницы': '✂️ Ножницы', 'б': '📄 Бумага', 'бумага': '📄 Бумага'}
    BOT = ['🪨 Камень', '✂️ Ножницы', '📄 Бумага']
    WIN = {'🪨 Камень': '✂️ Ножницы', '✂️ Ножницы': '📄 Бумага', '📄 Бумага': '🪨 Камень'}
    arg = (e.pattern_match.group(1) or '').lower().strip()
    if not arg or arg not in MAP:
        await respond(e, "✊✌️🖐 `!rps камень` / `ножницы` / `бумага` (или `к`!`н`!`б`)")
        return
    uc, bc = MAP[arg], random.choice(BOT)
    if uc == bc:
        res = "🤝 **Ничья!**"
    elif WIN[uc] == bc:
        res = "🏆 **Ты победил!**"
    else:
        res = "💀 **Бот победил!**"
    await respond(e, f"✊✌️🖐 **КНБ**\n\n👤 Ты: {uc}\n🤖 Бот: {bc}\n\n{res}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!slot$', func=owner_filter))
async def slot_cmd(e):

    SYM = ['🍒', '🍋', '🍊', '🍇', '🍉', '⭐', '💎', '7️⃣', '🔔', '🍀']
    msg = await respond(e, "🎰 [ ▓ | ▓ | ▓ ]")
    for _ in range(4):
        s = [random.choice(SYM) for _ in range(3)]
        await msg.edit(f"🎰 [ {s[0]} | {s[1]} | {s[2]} ]")
        await asyncio.sleep(0.3)
    s = [random.choice(SYM) for _ in range(3)]
    if s[0] == s[1] == s[2]:
        res = "💰💰💰 **ДЖЕКПОТ!**" if s[0] in ('💎', '7️⃣') else "🎊 **Выигрыш! Три одинаковых!**"
    elif len(set(s)) < 3:
        res = "😅 Почти! Два одинаковых — ещё раз!"
    else:
        res = "💸 Не повезло. Попробуй снова!"
    await msg.edit(f"🎰 [ {s[0]} | {s[1]} | {s[2]} ]\n\n{res}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!lucky$', func=owner_filter))
async def lucky_cmd(e):

    pct = random.randint(0, 100)
    bar = progress_bar(pct, 100, 12)
    tips = {
        (90, 100): "🌟 АБСОЛЮТНАЯ УДАЧА! Сегодня твой день!",
        (70, 89): "🍀 Очень удачный день — действуй!",
        (50, 69): "😊 Неплохо — удача на твоей стороне",
        (30, 49): "😐 Средний день, будь осторожен",
        (10, 29): "😬 Не лучший день...",
        (0, 9): "💀 Сиди дома и не высовывайся!",
    }
    msg = next(v for (a, b), v in tips.items() if a <= pct <= b)
    await respond(e, f"🔮 **Индекс удачи**\n\n[{bar}] **{pct}%**\n\n{msg}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!choose (.+)', func=owner_filter))
async def choose_cmd(e):

    raw = e.pattern_match.group(1)
    opts = [o.strip() for o in re.split(r'[,|/]', raw) if o.strip()]
    if len(opts) < 2:
        await respond(e, "ℹ️ Перечисли варианты через запятую: `!choose пицца, суши, бургер`")
        return
    winner = random.choice(opts)
    listed = "\n".join(f"{'➡️' if o == winner else '  •'} {o}" for o in opts)
    await respond(e, f"🤔 **Выбираю из {len(opts)} вариантов...**\n\n{listed}\n\n✅ **Выбор: {winner}**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!quiz$', func=owner_filter))
async def quiz_cmd(e):

    QUESTIONS = [
        ("Столица Австралии?", ["Сидней", "Мельбурн", "Канберра", "Перт"], 2),
        ("Сколько планет в Солнечной системе?", ["7", "8", "9", "10"], 1),
        ("Кто написал «Гамлета»?", ["Диккенс", "Толстой", "Шекспир", "Гёте"], 2),
        ("Химический символ золота?", ["Go", "Gd", "Au", "Ag"], 2),
        ("Год основания Google?", ["1996", "1998", "2000", "2002"], 1),
        ("Самая длинная река мира?", ["Амазонка", "Янцзы", "Нил", "Конго"], 2),
        ("Сколько байт в килобайте?", ["512", "1024", "2048", "4096"], 1),
        ("Скорость света (км/с)?", ["150 000", "300 000", "450 000", "600 000"], 1),
    ]
    q, opts, ans_idx = random.choice(QUESTIONS)
    letters = ['A', 'B', 'C', 'D']
    opts_text = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(opts))
    correct = f"{letters[ans_idx]}. {opts[ans_idx]}"
    await respond(e, 
        f"🧠 **Вопрос:**\n_{q}_\n\n{opts_text}\n\n"
        f"||✅ Ответ: **{correct}**||"
    )
    db.bump_stat('cmds')

# (functions moved to utils.py: safe_eval, caesar, morse_enc, gen_pwd, vigenere)

@client.on(events.NewMessage(pattern=r'!calc (.+)', func=owner_filter))
async def calc_cmd(e):

    expr = e.pattern_match.group(1).strip()
    r = safe_eval(expr)
    if r is not None:
        await respond(e, f"🧮 `{expr}` = **{r}**")
    else:
        await respond(e, "❌ Ошибка выражения. Разрешены: `+ - * / % sqrt sin cos tan log abs pow pi e factorial ceil floor round`")
    db.bump_stat('cmds')

async def send_reminder(chat_id, msg_text, delay):
    await asyncio.sleep(delay)
    try:
        await client.send_message(chat_id, f"⏰ **НАПОМИНАНИЕ:**\n{msg_text}")
    except Exception as e:
        logger.error(f"Ошибка напоминания: {e}")

@client.on(events.NewMessage(pattern=r'!remind (\d+)\s+(.+)', func=owner_filter))
async def remind_cmd(e):

    delay = int(e.pattern_match.group(1))
    text = e.pattern_match.group(2).strip()
    await respond(e, f"⏰ Напоминание через **{fmt_time(delay)}**\n📝 _{text}_")
    asyncio.create_task(send_reminder(e.chat_id, text, delay))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!search (.+)', func=owner_filter))
async def search_cmd(e):
    query = _to_english(e.pattern_match.group(1).strip())
    msg = await respond(e, "⏳ Ищу...")
    try:
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'format': 'json',
            'srlimit': 5,
        }
        async with aiohttp.ClientSession() as s:
            async with s.get('https://en.wikipedia.org/w/api.php', params=params) as resp:
                data = await resp.json()
        results = data.get('query', {}).get('search', [])
        if not results:
            await msg.edit("❌ Ничего не найдено.")
            return
        lines = [f"🔍 **Результаты (Wikipedia):** _{query}_\n"]
        for i, r in enumerate(results, 1):
            title = r.get('title', '?')
            href = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            snippet = r.get('snippet', '').replace('<span class="searchmatch">', '**').replace('</span>', '**')[:120]
            lines.append(f"{i}. [{title}]({href})")
            if snippet:
                lines.append(f"   _{snippet}_")
        await msg.edit("\n".join(lines))
    except Exception as ex:
        await msg.edit(f"❌ Ошибка поиска: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!shorten (.+)', func=owner_filter))
async def shorten_cmd(e):

    url = e.pattern_match.group(1).strip()
    msg = await respond(e, "⏳ Сокращаю...")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://is.gd/create.php",
                             params={"format": "json", "url": url},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        if 'shorturl' in data:
            await msg.edit(f"✂️ **Оригинал:** `{url[:55]}{'…' if len(url) > 55 else ''}`\n🔗 **Короткая:** {data['shorturl']}")
        else:
            await msg.edit(f"❌ Ошибка: {data.get('errormessage', 'Неверный URL')}")
    except Exception:
        await msg.edit("❌ Ошибка. Проверь URL.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!weather (.+)', func=owner_filter))
async def weather_cmd(e):

    city = e.pattern_match.group(1).strip()
    msg = await respond(e, "⏳ Запрашиваю погоду...")
    try:
        city_en = _to_english(city)
        from urllib.parse import quote
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{quote(city_en)}?format=j1",
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    raise ConnectionError(f"HTTP {r.status}")
                data = await r.json()
        cc = data.get('current_condition')
        loc = data.get('nearest_area')
        if not cc or not loc:
            await msg.edit("❌ Город не найден. Попробуй на латинице или уточни (страна/регион).")
            return
        cc = cc[0]
        loc = loc[0]
        city_name = loc['areaName'][0]['value']
        country = loc['country'][0]['value']
        temp = cc['temp_C']
        feels = cc['FeelsLikeC']
        humidity = cc['humidity']
        wind = cc['windspeedKmph']
        desc = cc['weatherDesc'][0]['value']
        await msg.edit(
            f"🌤 **Погода: {city_name}, {country}**\n\n"
            f"🌡 Температура: **{temp}°C** (ощущается как {feels}°C)\n"
            f"💧 Влажность: **{humidity}%**\n"
            f"💨 Ветер: **{wind} км/ч**\n"
            f"📋 {desc}"
        )
    except (aiohttp.ClientError, ConnectionError) as ex:
        logger.warning(f"wttr.in failed: {ex}, trying Open-Meteo...")
        async with aiohttp.ClientSession() as s:
            geo_r = await s.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={quote(city_en)}&count=1",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            if geo_r.status != 200:
                await msg.edit("❌ Город не найден. Попробуй на латинице.")
                return
            geo = await geo_r.json()
            results = geo.get('results')
            if not results:
                await msg.edit("❌ Город не найден. Попробуй на латинице.")
                return
            lat = results[0]['latitude']
            lon = results[0]['longitude']
            city_name = results[0].get('name', city)
            country = results[0].get('country', '')
            weather_r = await s.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                f"wind_speed_10m,weather_code&timezone=auto",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            if weather_r.status != 200:
                await msg.edit("❌ Не удалось получить погоду. Попробуй позже.")
                return
            wdata = await weather_r.json()
            cur = wdata.get('current', {})
            temp = cur.get('temperature_2m', '?')
            feels = cur.get('apparent_temperature', '?')
            humidity = cur.get('relative_humidity_2m', '?')
            wind = cur.get('wind_speed_10m', '?')
            wcode = cur.get('weather_code', 0)
            descs = {0:'Ясно', 1:'Преимущественно ясно', 2:'Переменная облачность', 3:'Пасмурно',
                     45:'Туман', 48:'Иней', 51:'Морось', 53:'Морось', 55:'Морось',
                     61:'Дождь', 63:'Дождь', 65:'Дождь', 71:'Снег', 73:'Снег', 75:'Снег',
                     80:'Ливень', 81:'Ливень', 82:'Ливень', 95:'Гроза', 96:'Гроза', 99:'Гроза'}
            desc = descs.get(wcode, f'Код {wcode}')
            await msg.edit(
                f"🌤 **Погода: {city_name}, {country}**\n\n"
                f"🌡 Температура: **{temp}°C** (ощущается как {feels}°C)\n"
                f"💧 Влажность: **{humidity}%**\n"
                f"💨 Ветер: **{wind} км/ч**\n"
                f"📋 {desc}"
            )
    except Exception as ex:
        logger.warning(f"Weather error: {ex}", exc_info=True)
        await msg.edit("❌ Ошибка получения погоды. Попробуй позже.")
    db.bump_stat('cmds')

def _to_english(text):
    latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
    if latin / max(len(text), 1) > 0.5:
        return text
    try:
        return _get_translator('en').translate(text)
    except Exception:
        return text

@client.on(events.NewMessage(pattern=r'!translate(?: ([a-z]{2}))? (.+)', func=owner_filter))
async def translate_cmd(e):

    target_lang = e.pattern_match.group(1) or 'ru'
    text = e.pattern_match.group(2).strip()
    msg = await respond(e, "⏳ Перевожу...")
    try:
        t = await asyncio.to_thread(_get_translator, target_lang)
        result = await asyncio.to_thread(t.translate, text)
        await msg.edit(f"🌐 **Перевод ({target_lang}):**\n\n{result}")
    except Exception as ex:
        await msg.edit(f"❌ Ошибка перевода: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!base64 (encode|decode) (.+)', func=owner_filter))
async def base64_cmd(e):

    mode, text = e.pattern_match.group(1), e.pattern_match.group(2).strip()
    try:
        if mode == 'encode':
            res = base64.b64encode(text.encode()).decode()
            await respond(e, f"🔐 **Base64 encode:**\n`{res}`")
        else:
            res = base64.b64decode(text.encode()).decode()
            await respond(e, f"🔓 **Base64 decode:**\n`{res}`")
    except Exception as ex:
        logger.error(f"base64 error: {ex}")
        await respond(e, "❌ Ошибка. Проверь данные.")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!hash (.+)', func=owner_filter))
async def hash_cmd(e):

    text = e.pattern_match.group(1).strip().encode()
    await respond(e, 
        f"#️⃣ **Хэши**\n\n"
        f"MD5:    `{hashlib.md5(text).hexdigest()}`\n"
        f"SHA1:   `{hashlib.sha1(text).hexdigest()}`\n"
        f"SHA256: `{hashlib.sha256(text).hexdigest()}`\n"
        f"SHA512: `{hashlib.sha512(text).hexdigest()[:64]}…`"
    )
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!morse (.+)', func=owner_filter))
async def morse_cmd(e):

    text = e.pattern_match.group(1).strip()
    await respond(e, f"📡 **Морзе:**\n_{text}_\n\n`{morse_enc(text)}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!caesar (encode|decode) (\d+) (.+)', func=owner_filter))
async def caesar_cmd(e):

    mode, shift, text = e.pattern_match.group(1), int(e.pattern_match.group(2)), e.pattern_match.group(3)
    res = caesar(text, shift, dec=(mode == 'decode'))
    await respond(e, f"{'🔒' if mode == 'encode' else '🔓'} **Цезарь (сдвиг {shift}):**\n_{text}_\n\n`{res}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!vigenere (encode|decode) (\S+) (.+)', func=owner_filter))
async def vigenere_cmd(e):

    mode, key, text = e.pattern_match.group(1), e.pattern_match.group(2), e.pattern_match.group(3)
    res = vigenere(text, key, dec=(mode == 'decode'))
    await respond(e, f"{'🔒' if mode == 'encode' else '🔓'} **Виженер (ключ: {key}):**\n_{text}_\n\n`{res}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!password(?:\s+(\d+))?(?:\s+(simple))?$', func=owner_filter))
async def password_cmd(e):

    length = max(4, min(int(e.pattern_match.group(1) or 16), 128))
    sym = not e.pattern_match.group(2)
    pwd = gen_pwd(length, sym)
    s = "🔴 Слабый" if length < 8 else "🟡 Средний" if length < 12 else "🟢 Сильный" if length < 20 else "💎 Очень сильный"
    await respond(e, f"🔑 **Пароль ({length} симв.)**\n\n`{pwd}`\n\nСила: {s}\nСимволы: {'✅' if sym else '❌'}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!qr (.+)', func=owner_filter))
async def qr_cmd(e):

    text = e.pattern_match.group(1).strip()
    msg = await respond(e, "⏳ Генерирую QR-код...")
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        path = os.path.join(MEDIA_DIR, f'qr_{int(time.time())}.png')
        img = await asyncio.to_thread(qrcode.make, text)
        await asyncio.to_thread(img.save, path)
        await client.send_file(e.chat_id, path,
            caption=f"📱 QR-код для:\n`{text[:80]}{'...' if len(text) > 80 else ''}`")
        await msg.delete()
        os.remove(path)
    except Exception as ex:
        await msg.edit(f"❌ Ошибка: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!uuid$', func=owner_filter))
async def uuid_cmd(e):

    ids = [str(uuid.uuid4()) for _ in range(5)]
    out = "\n".join(f"`{u}`" for u in ids)
    await respond(e, f"🆔 **Случайные UUID v4:**\n\n{out}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!color (.+)', func=owner_filter))
async def color_cmd(e):

    raw = e.pattern_match.group(1).strip().replace(' ', '')
    if raw.startswith('#'):
        h = raw.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        hex_val = raw.upper()
    else:
        raw = raw.removeprefix('rgb(').removesuffix(')')
        r, g, b = map(int, raw.split(','))
        hex_val = f"#{r:02X}{g:02X}{b:02X}"
    msg = await respond(e, "⏳ Генерирую образец цвета...")
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        path = os.path.join(MEDIA_DIR, f'color_{int(time.time())}.png')
        img = await asyncio.to_thread(Image.new, 'RGB', (300, 200), (r, g, b))
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        text_color = 'white' if brightness < 128 else 'black'
        draw = await asyncio.to_thread(ImageDraw.Draw, img)
        await asyncio.to_thread(draw.text, (10, 10), hex_val, fill=text_color)
        await asyncio.to_thread(img.save, path)
        await client.send_file(e.chat_id, path,
            caption=f"🎨 **{hex_val}**\nRGB: `rgb({r}, {g}, {b})`")
        await msg.delete()
        os.remove(path)
    except Exception as ex:
        await msg.edit(f"❌ Ошибка: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!ascii (.+)', func=owner_filter))
async def ascii_cmd(e):

    text = e.pattern_match.group(1).strip()
    codes = ' '.join(str(ord(c)) for c in text)
    back = ''.join(chr(int(x)) for x in codes.split())
    await respond(e, f"🔢 **ASCII коды:**\n_{text}_\n\n`{codes}`\n\nОбратно: `{back}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!type(?:\s+(fast|slow|matrix|glitch))?\s+(.+)', func=owner_filter))
async def type_cmd(e):

    mode = e.pattern_match.group(1) or 'normal'
    text = e.pattern_match.group(2).strip()
    if mode == 'fast':
        msg = await respond(e, "▌")
        for i in range(0, len(text), 2):
            chunk = text[:i + 2]
            await msg.edit(chunk + ("▌" if i + 2 < len(text) else ""))
            await asyncio.sleep(0.04)
        await msg.edit(text)
    elif mode == 'slow':
        msg = await respond(e, "▌")
        shown = ""
        for ch in text:
            shown += ch
            await msg.edit(shown + "▌")
            pause = 0.3 if ch in '.!?…' else 0.12 if ch in ',;:' else 0.07
            await asyncio.sleep(pause)
        await msg.edit(text)
    elif mode == 'matrix':
        CHARS = string.ascii_letters + string.digits + "@#%&"
        msg = await respond(e, "▓" * len(text))
        for step in range(len(text)):
            parts = list(text[:step])
            for _ in range(len(text) - step):
                parts.append(random.choice(CHARS))
            await msg.edit(''.join(parts))
            await asyncio.sleep(0.07)
        await msg.edit(text)
    elif mode == 'glitch':
        GLITCH = "░▒▓█▄▀■□▪▫"
        msg = await respond(e, "".join(random.choice(GLITCH) for _ in text))
        for _ in range(6):
            glitched = "".join(
                c if random.random() > 0.4 else random.choice(GLITCH)
                for c in text
            )
            await msg.edit(glitched)
            await asyncio.sleep(0.12)
        await msg.edit(text)
    else:
        msg = await respond(e, "▌")
        shown = ""
        for i, ch in enumerate(text):
            shown += ch
            if i % 2 == 0 or i == len(text) - 1:
                await msg.edit(shown + ("▌" if i < len(text) - 1 else ""))
                await asyncio.sleep(0.05)
        await msg.edit(text)
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!echo (.+)', func=owner_filter))
async def echo_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, e.pattern_match.group(1).strip())
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!bold (.+)', func=owner_filter))
async def bold_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, f"**{e.pattern_match.group(1).strip()}**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!italic (.+)', func=owner_filter))
async def italic_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, f"__{e.pattern_match.group(1).strip()}__")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!mono (.+)', func=owner_filter))
async def mono_cmd(e):

    await e.delete()
    await client.send_message(e.chat_id, f"`{e.pattern_match.group(1).strip()}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!clean(?:\s+(\d+))?$', func=owner_filter))
async def clean_cmd(e):

    limit = int(e.pattern_match.group(1) or 10)
    my_id = (await client.get_me()).id
    await e.delete()
    count = 0
    async for msg in client.iter_messages(e.chat_id, limit=limit):
        if msg.out or (msg.from_id and getattr(msg.from_id, 'user_id', None) == my_id):
            await msg.delete()
            count += 1
            await asyncio.sleep(0.1)
    info = await client.send_message(e.chat_id, f"✅ Удалено **{count}** своих сообщений")
    await asyncio.sleep(3)
    await info.delete()
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!purge(?:\s+(\d+))?$', func=owner_filter))
async def purge_cmd(e):

    limit = int(e.pattern_match.group(1) or 10)
    await e.delete()
    count = 0
    async for msg in client.iter_messages(e.chat_id, limit=limit):
        await msg.delete()
        count += 1
        await asyncio.sleep(0.04)
    info = await client.send_message(e.chat_id, f"⚠️ Удалено **{count}** сообщений")
    await asyncio.sleep(3)
    await info.delete()
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!spam (\d+) (.+)', func=owner_filter))
async def spam_cmd(e):

    count, text = int(e.pattern_match.group(1)), e.pattern_match.group(2).strip()
    MAX_SPAM = 50
    if count < 1 or count > MAX_SPAM:
        await respond(e, f"❌ Допустимо от 1 до {MAX_SPAM} сообщений.")
        return
    cooldown_key = f'spam_{e.chat_id}'
    remaining = command_cooldown.get(cooldown_key, 0) - time.time()
    if remaining > 0:
        await respond(e, f"⏳ Подождите {int(remaining)} сек перед повторным спамом.")
        return
    command_cooldown[cooldown_key] = time.time() + 30
    await e.delete()
    for _ in range(count):
        await client.send_message(e.chat_id, text)
        await asyncio.sleep(0.35)
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!forward (-?\d+)', func=owner_filter))
async def forward_cmd(e):

    if not e.reply_to_msg_id:
        await respond(e, "ℹ️ Ответьте на сообщение: `!forward [chat_id]`")
        return
    try:
        msg = await e.get_reply_message()
        await client.forward_messages(int(e.pattern_match.group(1)), msg)
        await respond(e, f"✅ Переслано в `{e.pattern_match.group(1)}`")
    except Exception as ex:
        await respond(e, f"❌ {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!pin$', func=owner_filter))
async def pin_cmd(e):

    if not e.reply_to_msg_id:
        await respond(e, "ℹ️ Ответьте на сообщение")
        return
    await (await e.get_reply_message()).pin(notify=False)
    await e.delete()
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!unpin$', func=owner_filter))
async def unpin_cmd(e):

    if e.reply_to_msg_id:
        await (await e.get_reply_message()).unpin()
    else:
        await client.unpin_message(e.chat_id)
    await e.delete()
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!copyall (\d+) (-?\d+)', func=owner_filter))
async def copyall_cmd(e):

    count, target = int(e.pattern_match.group(1)), int(e.pattern_match.group(2))
    await respond(e, f"⏳ Копирую {count} сообщений...")
    msgs = []
    async for m in client.iter_messages(e.chat_id, limit=count):
        msgs.append(m)
    msgs.reverse()
    copied = 0
    for m in msgs:
        try:
            await client.forward_messages(target, m)
            copied += 1
            await asyncio.sleep(0.4)
        except Exception:
            pass
    await respond(e, f"✅ Скопировано **{copied}/{count}** → `{target}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!react (.+)', func=owner_filter))
async def react_cmd(e):

    if not e.reply_to_msg_id:
        await respond(e, "ℹ️ Ответьте на сообщение: `!react 👍`")
        return
    emoji = e.pattern_match.group(1).strip()
    try:
        await client(SendReactionRequest(
            peer=e.chat_id,
            msg_id=e.reply_to_msg_id,
            reaction=[ReactionEmoji(emoticon=emoji)]
        ))
        await e.delete()
    except Exception as ex:
        await respond(e, f"❌ Не удалось поставить реакцию: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'^!save$', func=owner_filter))
async def save_media_cmd(e):

    if not e.reply_to_msg_id:
        await respond(e, "ℹ️ Ответьте на фото/видео или используйте `!save key value`")
        return
    replied = await e.get_reply_message()
    if not replied.media:
        await respond(e, "❌ В ответном сообщении нет медиа.")
        return
    os.makedirs(MEDIA_DIR, exist_ok=True)
    try:
        path = await replied.download_media(os.path.join(MEDIA_DIR, ''))
        name = os.path.basename(path) if path else 'unknown'
        db.set_saved(f'_media_{int(time.time())}', name)
        await respond(e, f"✅ **Сохранено:** `{name}`")
        logger.info(f"Media saved: {name}")
    except Exception as ex:
        await respond(e, f"❌ Ошибка сохранения: {ex}")
        logger.error(f"Save media error: {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!save (\S+) (.+)', func=owner_filter))
async def save_cmd(e):

    k, v = e.pattern_match.group(1), e.pattern_match.group(2)
    db.set_saved(k, v)
    await respond(e, f"✅ `{k}` = _{v}_")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!get (\S+)', func=owner_filter))
async def get_cmd(e):

    k = e.pattern_match.group(1)
    v = db.get_saved(k)
    await respond(e, f"📦 `{k}` = _{v}_" if v else f"❌ Ключ `{k}` не найден")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!del (\S+)', func=owner_filter))
async def del_cmd(e):

    k = e.pattern_match.group(1)
    v = db.get_saved(k)
    if v is not None:
        db.del_saved(k)
        await respond(e, f"🗑 Удалено: `{k}`")
    else:
        await respond(e, f"❌ `{k}` не найден")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!list$', func=owner_filter))
async def list_cmd(e):

    d = db.all_saved()
    if not d:
        await respond(e, "📭 Нет данных")
        db.bump_stat('cmds')
        return
    items = "\n".join(f"• `{k}` — _{v[:40]}{'…' if len(v) > 40 else ''}_" for k, v in d.items())
    await respond(e, f"📦 **Сохранено ({len(d)}):**\n\n{items}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!find (.+)', func=owner_filter))
async def find_cmd(e):

    query = e.pattern_match.group(1).strip().lower()
    saved_results = db.search_saved(query)
    notes_results = db.search_notes(query)
    lines = []
    if saved_results:
        lines.append(f"📦 **В сохранённом:**")
        for row in saved_results:
            lines.append(f"  • `{row['key']}` — _{row['value'][:40]}{'…' if len(row['value']) > 40 else ''}_")
    if notes_results:
        lines.append(f"📝 **В заметках:**")
        for row in notes_results:
            lines.append(f"  • `{row['key']}` — _{row['value'][:40]}{'…' if len(row['value']) > 40 else ''}_")
    if not lines:
        await respond(e, "🔍 **Ничего не найдено**")
    else:
        await respond(e, f"🔍 **Результаты поиска: {query}**\n\n" + "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!note (\S+)(?: (.+))?', func=owner_filter))
async def note_cmd(e):

    k = e.pattern_match.group(1)
    t = e.pattern_match.group(2) or ""
    if e.reply_to_msg_id:
        r = await e.get_reply_message()
        t = r.text or t
    if not t:
        await respond(e, "ℹ️ `!note <название> <текст>` или ответом")
        return
    db.set_note(k, t)
    await respond(e, f"📝 Заметка сохранена: `{k}`")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!getnote (\S+)', func=owner_filter))
async def getnote_cmd(e):

    k = e.pattern_match.group(1)
    v = db.get_note(k)
    if v is not None:
        await respond(e, f"📝 **{k}:**\n\n{v}")
    else:
        await respond(e, f"❌ Заметка `{k}` не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!delnote (\S+)', func=owner_filter))
async def delnote_cmd(e):

    k = e.pattern_match.group(1)
    v = db.get_note(k)
    if v is not None:
        db.del_note(k)
        await respond(e, f"🗑 Заметка удалена: `{k}`")
    else:
        await respond(e, f"❌ `{k}` не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!notes$', func=owner_filter))
async def notes_cmd(e):

    d = db.all_notes()
    if not d:
        await respond(e, "📭 Нет заметок")
        db.bump_stat('cmds')
        return
    items = "\n".join(f"• `{k}` — _{v[:40]}{'…' if len(v) > 40 else ''}_" for k, v in d.items())
    await respond(e, f"📝 **Заметки ({len(d)}):**\n\n{items}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!todo (.+)', func=owner_filter))
async def todo_add_cmd(e):

    task = e.pattern_match.group(1).strip()
    db.add_todo(task)
    todos = db.get_todos()
    await respond(e, f"✅ Задача добавлена: _{task}_\n📋 Всего: {len(todos)}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!todos$', func=owner_filter))
async def todos_cmd(e):

    todos = db.get_todos()
    if not todos:
        await respond(e, "📭 Список задач пуст")
        db.bump_stat('cmds')
        return
    lines = []
    for i, t in enumerate(todos, 1):
        mark = "✅" if t['done'] else "⬜"
        lines.append(f"{mark} {i}. _{t['text']}_")
    done = sum(1 for t in todos if t['done'])
    await respond(e, f"📋 **Список задач** ({done}/{len(todos)} выполнено):\n\n" + "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!done (\d+)', func=owner_filter))
async def done_cmd(e):

    idx = int(e.pattern_match.group(1)) - 1
    todos = db.get_todos()
    if 0 <= idx < len(todos):
        db.update_todo(todos[idx]['id'], done=True)
        await respond(e, f"✅ Выполнено: _{todos[idx]['text']}_")
    else:
        await respond(e, f"❌ Задача #{idx + 1} не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!undone (\d+)', func=owner_filter))
async def undone_cmd(e):

    idx = int(e.pattern_match.group(1)) - 1
    todos = db.get_todos()
    if 0 <= idx < len(todos):
        db.update_todo(todos[idx]['id'], done=False)
        await respond(e, f"⬜ Снята отметка: _{todos[idx]['text']}_")
    else:
        await respond(e, f"❌ Задача #{idx + 1} не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!deltodo (\d+)', func=owner_filter))
async def deltodo_cmd(e):

    idx = int(e.pattern_match.group(1)) - 1
    todos = db.get_todos()
    if 0 <= idx < len(todos):
        db.del_todo(todos[idx]['id'])
        await respond(e, f"🗑 Удалена задача: _{todos[idx]['text']}_")
    else:
        await respond(e, f"❌ Задача #{idx + 1} не найдена")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!afk(?:\s+(.+))?$', func=owner_filter))
async def afk_cmd(e):

    reason = (e.pattern_match.group(1) or '').strip()
    state.set_afk(reason)
    r = f"\n📝 _{reason}_" if reason else ""
    await respond(e, f"😴 **AFK включён**{r}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!unafk$', func=owner_filter))
async def unafk_cmd(e):

    dur = state.clear_afk()
    if dur is not None:
        await respond(e, f"☀️ **AFK выключен** | Отсутствовал: _{fmt_time(dur)}_")
    else:
        await respond(e, "ℹ️ AFK не был включён")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!chatinfo$', func=owner_filter))
async def chatinfo_cmd(e):

    chat = await e.get_chat()
    name = getattr(chat, 'title', None) or f"{getattr(chat, 'first_name', '')} {getattr(chat, 'last_name', '')}".strip()
    uname = getattr(chat, 'username', None)
    members = getattr(chat, 'participants_count', None)
    lines = [
        f"📊 **Информация о чате**\n",
        f"📛 **{name}**",
        f"🆔 `{e.chat_id}`",
    ]
    if uname:
        lines.append(f"🔖 @{uname}")
    else:
        lines.append("🔖 Username: нет")
    lines.append(f"👥 Тип: `{type(chat).__name__}`")
    if members:
        lines.append(f"👤 Участников: `{members}`")
    await respond(e, "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!members$', func=owner_filter))
async def members_cmd(e):

    try:
        p = await client.get_participants(e.chat_id)
        bots = sum(1 for x in p if x.bot)
        await respond(e, f"👥 **Участники**\n\nВсего: `{len(p)}`\n👤 Людей: `{len(p) - bots}`\n🤖 Ботов: `{bots}`")
    except Exception as ex:
        await respond(e, f"❌ {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!admins$', func=owner_filter))
async def admins_cmd(e):

    try:
        admins = await client.get_participants(e.chat_id, filter=ChannelParticipantsAdmins())
        lines = [f"👑 **Администраторы ({len(admins)}):**\n"]
        for a in admins[:25]:
            name = f"{a.first_name or ''} {a.last_name or ''}".strip()
            lines.append(f"• {name} — {'@' + a.username if a.username else '`' + str(a.id) + '`'}")
        await respond(e, "\n".join(lines))
    except Exception as ex:
        await respond(e, f"❌ {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!top(?:\s+(\d+))?$', func=owner_filter))
async def top_cmd(e):

    limit = int(e.pattern_match.group(1) or 200)
    await respond(e, "⏳ Анализирую...")
    cnt, names = defaultdict(int), {}
    async for msg in client.iter_messages(e.chat_id, limit=limit):
        if msg.sender_id:
            cnt[msg.sender_id] += 1
            if msg.sender_id not in names:
                s = await msg.get_sender()
                if s:
                    n = f"{getattr(s, 'first_name', '') or ''} {getattr(s, 'last_name', '') or ''}".strip()
                    names[msg.sender_id] = n or str(msg.sender_id)
    top = sorted(cnt.items(), key=lambda x: x[1], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = [f"🏆 **Топ активных** (из {limit} сообщ.):\n"]
    for i, (uid, c) in enumerate(top):
        lines.append(f"{medals[i]} {names.get(uid, uid)} — `{c}` сообщ.")
    await respond(e, "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!bots$', func=owner_filter))
async def bots_cmd(e):

    try:
        bots = await client.get_participants(e.chat_id, filter=ChannelParticipantsBots())
        lines = [f"🤖 **Боты в чате ({len(bots)}):**\n"]
        for b in bots[:20]:
            lines.append(f"• @{b.username or b.id}")
        await respond(e, "\n".join(lines))
    except Exception as ex:
        await respond(e, f"❌ {ex}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!resetdata$', func=owner_filter))
async def resetdata_cmd(e):

    db.clear_all()
    state.auto_reply_enabled = False
    state.auto_reply_text = '💫 Я автоответчик, хозяин скоро ответит! Спасибо за терпение 😘'
    state.ghost_mode = False
    state.afk_start_time = None
    state.afk_reason = ''
    state.sudo_users.clear()
    state._save()
    await respond(e, "🧹 **Все данные сброшены.**")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!ytshow\s+(.+)', func=owner_filter))
async def ytshow_cmd(e):

    raw = e.pattern_match.group(1).strip()
    parts = raw.rsplit(None, 1)
    if len(parts) == 2 and parts[1].isdigit():
        url = parts[0]
        height = int(parts[1])
    else:
        url = raw
        height = None

    status_msg = await respond(e, f"⏳ Загружаю ({'авто' if not height else f'{height}p'})...")

    async def edit_fn(text):
        try:
            await status_msg.edit(text)
        except Exception:
            pass

    filename = await run_download(edit_fn, url, mode='video', quality=height, timeout=600)
    if filename:
        await send_and_clean(edit_fn, client, e.chat_id, filename, f"🎬 YouTube: {url}")
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!dl\s+(.+)', func=owner_filter))
async def dl_cmd(e):

    url = e.pattern_match.group(1).strip()

    status_msg = await respond(e, "⏳ Загрузка...")

    async def edit_fn(text):
        try:
            await status_msg.edit(text)
        except Exception:
            pass

    try:
        filename = await run_download(edit_fn, url, mode='video', timeout=600)
        if filename:
            await send_and_clean(edit_fn, client, e.chat_id, filename)
    except Exception as ex:
        try:
            await status_msg.edit(f"❌ Ошибка: {ex}")
        except Exception:
            pass
        _log.error(f"dl error: {ex}")
    db.bump_stat('cmds')


@client.on(events.NewMessage(pattern=r'!playlist\s+(.+?)(?:\s+(\d+)(?:-(\d+))?)?$', func=owner_filter))
async def playlist_cmd(e):

    g = e.pattern_match
    url = g.group(1).strip()
    start_num = None
    end_num = None
    if g.group(2):
        start_num = int(g.group(2))
        end_num = int(g.group(3)) if g.group(3) else start_num

    msg = await respond(e, "⏳ Получаю информацию о плейлисте...")
    try:
        import yt_dlp

        def _get_playlist_info():
            opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                'cachedir': False,
                'extract_flat': True,
                'force_generic_extractor': False,
                'cookiefile': os.path.abspath(os.path.join(os.path.dirname(__file__), 'cookies.txt')),
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', '')
                entries = info.get('entries', [])
                video_urls = []
                for entry in entries:
                    if entry and entry.get('url'):
                        video_urls.append(entry['url'])
                    elif entry and entry.get('webpage_url'):
                        video_urls.append(entry['webpage_url'])
                    elif entry and entry.get('id'):
                        video_urls.append(f'https://youtube.com/watch?v={entry["id"]}')
                return title, video_urls

        title, video_urls = await asyncio.to_thread(_get_playlist_info)

        if not video_urls:
            await msg.edit("❌ Плейлист пуст или недоступен.")
            return

        total = len(video_urls)
        if start_num:
            s = max(1, start_num)
            e_idx = min(total, end_num) if end_num else min(total, s)
            selected = video_urls[s - 1:e_idx]
        else:
            selected = video_urls[:50]

        await msg.edit(f"📋 Плейлист: **{title or '?'}** ({len(selected)}/{total} видео)\n⏳ Начинаю загрузку...")

        for i, video_url in enumerate(selected, 1):
            vid_msg = await respond(e, f"⏳ [{i}/{len(selected)}] Загружаю видео {i}...")

            async def edit_vid(text, vm=vid_msg):
                try:
                    await vm.edit(text)
                except Exception:
                    pass

            filename = await run_download(edit_vid, video_url, mode='video', timeout=600)
            if filename:
                await send_and_clean(edit_vid, client, e.chat_id, filename, f"🎬 [{i}/{len(selected)}]")
                await asyncio.sleep(2)

        await respond(e, f"✅ **Плейлист загружен!** ({len(selected)}/{total} видео)")
    except Exception as ex:
        await respond(e, f"❌ Ошибка плейлиста: {ex}")
        _log.error(f"playlist error: {ex}")
    db.bump_stat('cmds')


async def safe_edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


@client.on(events.NewMessage(pattern=r'!audio\s+(.+)', func=owner_filter))
async def audio_cmd(e):

    url = e.pattern_match.group(1).strip()

    status_msg = await respond(e, "⏳ Загрузка аудио...")

    async def edit_fn(text):
        try:
            await status_msg.edit(text)
        except Exception:
            pass

    try:
        filename = await run_download(edit_fn, url, mode='audio', timeout=600)
        if filename:
            await send_and_clean(edit_fn, client, e.chat_id, filename, f"🎵 Аудио")
    except Exception as ex:
        await safe_edit(status_msg, f"❌ Ошибка: {ex}")
        _log.error(f"audio error: {ex}")
    db.bump_stat('cmds')


@client.on(events.NewMessage(pattern=r'!sub\s+(.+?)(?:\s+(\w{2}))?$', func=owner_filter))
async def sub_cmd(e):

    g = e.pattern_match
    url = g.group(1).strip()
    lang = (g.group(2) or 'ru').lower()

    msg = await respond(e, f"⏳ Ищу субтитры ({lang})...")
    try:
        def _get_captions():
            out_dir = os.path.join(MEDIA_DIR, 'subtmp')
            os.makedirs(out_dir, exist_ok=True)
            opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                'cachedir': False,
                'cookiefile': os.path.abspath(os.path.join(os.path.dirname(__file__), 'cookies.txt')),
                'writesubtitles': True,
                'subtitleslangs': [lang],
                'subtitlesformat': 'srt',
                'skip_download': True,
                'outtmpl': os.path.join(out_dir, '%(id)s'),
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                subs = info.get('subtitles') or info.get('requested_subtitles') or {}
                if lang not in subs:
                    for code in subs:
                        if code.startswith(lang):
                            lang_found = code
                            break
                    else:
                        return None
                else:
                    lang_found = lang
                sub_data = subs[lang_found]
                sub_url = None
                if isinstance(sub_data, list):
                    for entry in sub_data:
                        if entry.get('ext') == 'srt' and entry.get('url'):
                            sub_url = entry['url']
                            break
                    if not sub_url and sub_data and sub_data[0].get('url'):
                        sub_url = sub_data[0]['url']
                elif isinstance(sub_data, dict):
                    sub_url = sub_data.get('url')
                if sub_url:
                    r = requests.get(sub_url, timeout=30)
                    r.raise_for_status()
                    return r.text
                return None

        srt_content = await asyncio.to_thread(_get_captions)

        if srt_content:
            sub_path = os.path.join(MEDIA_DIR, f'sub_{lang}.srt')
            with open(sub_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            await msg.edit(f"📤 Отправляю субтитры ({lang})...")
            await client.send_file(e.chat_id, sub_path, caption=f"📝 Субтитры ({lang})")
            await asyncio.sleep(3)
            try:
                os.remove(sub_path)
            except OSError:
                pass
            await msg.edit(f"✅ Субтитры ({lang}) отправлены.")
        else:
            await msg.edit(f"❌ Субтитры ({lang}) не найдены для этого видео.")
    except Exception as ex:
        await msg.edit(f"❌ Ошибка: {ex}")
        logger.error(f"sub error: {ex}")
    db.bump_stat('cmds')


@client.on(events.NewMessage(pattern=r'!watch\s+(on|off)$', func=owner_filter))
async def watch_cmd(e):
    global _watch_task
    arg = e.pattern_match.group(1)
    if arg == 'on':
        if _watch_task and not _watch_task.done():
            await respond(e, "⚠️ Мониторинг уже запущен.")
            return
        db.clear_sessions()
        try:
            result = await client(GetAuthorizationsRequest())
            for auth in result.authorizations:
                h = hashlib.md5(f"{auth.hash}{auth.device_model}{auth.platform}".encode()).hexdigest()
                db.save_session(h, json.dumps({"device": auth.device_model, "platform": auth.platform, "ip": auth.ip, "date": str(auth.date_created)}))
        except Exception as ex:
            logger.warning(f"Init sessions: {ex}")

        async def monitor():
            while True:
                try:
                    result = await client(GetAuthorizationsRequest())
                    known = db.all_sessions()
                    for auth in result.authorizations:
                        h = hashlib.md5(f"{auth.hash}{auth.device_model}{auth.platform}".encode()).hexdigest()
                        if h not in known:
                            db.save_session(h, json.dumps({"device": auth.device_model, "platform": auth.platform, "ip": auth.ip, "date": str(auth.date_created)}))
                            me = await client.get_me()
                            await client.send_message(me.id, f"⚠️ **Новый вход**\nУстройство: {auth.device_model}\nПлатформа: {auth.platform}\nIP: {auth.ip}\nДата: {auth.date_created}")
                            logger.warning(f"New session: {auth.device_model} {auth.ip}")
                except Exception as ex:
                    logger.error(f"Watch error: {ex}")
                await asyncio.sleep(300)

        _watch_task = asyncio.create_task(monitor())
        await respond(e, "👁️ **Мониторинг сессий ВКЛЮЧЁН.** Проверка каждые 5 мин.")
    else:
        if _watch_task and not _watch_task.done():
            _watch_task.cancel()
            _watch_task = None
        await respond(e, "👁️ **Мониторинг сессий ВЫКЛЮЧЕН.**")
    db.bump_stat('cmds')


@client.on(events.NewMessage(pattern=r'!check_email\s+(\S+)', func=owner_filter))
async def check_email_cmd(e):

    email = e.pattern_match.group(1).strip().lower()
    msg = await respond(e, f"🔍 Проверяю {email}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://api.xposedornot.com/v1/check-email/{email}',
                params={'details': 'true'},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 404:
                    await msg.edit(f"✅ **{email}** не найден в известных утечках.")
                elif resp.status == 200:
                    data = await resp.json()
                    breaches = data.get('breaches', [])
                    if not breaches:
                        await msg.edit(f"✅ **{email}** не найден в известных утечках.")
                        return
                    lines = [f"⚠️ **{email}** найден в {len(breaches)} утечках:\n"]
                    for b in breaches[:15]:
                        name = b.get('Name', b) if isinstance(b, dict) else b
                        date = b.get('BreachDate', '') if isinstance(b, dict) else ''
                        lines.append(f"• {name}" + (f" ({date})" if date else ""))
                    if len(breaches) > 15:
                        lines.append(f"… и ещё {len(breaches) - 15}")
                    await msg.edit("\n".join(lines))
                elif resp.status == 429:
                    await msg.edit("❌ Слишком много запросов. Лимит: 100/день на IP.")
                else:
                    await msg.edit(f"❌ Ошибка API: HTTP {resp.status}")
    except asyncio.TimeoutError:
        await msg.edit("❌ Таймаут запроса к API.")
    except Exception as ex:
        await msg.edit(f"❌ Ошибка: {ex}")
        logger.error(f"check_email error: {ex}")
    db.bump_stat('cmds')


@client.on(events.NewMessage(pattern=r'!protect\s+(on|off)$', func=owner_filter))
async def protect_cmd(e):
    global _protect_task
    arg = e.pattern_match.group(1)
    if arg == 'on':
        if _protect_task and not _protect_task.done():
            await respond(e, "⚠️ Защита уже включена.")
            return
        dialogs = await client.get_dialogs(limit=1000)
        db.clear_protected_chats()
        for d in dialogs:
            db.add_protected_chat(d.id)
        await respond(e, f"🔒 **Защита ВКЛЮЧЕНА.** Отслеживается {len(dialogs)} чатов.")

        async def monitor():
            while True:
                try:
                    current = {d.id for d in await client.get_dialogs(limit=1000)}
                    protected = set(db.get_protected_chat_ids())
                    missing = protected - current
                    for cid in missing:
                        me = await client.get_me()
                        await client.send_message(me.id, f"⚠️ **Удалён чат**\nID: `{cid}`\nЧат был удалён или вы из него вышли.")
                        db.del_protected_chat(cid)
                except Exception as ex:
                    logger.error(f"Protect monitor error: {ex}")
                await asyncio.sleep(120)

        _protect_task = asyncio.create_task(monitor())
    else:
        if _protect_task and not _protect_task.done():
            _protect_task.cancel()
            _protect_task = None
        db.clear_protected_chats()
        await respond(e, "🔓 **Защита ВЫКЛЮЧЕНА.**")
    db.bump_stat('cmds')


@client.on(events.NewMessage(func=lambda e: e.is_private))
async def private_handler(event):
    global reply_cooldown
    sender = await event.get_sender()
    if not sender:
        return

    _log.info(f"📩 [ЛС] От {sender.first_name} (id:{sender.id})")
    if event.reply_to_msg_id:
        _log.info(f"↩️ Ответ на сообщение ID:{event.reply_to_msg_id}")

    uid = sender.id
    now = time.time()

    if len(reply_cooldown) > MAX_COOLDOWN_ENTRIES:
        cutoff = now - 3600
        reply_cooldown = {k: v for k, v in reply_cooldown.items() if v > cutoff}

    if state.mute_enabled:
        logger.info(f"🔇 Mute — игнорирую {uid}")
        return

    if state.lock_enabled:
        try:
            me = await client.get_me()
            if uid == me.id:
                pass
            else:
                is_contact = db.get_saved(f'_lock_cache_{uid}')
                if is_contact is None:
                    is_contact = '0'
                    try:
                        contact = await client.get_entity(uid)
                        if getattr(contact, 'contact', False):
                            is_contact = '1'
                    except Exception:
                        pass
                    if is_contact == '0':
                        try:
                            common = await client.get_common_chats(uid)
                            if common:
                                is_contact = '1'
                        except Exception:
                            pass
                    db.set_saved(f'_lock_cache_{uid}', is_contact)
                if is_contact == '0':
                    logger.info(f"🔒 Lock: {uid} не контакт и нет общих чатов — игнорирую")
                    return
        except Exception as ex:
            logger.warning(f"Lock check error for {uid}: {ex}")

    silent_mode = state.silent_enabled

    if state.readreceipt_enabled:
        try:
            await client.send_read_acknowledge(event.chat_id, event.message)
        except Exception:
            pass

    if event.reply_to_msg_id and not event.out:
        try:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.sender_id:
                raw_text = event.raw_text.strip()
                lines = raw_text.split('\n', 1)
                cmd_part = lines[0].strip().lower()
                custom_reply = lines[1].strip() if len(lines) > 1 else None
                if cmd_part in RP_COMMANDS:
                    target_entity = await client.get_entity(reply_msg.sender_id)
                    target_name = target_entity.first_name or "пользователь"
                    user_name = sender.first_name or "Кто-то"
                    action_text = format_rp_action(cmd_part, user_name, target_name)
                    reply_text = custom_reply or get_rp_reply(cmd_part)
                    if state.typing_enabled:
                        async with client.action(event.chat_id, 'typing'):
                            await asyncio.sleep(0.8)
                    sent = await safe_flood(lambda: event.reply(f"{action_text}\n{reply_text}"))
                    logger.info(f"✅ RP (in): {user_name} -> {target_name} ({cmd_part})")
                    if state.ghost_mode or state.shadow_enabled:
                        asyncio.create_task(shadow_delete_msg(sent))
                    if state.autodel_enabled:
                        asyncio.create_task(shadow_delete_msg(sent, state.autodel_delay))
                    db.bump_stat('cmds')
                    return
        except Exception as e:
            logger.error(f"RP error (in): {e}")

    if state.afk_start_time and now - reply_cooldown.get(f'afk_{uid}', 0) > 60:
        if silent_mode:
            logger.info(f"🔇 Silent — AFK ответ скрыт для {uid}")
        else:
            dur = fmt_time(now - state.afk_start_time)
            reason_part = f"\n📝 _{state.afk_reason}_" if state.afk_reason else ""
            reply_cooldown[f'afk_{uid}'] = now
            if state.typing_enabled:
                async with client.action(event.chat_id, 'typing'):
                    await asyncio.sleep(0.8)
            sent = await safe_flood(lambda: event.reply(f"😴 Хозяин AFK уже **{dur}**{reason_part}"))
            if state.ghost_mode or state.shadow_enabled:
                asyncio.create_task(shadow_delete_msg(sent))
            if state.autodel_enabled:
                asyncio.create_task(shadow_delete_msg(sent, state.autodel_delay))

    if state.auto_reply_enabled and now - reply_cooldown.get(uid, 0) > 10:
        reply_text = db.get_reply_text(uid)
        if reply_text is None:
            reply_text = db.get_default_reply()
        if reply_text is None:
            reply_text = state.auto_reply_text if state.auto_reply_text else None
        if reply_text and not silent_mode:
            reply_cooldown[uid] = now
            if state.reply_delay:
                await asyncio.sleep(state.reply_delay)
            if state.typing_enabled:
                async with client.action(event.chat_id, 'typing'):
                    await asyncio.sleep(0.8)
            sent = await safe_flood(lambda: event.reply(reply_text))
            if state.ghost_mode or state.shadow_enabled:
                asyncio.create_task(shadow_delete_msg(sent))
            if state.autodel_enabled:
                asyncio.create_task(shadow_delete_msg(sent, state.autodel_delay))
        elif silent_mode:
            logger.info(f"🔇 Silent — автоответ скрыт для {uid}")

async def safe_flood(coro_factory, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except FloodWaitError as e:
            logger.warning(f"FloodWait: {e.seconds}s, попытка {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(e.seconds + 1)
            else:
                raise


async def shadow_delete_msg(msg, delay=None):
    d = delay or state.shadow_delay or 5
    await asyncio.sleep(d)
    try:
        await msg.delete()
    except Exception:
        pass

@client.on(events.NewMessage(outgoing=True, func=lambda e: e.is_private and e.reply_to_msg_id))
async def rp_outgoing_handler(event):
    if event.sender_id != OWNER_ID and event.sender_id not in state.sudo_users:
        return
    try:
        reply_msg = await event.get_reply_message()
        if not reply_msg or not reply_msg.sender_id:
            return
        raw_text = event.raw_text.strip()
        lines = raw_text.split('\n', 1)
        cmd_part = lines[0].strip().lower()
        if cmd_part not in RP_COMMANDS:
            return
        custom_reply = lines[1].strip() if len(lines) > 1 else None
        target_entity = await client.get_entity(reply_msg.sender_id)
        target_name = target_entity.first_name or "пользователь"
        me = await client.get_me()
        user_name = me.first_name or "Кто-то"
        action_text = format_rp_action(cmd_part, user_name, target_name)
        reply_text = custom_reply or get_rp_reply(cmd_part)
        if state.typing_enabled:
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(0.8)
        sent = await safe_flood(lambda: event.reply(f"{action_text}\n{reply_text}"))
        logger.info(f"✅ RP: {user_name} -> {target_name} ({cmd_part}) | реплика: {'кастом' if custom_reply else 'рандом'}")
        if state.ghost_mode or state.shadow_enabled:
            asyncio.create_task(shadow_delete_msg(sent))
        if state.autodel_enabled:
            asyncio.create_task(shadow_delete_msg(sent, state.autodel_delay))
        db.bump_stat('cmds')
    except Exception as e:
        logger.error(f"RP error: {e}")

@client.on(events.NewMessage(pattern=r'^!rphelp$', func=lambda e: e.is_private))
async def rphelp_cmd(event):
    sender = await event.get_sender()
    if not sender:
        return
    lines = ["📚 **Доступные RP-команды**\n"]
    for category in get_all_categories():
        cmds = get_category_commands(category)
        if cmds:
            lines.append(f"\n**{category.upper()}**: {', '.join(f'`{c}`' for c in cmds)}")
    await event.reply("\n".join(lines))
    db.bump_stat('cmds')

import help_data

if __name__ == "__main__":
    import threading
    print("🚀 Запуск UserBot...")
    os.makedirs(MEDIA_DIR, exist_ok=True)
    threading.Thread(target=run_web, daemon=True).start()
    client.start()
    print("✅ Бот запущен!")
    client.run_until_disconnected()
