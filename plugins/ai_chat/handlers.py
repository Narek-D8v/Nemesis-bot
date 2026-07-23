import asyncio
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
from aiogram.types import Message

from db import db
from utils import esc

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.getenv("OPENROUTER_API_KEY", "")

COOLDOWN_SECONDS = 5
DAILY_LIMIT = 20
MAX_CONTEXT = 20
MAX_TOKENS = 200
MODEL = "openrouter/free"

SYSTEM_PROMPT = (
    "Ты — Немуся, полезный ассистент. "
    "Отвечай максимально кратко, без приветствий и лишних слов. Только суть. "
    "Используй язык пользователя."
)

context: dict[int, dict[int, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
last_used: dict[int, dict[int, float]] = defaultdict(dict)
daily_usage: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
auto_mode: dict[int, bool] = {}

AI_CMD = re.compile(r'^!спроси\s+(.+)', re.DOTALL)
FORGET_CMD = re.compile(r'^!забудь\s*$')
MODE_CMD = re.compile(r'^!режим\s*$')


def _get_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_user_link(message: Message) -> str:
    user = message.from_user
    name = esc(user.first_name or "Пользователь")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _check_premium(chat_id: int, user_id: int) -> bool:
    return await db.is_premium_group(chat_id) or await db.is_premium_user(user_id)


def _call_ai(messages: list[dict]) -> str | None:
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": MAX_TOKENS,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        pass
    return None


async def handle_ai_chat(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    if not API_KEY:
        return False

    stripped = text.strip()

    # !забудь
    if FORGET_CMD.match(stripped):
        if user_id in context[chat_id]:
            del context[chat_id][user_id]
        user_link = _get_user_link(message)
        await message.reply(f"🧹 {user_link} контекст диалога сброшен.")
        return True

    # !режим
    if MODE_CMD.match(stripped):
        current = auto_mode.get(chat_id, False)
        auto_mode[chat_id] = not current
        status = "включён" if auto_mode[chat_id] else "выключен"
        user_link = _get_user_link(message)
        await message.reply(f"🤖 {user_link} режим автоответа {status}.")
        return True

    # !спроси ...
    m = AI_CMD.match(stripped)
    if m:
        question = m.group(1).strip()
        if question:
            await _process_ai_request(message, chat_id, user_id, question)
        return True

    # Auto-mode: reply to bot message
    if not auto_mode.get(chat_id):
        return False
    if not message.reply_to_message:
        return False
    if not message.reply_to_message.from_user or not message.reply_to_message.from_user.is_bot:
        return False
    if message.reply_to_message.from_user.id != message.bot.id:
        return False

    await _process_ai_request(message, chat_id, user_id, text)
    return True


async def _process_ai_request(message: Message, chat_id: int, user_id: int, question: str) -> None:
    if not await _check_premium(chat_id, user_id):
        await message.reply(
            f"😌 {_get_user_link(message)} эта команда доступна только с премиумом!"
        )
        return

    last = last_used[user_id].get(chat_id, 0)
    if time.time() - last < COOLDOWN_SECONDS:
        user_link = _get_user_link(message)
        await message.reply(f"⏳ {user_link} подожди немного перед следующим запросом.")
        return

    today = _get_today()
    if daily_usage[user_id][today] >= DAILY_LIMIT:
        user_link = _get_user_link(message)
        await message.reply(
            f"😌 {user_link} ты исчерпал лимит запросов на сегодня ({DAILY_LIMIT})."
        )
        return

    user_link = _get_user_link(message)
    thinking_msg = await message.reply(f"⏳ {user_link} думаю...")

    user_context = context[chat_id][user_id]
    user_context.append({"role": "user", "content": question})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_context

    answer = await asyncio.to_thread(_call_ai, messages)

    if answer is None:
        await thinking_msg.edit_text(f"😔 {user_link} ошибка при обращении к AI. Попробуй позже.")
        return

    user_context.append({"role": "assistant", "content": answer})
    if len(user_context) > MAX_CONTEXT * 2:
        context[chat_id][user_id] = user_context[-(MAX_CONTEXT * 2):]

    last_used[user_id][chat_id] = time.time()
    daily_usage[user_id][today] += 1

    remaining = DAILY_LIMIT - daily_usage[user_id][today]
    await thinking_msg.edit_text(
        f"🤖 {answer}\n\n💬 Осталось запросов сегодня: {remaining}"
    )
