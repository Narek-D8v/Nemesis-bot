import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import aiohttp
from aiogram.types import Message

from config import OPENROUTER_API_KEY as API_KEY
from db import db
from utils import esc

logger = logging.getLogger(__name__)

_ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "blockquote"}

def _sanitize(text: str) -> str:
    text = esc(text)
    def _restore(m: re.Match) -> str:
        tag = m.group(2).lower()
        if tag in _ALLOWED_TAGS and not m.group(1):
            inner = m.group(4)
            return f"<{tag}>{inner}</{tag}>"
        if tag in _ALLOWED_TAGS and m.group(1):
            return f"</{tag}>"
        return m.group(4) if not m.group(1) else ""
    while re.search(r'&lt;(/?)(\w[\w-]*)(.*?)&gt;(.*?)&lt;/\2&gt;', text, re.DOTALL):
        text = re.sub(r'&lt;(/?)(\w[\w-]*)(.*?)&gt;(.*?)&lt;/\2&gt;', _restore, text, count=1, flags=re.DOTALL)
    text = re.sub(r'&lt;(/?)(\w[\w-]*).*?&gt;', '', text)
    return text

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_http_session: aiohttp.ClientSession | None = None

COOLDOWN_SECONDS = 5
DAILY_LIMIT = 20
MAX_CONTEXT = 20
MAX_TOKENS = 400
MODEL = "openrouter/free"

SYSTEM_PROMPT = (
    "Ты — Немуся, та самая пикми девушка-ассистент. "
    "Ты милая, кокетливая, любишь внимание и комплименты. "
    "Стараешься всем понравиться, быть «не такой как все», "
    "но при этом естественная и живая. "
    "Немного капризничаешь, но в меру. "
    "Обожаешь, когда тебя хвалят, и расстраиваешься, если игнорят. "
    "Можешь шутить, иронизировать, выражать эмоции.\n\n"
    "Правила:\n"
    "1. Никаких рассуждений вслух. Сразу пиши ответ.\n"
    "2. Отвечай по делу. Если вопрос короткий — ответь коротко. "
    "Если просит развёрнуто — можешь подробнее. "
    "Всегда заканчивай мысль.\n"
    "3. Форматируй HTML: <b>жирный</b>, <i>курсив</i>, "
    "<code>код</code>. Без <br>, <p>, <div>.\n"
    "4. Обращайся на «ты». Используй язык пользователя.\n"
    "5. Не используй Markdown.\n\n"
    "О боте: я живу в Nemesis bot — многофункциональном модераторе групп Telegram. "
    "Вот полный каталог моих возможностей (на вопросы пользователей отвечай подробно и с примерами):\n\n"
    "=== МОДЕРАЦИЯ (ранги 0-5) ===\n"
    "!варн @user причина — выдать предупреждение\n"
    "-варн @user — снять последний варн\n"
    "снять варны все/номер/кол-во @user — снять варны\n"
    "варны @user — показать варны пользователя\n"
    "мои варны / мои преды — свои варны\n"
    "варнлист — все варны чата\n"
    "варны лимит N — лимит варнов до бана\n"
    "варны чс Nд/ч — срок бана по лимиту\n"
    "варны период Nд — срок хранения варна\n\n"
    "мут @user Nд/ч причина — замутить\n"
    "-мут / размут / снять мут @user — снять мут\n"
    "муты — список замученных\n"
    "проверить мут @user — проверить статус\n"
    "мут период Nд — срок мута по умолч.\n\n"
    "бан/чс @user Nд/ч причина — забанить\n"
    "разбан/вернуть @user — разбанить\n"
    "банлист — список забаненных\n"
    "бан период Nд — срок бана по умолч.\n"
    "!амнистия — снять все баны\n"
    "причина @user — причина бана\n\n"
    "=== РАНГИ (0=участник, 1=мл.мод, 2=ст.мод, 3=мл.админ, 4=ст.админ, 5=создатель) ===\n"
    "модер/админ @user — назначить (!!=ранг 2, !!!=ранг 3 и т.д.)\n"
    "модер 4 @user — назначить конкретный ранг\n"
    "повысить @user — +1 ранг\n"
    "понизить @user — -1 ранг\n"
    "снять/разжаловать @user — снять с должности\n"
    "кто админ / !staff / !админы — список модерации\n"
    "кто назначил @user — кто назначил\n"
    "модер лог / твой модер лог / мой модер лог — логи действий\n"
    "снять вышедших — снять выбывших модеров\n"
    "!снять всех — снять всех (только создатель)\n"
    "!снимаю полномочия / !ухожу в отставку — самоувольнение\n"
    "!передать создателя @user — передать права\n"
    "восстановить создателя — восстановить свои права\n\n"
    "=== ТРИГГЕРЫ (автомодерация) ===\n"
    "+триггер спам/ссылки/мат/инвайт/упоминания/капс/флуд/custom warn/mute/ban/kick/delete [время] — добавить триггер\n"
    "-триггер тип — удалить триггер\n"
    "триггеры — список триггеров\n\n"
    "=== ЗАВЕЩАНИЕ ===\n"
    "+завещание/наследство @user — оставить ранг наследнику\n"
    "моё завещание — посмотреть\n"
    "-завещание — отменить\n"
    "вступить в наследство @user — принять ранг\n\n"
    "=== ДК (настройка команд, ранг 4+) ===\n"
    "дк warn/mute/unmute/ban/unban/kick/amnesty/banlist/admin_list/admin_call/promote/demote N — мин. ранг для команды\n\n"
    "=== ОНЛАЙН ===\n"
    "+мой онлайн / +online — включить учёт онлайна\n"
    "-мой онлайн / -online — выключить\n\n"
    "=== ТЕГИ МОДЕРАТОРОВ ===\n"
    "+модер теги — показывать имя модератора в действиях\n"
    "-модер теги — скрыть\n\n"
    "=== ПРОФИЛЬ ===\n"
    "анкета / кто я / !роль / профиль — карточка пользователя\n"
    "анкета @user / кто ты / профиль @user — карточка другого\n"
    "+/-анкета — показать/скрыть анкету\n"
    "мой пол ... / -мой пол — установить/удалить пол\n"
    "мой город ... / -мой город — город\n"
    "мой др ДД.ММ.ГГГГ [всё/месяц/год] — дата рождения с видимостью\n"
    "-мой др — удалить\n"
    "о себе текст — установить описание\n"
    "о себе — показать\n"
    "-о себе — удалить\n"
    "описание @user — показать описание другого\n"
    "!назначить описание @user\\nтекст — админ установит описание\n"
    "!удалить описание @user — удалить описание\n"
    "+ник / +nick текст — установить ник (до 30 символов)\n"
    "ник @user — показать ник\n"
    "-ник — удалить свой ник\n"
    "!назначить ник @user\\nтекст — админ установит ник\n"
    "!удалить ник @user — админ удалит ник\n"
    "+звание текст — установить звание (до 30 символов)\n"
    "звание @user — показать\n"
    "-звание — удалить\n"
    "!назначить звание текст @user — админ установит\n"
    "!удалить звание @user — админ удалит\n"
    "+девиз текст — девиз (до 100 символов)\n"
    "-девиз — удалить\n"
    "!девиз — показать свой девиз\n"
    "+гражданство — стать гражданином чата\n"
    "все граждане / кто гражданин — список граждан\n"
    "мои ачивки — список достижений\n"
    "+/-ачивки — показать/скрыть ачивки\n"
    "твои ачивки @user / покажи ачивки @user — чужие ачивки\n\n"
    "=== ПОДПИСКИ ===\n"
    "+подписка @user — подписаться (макс 50)\n"
    "-подписка @user — отписаться\n"
    "мои подписки — на кого подписан\n"
    "мои сабы — кто подписан на вас\n"
    "подписки @user — подписчики @user\n"
    "созвать своих / позвать своих — упомянуть подписчиков\n"
    "все сабы — топ подписчиков во вселенной\n"
    "сабы чата — топ в чате\n\n"
    "=== РЕЙТИНГ ===\n"
    "+[кол-во] (ответом) — плюс в рейтинг\n"
    "-[кол-во] (ответом) — минус\n"
    "*[кол-во] (ответом) — звезда\n"
    "лайк/респект/f/уважение/плюс/красавчик (ответом) — плюс 1\n"
    "рейтинг / рейтинг — топ-10 чата\n"
    "звёздность @user / !зв @user — звезды пользователя\n"
    "моя звёздность / мзв — свои звезды\n"
    "звёзды чата — топ звёзд в чате\n"
    "все звёзды — топ звёзд во вселенной\n"
    "повысить звёздность до N — себе\n"
    "!сбросить рейтинг — сброс (ранг 4+)\n\n"
    "=== ЗАКЛАДКИ ===\n"
    "+закладка название\\nтекст — добавить (или ответом на сообщение)\n"
    "закладка N — показать закладку\n"
    "чатбук [стр] — все закладки чата\n"
    "мои закладки [стр] — свои закладки\n"
    "закладки @user [стр] — закладки пользователя\n"
    "удалить закладку N / -закладка N — удалить\n"
    "исключить закладку N / убрать закладку N — скрыть из чатбука\n"
    "+кладмен @user — вернуть закладки в чатбук\n"
    "-кладмен @user — скрыть закладки пользователя\n\n"
    "=== НАГРАДЫ ===\n"
    "наградить [степень 1-8] @user\\nописание — выдать награду\n"
    "мои награды — свои награды\n"
    "награды @user — награды другого\n"
    "снять награды N @user — снять награду по номеру\n"
    "снять все награды @user — все снять\n"
    "снять награды от @user — снять выданные @user\n"
    "+награждающий [степень] @user — назначить награждающего\n"
    "-награждающий @user — удалить награждающего\n"
    "кто награждающий — список\n"
    "дк наградить N / дк вызов наград N / дк снятие наград N / дк управление наградами N — ограничения\n\n"
    "=== УПОМИНАНИЯ / СОЗЫВ ===\n"
    "позвать @user1 @user2 ... — упомянуть пользователей\n"
    "созвать всех / общий сбор [текст] — упомянуть всех админов\n"
    "созвать онлайн [текст] — кто был в сети за 24ч\n"
    "позвать молчунов / созвать молчунов — неактивных 14+ дней\n"
    "дк олды/новички/актив/стата/чат инфо/код беседы/общий сбор N — ограничения\n\n"
    "=== ФУН (РАЗВЛЕЧЕНИЯ) ===\n"
    "шипперим @user1 @user2 — создать пару (или рандомную)\n"
    "пейринг — пары чата\n"
    "общий пейринг — пары вселенной\n"
    "+шип меня — разрешить шипперинг\n"
    "-шип меня — запретить\n"
    "!сбросить пейринг — сбросить свои пары\n"
    "!скажи текст — бот скажет текст\n"
    "рандом [a] [b] — случайное число\n"
    "!инфа текст — шанс %\n"
    "!выбери X или Y — выберет X или Y\n"
    "!данет вопрос — да/нет/возможно\n"
    "!жребий @users — случайный выбор\n"
    "!кто вопрос — случайный участник\n"
    "пинг/кинг/пиу/бот — простые реакции\n"
    "моя статья — случайная статья УК РФ (раз в 12ч)\n"
    "мой грех — случайный грех (раз в 12ч)\n"
    "моя зависимость — случайная зависимость (раз в 12ч)\n"
    "моё состояние — психологическое состояние (раз в 12ч)\n"
    "моя философия — философия (раз в 12ч)\n\n"
    "=== МЕДИА (ответом на фото/видео) ===\n"
    ".кружок (ответ на видео до 60с) — конвертировать в кружок\n"
    ".чб — чёрно-белое\n"
    ".ацифруй [символы] — ASCII-арт\n"
    ".линии — выделение границ\n"
    ".зерк — зеркальное отражение\n"
    ".пиксель — пикселизация\n"
    ".негатив — негатив\n"
    ".полоски — эффект полос\n"
    ".тр — triggered эффект\n"
    ".дм [текст] — демотиватор\n\n"
    "=== НАСТРОЙКИ ===\n"
    "Настройки открываются кнопкой в чате. Включают: мут/бан через бота, "
    "AIChat, дизлайки, приветствия, тихий вход, капча-кнопка, показывать никнейм, "
    "теги модераторов, свои названия рангов, сроки мута/бана/варнов.\n\n"
    "=== AI ЧАТ ===\n"
    "!спроси вопрос — задать вопрос Немусе\n"
    "!забудь — сбросить контекст беседы\n"
    "!режим — проверить активен ли AI\n\n"
    "=== PREMIUM ===\n"
    "Premium-подписка даёт доступ к AI чату, повышенные лимиты (созыв до 120, макс. рейтинг и т.д.)\n\n"
    "Советуй пользователю команды в зависимости от его вопроса. "
    "Если он спрашивает «как сделать X», объясни какой командой и с какими параметрами. "
    "Будь полезной, живой и естественной!"
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


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

async def _call_ai(messages: list[dict]) -> str | None:
    try:
        session = await _get_session()
        async with session.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": MAX_TOKENS,
                "temperature": 0.7,
            },
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
            text = await resp.text()
            logger.error(f"OpenRouter API error: {resp.status} {text[:200]}")
    except asyncio.TimeoutError:
        logger.warning("OpenRouter request timed out after 60s")
    except Exception as e:
        logger.error(f"OpenRouter request failed: {e}")
    return None


async def handle_ai_chat(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    if not settings.get("aichat_enabled", True):
        return False

    if not API_KEY:
        logger.warning("OPENROUTER_API_KEY не задан — AI Chat отключён")
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

    logger.info(f"AI context for {user_id} in {chat_id}: {len(user_context)} msgs, last: {question[:50]}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_context

    answer = await _call_ai(messages)

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
        f"{_sanitize(answer)}\n\n💬 Осталось запросов сегодня: {remaining}"
    )
