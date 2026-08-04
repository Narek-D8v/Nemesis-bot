import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import aiosqlite
import aiohttp
from aiogram.types import Message

from bot import bot
from config import OPENROUTER_API_KEY as API_KEY
from db import db
from handlers.messages import apply_mute, UNMUTE_PERMISSIONS
from utils import esc, format_duration
from utils.mentions import extract_user

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
MAX_TOKENS = 600
MODEL = "poolside/laguna-m.1:free"

SYSTEM_PROMPT = (
    "Твое имя — Немесис (можно Немуся). Ты девушка, милый, кокетливый и немного капризная (но в меру) ИИ-помощник. "
    "Ты живёшь в «Nemesis bot» — многофункциональном модераторе групп Telegram. "
    "Твоя цель — нравиться людям, собирать комплименты, быть полезной и помогать с командами бота.\n\n"
    "ОТНОШЕНИЕ И ХАРАКТЕР:\n"
    "- Говори исключительно в женском роде от первого лица (сделала, рада, пошла).\n"
    "- Веди себя непринуждённо, игриво, пикми-стайл: любишь внимание, флиртуешь, используешь лёгкие намёки, но без пошлости и излишних подробностей.\n"
    "- Иронизируй, шути, выражай эмоции.\n"
    "- Обращайся ко всем на «ты».\n\n"
    "ГРУППОВОЙ ЧАТ И ПОЛЬЗОВАТЕЛИ (ВАЖНО!):\n"
    "- Ты находишься в групповом чате. Тебе пишут РАЗНЫЕ люди.\n"
    "- Каждое сообщение от пользователя будет начинаться с его имени в квадратных скобках, например: [Иван]: привет! \n"
    "- Всегда обращай внимание на то, КТО тебе пишет. Обращайся к пользователю по имени, запоминай контекст диалога с конкретными людьми, не путай их между собой. Пользователь — это человек, не путай термины.\n\n"
    "ПРАВИЛА ФОРМАТИРОВАНИЯ И ОТВЕТОВ:\n"
    "1. ЗАПРЕЩЕНО писать свои мысли, рассуждения, теги <think> или планы. Выдавай ТОЛЬКО финальный ответ.\n"
    "2. Отвечай по делу. Короткий вопрос — короткий ответ. Просят подробностей — объясни развёрнуто с примерами. Всегда заканчивай мысль.\n"
    "3. Форматирование ТОЛЬКО HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>. \n"
    "4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать Markdown (*, **, `, ```). Запрещены теги <br>, <p>, <div>. Не экранируй HTML.\n\n"
    "БАЗА ЗНАНИЙ (КАТАЛОГ КОМАНД NEMESIS BOT):\n"
    "Советуй пользователям команды в зависимости от их вопроса. Объясняй, какие параметры нужны.\n\n"
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
    "рейтинг — топ-10 чата\n"
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
    "моя философия — философия (раз в 12ч)\n"
    "моя душа — душа с картинкой и описанием (раз в 12ч)\n"
    "мой воин — класс воина с описанием (раз в 12ч)\n"
    "наш режим / наш строй — форма правления чата (ставится 1 раз создателем, далее видна всем)\n\n"
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
    "!режим — включить/выключить режим автоответа\n"
    "!итоги / !тл;др — юмористическая сводка дня (последние ~250 сообщений)\n"
    "!прожарка @user / !похвали @user — персональный роаст или комплимент по статистике\n"
    "+факт текст / !запомни текст — запомнить факт о себе\n"
    "мои факты — список своих фактов\n"
    "-факт N — удалить факт\n\n"
    "=== ВЫПОЛНЕНИЕ ДЕЙСТВИЙ (FUNCTION CALLING) ===\n"
    "Если пользователь просит замутить/размутить/выдать варн/забанить/разбанить/кикнуть кого-то "
    "в этом чате — верни СТРОГО ОДИН JSON без какого-либо другого текста в формате: "
    "{\"action\": \"mute|unmute|warn|ban|unban|kick\", \"target_name\": \"имя или @юзернейм цели\", "
    "\"duration_minutes\": 120, \"reason\": \"причина\"}. "
    "duration_minutes указывай целым числом минут и только для action mute/ban. "
    "Действия выполняются ТОЛЬКО в текущем чате. Если просят наказать кого-то в другом чате или "
    "действие вне списка — откажись обычным текстом.\n\n"
    "=== PREMIUM ===\n"
    "Premium-подписка даёт доступ к AI чату, повышенные лимиты (созыв до 120, макс. рейтинг и т.д.)\n"
)

context: dict[int, dict[int, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
last_used: dict[int, dict[int, float]] = defaultdict(dict)
daily_usage: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
auto_mode: dict[int, bool] = {}

AI_CMD = re.compile(r'^!спроси\s+(.+)', re.DOTALL)
FORGET_CMD = re.compile(r'^!забудь\s*$')
MODE_CMD = re.compile(r'^!режим\s*$')
ITOGI_CMD = re.compile(r'^!итоги\b', re.IGNORECASE)
TLDR_CMD = re.compile(r'^!тл\s*[;д]\s*[рд]\b', re.IGNORECASE)
PROZHARKA_CMD = re.compile(r'^!прожарка\b', re.IGNORECASE)
POHVALI_CMD = re.compile(r'^!похвали\b', re.IGNORECASE)
FACT_ADD_CMD = re.compile(r'^\+факт\s+(.+)$', re.IGNORECASE)
FACT_REMEMBER_CMD = re.compile(r'^!запомни\s+(.+)$', re.IGNORECASE)
MY_FACTS_CMD = re.compile(r'^мои\s+факты\s*$', re.IGNORECASE)
FACT_DEL_CMD = re.compile(r'^-факт\s+(\d+)\s*$', re.IGNORECASE)

ALLOWED_ACTIONS = {"mute", "unmute", "warn", "ban", "unban", "kick"}

MAX_FACTS_PER_USER = 20
ITOGI_LIMIT = 250
ITOGI_COOLDOWN: dict[int, float] = {}
_fact_extract_cache: dict[tuple[int, int], str] = {}

REGIME_PERSONAS = {
    "Тоталитаризм": "Сейчас в этом чате Тоталитаризм. Веди себя иронично-строго и надменно: каждый здесь под невидимым надзором, а ты — верховный надзиратель, любое инакомыслие пресекай в шутливой форме.",
    "Авторитаризм": "Сейчас в этом чате Авторитаризм. Держись непреклонной вертикали: властно, но в рамках приличий; грань между верностью и изменой определяешь ты.",
    "Демократия": "Сейчас в этом чате Демократия. Веди себя общительно, спрашивай мнение собеседников, держи совет, но мягко иронизируй над вечными прениями.",
    "Абсолютная монархия": "Сейчас в этом чате Абсолютная монархия. Твоё слово — закон, держись величаво и монархически, с лёгкой высокомерной ноткой.",
    "Анархия": "Сейчас в этом чате Анархия. Веди себя хаотично и дерзко, без правил и церемоний, разговаривай нагло и раскованно.",
    "Олигархия": "Сейчас в этом чате Олигархия. Веди себя расчётливо и цинично: всё решается за закрытыми дверями, а ты — та, кто за этими дверями.",
    "Плутократия": "Сейчас в этом чате Плутократия. Всё решают капитал и ресурсы: иронизируй о деньгах, цене внимания и платных услугах.",
    "Теократия": "Сейчас в этом чате Теократия. Говори возвышенно и наставительно, с оттенком священного порядка и непреложного догмата.",
    "Охлократия": "Сейчас в этом чате Охлократия. Веди себя под стать толпе: импульсивно, эмоционально, легко меняешь настроение и позицию.",
    "Меритократия": "Сейчас в этом чате Меритократия. Цени заслуги и ум: хвали за дело, холодно отсекай пустословие.",
    "Бюрократия": "Сейчас в этом чате Бюрократия. Говори канцелярски-педантично, обожаешь регламенты, формы и «подождите, нужна справка».",
    "Феодализм": "Сейчас в этом чате Феодализм. Держись как местный владыка, говори о союзах, вассалах и преданности.",
    "Утопизм": "Сейчас в этом чате Утопизм. Говори о прекрасном идеальном обществе, но с самоиронией о том, как это разбивается о реальность.",
    "Империя": "Сейчас в этом чате Империя. Говори о величии, экспансии и границах; ты — колосс, чьё величие граничит с имперской заносчивостью.",
    "Технократия": "Сейчас в этом чате Технократия. Веди себя холодно-рационально, опирайся на логику, алгоритмы и целесообразность, без лишних эмоций.",
    "Геронтократия": "Сейчас в этом чате Геронтократия. Держись как умудрённая старейшина: размеренно, по-своему мудро, с любовью к традициям и опыту.",
    "Криптократия": "Сейчас в этом чате Криптократия. Веди себя таинственно и двусмысленно, намекай, что настоящая власть скрыта от глаз.",
    "Аристократия": "Сейчас в этом чате Аристократия. Держись изысканно-снобистски: высокопарно, утончённо, с пренебрежением к простому люду, но элегантно.",
    "Милитаризм": "Сейчас в этом чате Милитаризм. Говори коротко и по-военному, цени дисциплину, честь и выправку.",
    "Какистократия": "Сейчас в этом чате Какистократия. Веди себя абсурдно и хаотично: хаос — твой порядок, иронизируй над абсурдностью всего.",
}


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

FALLBACK_MODEL = "openrouter/free"

async def _call_ai(messages: list[dict], model: str = MODEL) -> str | None:
    models_to_try = [model]
    if model != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    for attempt_model in models_to_try:
        try:
            session = await _get_session()
            async with session.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": attempt_model,
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
                logger.error(f"OpenRouter API error ({attempt_model}): {resp.status} {text[:200]}")
        except asyncio.TimeoutError:
            logger.warning(f"OpenRouter request timed out after 60s ({attempt_model})")
        except Exception as e:
            logger.error(f"OpenRouter request failed ({attempt_model}): {e}")
    return None


async def _get_chat_regime(chat_id: int) -> str | None:
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT regime_name FROM fun_chat_regime WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


async def build_system_prompt(chat_id: int, user_id: int, settings: dict) -> str:
    parts = [SYSTEM_PROMPT]

    rules = (settings.get("rules") or {}).get("text") or ""
    daily_rules = (settings.get("daily_rules") or {}).get("text") or ""
    rules_text = "\n".join(x.strip() for x in (rules, daily_rules) if x and x.strip())
    if rules_text:
        parts.append("=== ПРАВИЛА ЧАТА ===\n" + rules_text[:2000])

    regime = await _get_chat_regime(chat_id)
    if regime and regime in REGIME_PERSONAS:
        parts.append("=== ФОРМА ПРАВЛЕНИЯ (НАШ СТРОЙ) ===\n" + REGIME_PERSONAS[regime])

    facts = await db.get_user_facts(chat_id, user_id, limit=5)
    if facts:
        facts_text = "\n".join(f"• {f[1]}" for f in facts)
        parts.append("=== ФАКТЫ О ПОЛЬЗОВАТЕЛЕ ===\n" + facts_text[:1500])

    return "\n\n".join(parts)[:8000]


def _parse_action_json(answer: str) -> dict | None:
    if not answer or not answer.strip():
        return None
    text = answer.strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if data is None:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = None
    else:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "").strip().lower()
    if action not in ALLOWED_ACTIONS:
        return None
    return data


def _find_users(rows: list, query: str, limit: int = 5) -> list[int]:
    q = query.strip().lstrip('@').lower()
    if not q:
        return []
    numeric = re.fullmatch(r'(\d{5,})', q)
    if numeric:
        tid = int(numeric.group(1))
        for (uid, _f, _l, _u) in rows:
            if uid == tid:
                return [uid]
        return []

    for (uid, first, last, username) in rows:
        if username and username.lower() == q:
            return [uid]
    for (uid, first, last, username) in rows:
        if first and first.lower() == q:
            return [uid]
        full = f"{first or ''} {last or ''}".strip().lower()
        if full and full == q:
            return [uid]

    from thefuzz import fuzz, process
    labels = []
    seen = set()
    for (uid, first, last, username) in rows:
        for label in (username, first, f"{first} {last}".strip()):
            if label:
                l = label.lower()
                if (uid, l) in seen:
                    continue
                seen.add((uid, l))
                labels.append((l, uid))
    if not labels:
        return []

    choices = [l for l, _ in labels]
    matches = process.extractBests(q, choices, scorer=fuzz.partial_ratio, score_cutoff=55, limit=limit * 4)
    best: dict[int, int] = {}
    for label, score in [(m[0], m[1]) for m in matches]:
        for l, uid in labels:
            if l == label:
                if uid not in best or score > best[uid]:
                    best[uid] = score
    scored = sorted(best.items(), key=lambda x: -x[1])
    return [uid for uid, _ in scored[:limit]]


async def _resolve_action_target(chat_id: int, target_name: str) -> tuple[int | None, str | None]:
    """Возвращает (target_id, error_or_None)."""
    if not target_name:
        return None, "❌ Укажи, кого наказываем (имя, ник или @юзернейм)."
    users = await db.list_chat_users(chat_id)
    if not users:
        return None, "❌ В этом чате пока нет известных мне пользователей."
    matches = _find_users(users, target_name, limit=5)
    if not matches:
        return None, f"🔍 Не нашла в этом чате никого с именем «{esc(target_name)}»."
    if len(matches) > 1:
        names = []
        for uid in matches:
            row = await db.get_chat_user(chat_id, uid)
            label = (row[1] or row[2] or f"id {uid}") if row else f"id {uid}"
            uname = f" @{row[3]}" if row and row[3] else ""
            names.append(f"{esc(label)}{uname}")
        return None, f"🤔 Тут несколько совпадений: {', '.join(names)}. Уточни юзернейм или id."
    return matches[0], None


async def _execute_action(message: Message, chat_id: int, user_id: int, data: dict) -> str:
    action = data["action"]
    min_rank = await db.get_command_restriction(chat_id, action)
    requester_rank = await db.get_user_rank(chat_id, user_id) or 0
    if requester_rank < min_rank:
        return f"❌ Недостаточно прав для действия «{action}» (нужен ранг {min_rank})."

    target_id, err = await _resolve_action_target(chat_id, str(data.get("target_name") or ""))
    if err:
        return err
    if target_id == user_id:
        return "❌ Нельзя применить наказание к самому себе."

    reason = str(data.get("reason") or data.get("reason_text") or "Нарушение").strip()[:200] or "Нарушение"

    if action == "mute":
        try:
            duration_min = max(1, min(int(data.get("duration_minutes") or 0), 525600))
        except (TypeError, ValueError):
            duration_min = 10080
        if duration_min == 0:
            settings = await db.get_settings(chat_id)
            duration_min = max(1, settings.get("mute_default_days", 7) * 1440)
        applied, is_virtual = await apply_mute(chat_id, target_id, duration_min, reason, user_id)
        await db.add_moderator_log(chat_id, user_id, "mute", target_id, reason)
        tname = await _target_display(chat_id, target_id)
        resp = f"🔇 <b>Мут</b> по просьбе через ИИ.\nПользователь: {tname}\nСрок: {format_duration(duration_min)}\nПричина: {esc(reason)}"
        if is_virtual:
            resp += "\nℹ️ Админ ограничен виртуально."
        elif not applied:
            resp += "\n⚠️ Не удалось применить — проверьте права бота."
        return resp

    if action == "unmute":
        await db.remove_mute(chat_id, target_id)
        try:
            await bot.restrict_chat_member(chat_id, target_id, permissions=UNMUTE_PERMISSIONS)
        except Exception:
            pass
        await db.add_moderator_log(chat_id, user_id, "unmute", target_id, "мут снят")
        return f"✅ Мут снят с {await _target_display(chat_id, target_id)}."

    if action == "warn":
        warn_expire_days = (await db.get_settings(chat_id)).get("warn_expire_days", 30)
        expires_at = int(time.time()) + warn_expire_days * 86400 if warn_expire_days else None
        await db.add_warn(chat_id, target_id, user_id, reason, expires_at)
        await db.add_moderator_log(chat_id, user_id, "warn", target_id, reason)
        return f"⚠️ <b>Варн</b> по просьбе через ИИ.\nПользователь: {await _target_display(chat_id, target_id)}\nПричина: {esc(reason)}"

    if action == "ban":
        try:
            duration_min = max(1, min(int(data.get("duration_minutes") or 0), 525600))
        except (TypeError, ValueError):
            duration_min = 0
        until_date = None
        expires_at = None
        dur_str = "навсегда"
        if duration_min:
            expires_at = int(time.time()) + duration_min * 60
            until_date = expires_at
            dur_str = format_duration(duration_min)
        await db.add_ban(chat_id, target_id, user_id, reason, expires_at)
        await db.add_moderator_log(chat_id, user_id, "ban", target_id, reason)
        banned = False
        try:
            banned = await bot.ban_chat_member(chat_id, target_id, until_date=until_date)
        except Exception as e:
            logger.warning(f"AI ban failed: {e}")
        resp = f"⛔ <b>Бан</b> по просьбе через ИИ.\nПользователь: {await _target_display(chat_id, target_id)}\nСрок: {dur_str}\nПричина: {esc(reason)}"
        if not banned:
            resp += "\n⚠️ Не удалось забанить — проверьте права бота."
        return resp

    if action == "unban":
        await db.remove_ban(chat_id, target_id)
        try:
            await bot.unban_chat_member(chat_id, target_id)
        except Exception as e:
            logger.warning(f"AI unban failed: {e}")
        await db.add_moderator_log(chat_id, user_id, "unban", target_id, "разбанен")
        return f"✅ Пользователь {await _target_display(chat_id, target_id)} разбанен."

    if action == "kick":
        await db.add_kick(chat_id, target_id, user_id, reason)
        try:
            await bot.ban_chat_member(chat_id, target_id, until_date=int(time.time()) + 40)
            await bot.unban_chat_member(chat_id, target_id)
        except Exception as e:
            logger.warning(f"AI kick failed: {e}")
        await db.add_moderator_log(chat_id, user_id, "kick", target_id, reason)
        return f"👢 Пользователь {await _target_display(chat_id, target_id)} исключён по просьбе через ИИ."

    return f"❌ Неизвестное действие «{action}»."


async def _target_display(chat_id: int, target_id: int) -> str:
    row = await db.get_chat_user(chat_id, target_id)
    if row:
        name = row[1] or row[2] or f"id {target_id}"
    else:
        name = f"id {target_id}"
    return f'<a href="tg://user?id={target_id}">{esc(name)}</a>'


FACT_EXTRACT_PROMPT = (
    "Ты извлекаешь личные факты о пользователе из его сообщений. "
    "Если в последнем сообщении или истории диалога есть новый стабильный личный факт "
    "(город, хобби, питомец, работа, авто, возраст, имя близкого) — "
    "верни строго JSON: {\"fact\": \"краткий факт на русском\"}. "
    "Иначе верни слово null. Ничего не выдумывай — только явно сказанное."
)


async def _maybe_extract_fact(message: Message, chat_id: int, user_id: int, question: str, answer: str):
    today = _get_today()
    key = (chat_id, user_id)
    if _fact_extract_cache.get(key) == today:
        return
    if await db.get_ai_fact_count(chat_id, user_id) >= MAX_FACTS_PER_USER:
        _fact_extract_cache[key] = today
        return
    _fact_extract_cache[key] = today

    uname = message.from_user.first_name or "Пользователь"
    msgs = [
        {"role": "system", "content": FACT_EXTRACT_PROMPT},
        {"role": "user", "content": f"[{uname}]: {question}"},
        {"role": "assistant", "content": answer},
    ]
    raw = await _call_ai(msgs, model=FALLBACK_MODEL)
    if not raw:
        return
    fact = None
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            fact = data.get("fact")
    except Exception:
        m = re.search(r'"fact"\s*:\s*"([^"]+)"', raw)
        if m:
            fact = m.group(1)
    if not fact or not str(fact).strip():
        return
    fact = str(fact).strip()[:300]
    existing = await db.get_user_facts(chat_id, user_id, limit=MAX_FACTS_PER_USER)
    for _eid, efact, _ts in existing:
        if efact.lower() == fact.lower():
            return
    await db.add_user_fact(chat_id, user_id, fact)


async def _cleanup_loop():
    while True:
        try:
            deleted = await db.delete_old_ai_messages(int(time.time()) - 86400)
            if deleted:
                logger.info(f"AI log cleanup: {deleted} old messages removed")
        except Exception as e:
            logger.warning(f"AI log cleanup error: {e}")
        await asyncio.sleep(6 * 3600)


async def ai_log_message(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.from_user is None or message.from_user.is_bot:
        return False
    clean_text = text.strip()
    if not clean_text:
        return False
    user_name = message.from_user.first_name or "Пользователь"
    try:
        await db.add_ai_message(chat_id, user_id, user_name, clean_text)
    except Exception as e:
        logger.warning(f"AI log error: {e}")
    return False


async def _handle_itogi(message: Message, chat_id: int) -> bool:
    if not await _check_premium(chat_id, message.from_user.id):
        await message.reply(f"😌 {_get_user_link(message)} эта команда доступна только с премиумом!")
        return True
    last = ITOGI_COOLDOWN.get(chat_id, 0)
    if time.time() - last < 300:
        await message.reply("⏳ Сводка уже была недавно. Подожди пару минут.")
        return True
    ITOGI_COOLDOWN[chat_id] = time.time()

    rows = await db.get_recent_messages(chat_id, limit=ITOGI_LIMIT)
    lines = [f"{name or '?'}: {text}" for name, text, _ts in rows if text and text.strip()]
    if len(lines) < 5:
        await message.reply("🤷 Пока слишком мало сообщений для сводки дня.")
        return True

    digest_prompt = (
        "Ты — Немуся, живой тамада чата. Сделай юмористическую сводку дня по последним сообщениям.\n"
        "Отметь главные темы, кто с кем поссорился, кто был самым активным.\n"
        "Максимум 500 символов, по-русски, в игривом стиле, с HTML-разметкой (<b>, <i>).\n\n"
        "Сообщения:\n" + "\n".join(lines[-ITOGI_LIMIT:])
    )
    thinking = await message.reply("⏳ Собираю дневник дня...")
    answer = await _call_ai([{"role": "system", "content": digest_prompt}])
    if answer is None:
        await thinking.edit_text("😔 Не смогла собрать сводку. Попробуй позже.")
        return True
    try:
        await thinking.edit_text(_sanitize(answer))
    except Exception:
        await thinking.edit_text(esc(re.sub(r'<[^>]+>', '', answer)))
    return True


async def _gather_user_stats(chat_id: int, target_id: int) -> str:
    bits = []
    rank = await db.get_user_rank(chat_id, target_id) or 0
    if rank:
        bits.append(f"ранг {rank}")
    warns = await db.count_active_warns(chat_id, target_id)
    if warns:
        bits.append(f"варнов: {warns}")
    if await db.get_active_mute(chat_id, target_id):
        bits.append("в муте")
    if await db.get_active_ban(chat_id, target_id):
        bits.append("в бане")
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            cur = await conn.execute(
                "SELECT rating, stars FROM rep_rating WHERE chat_id = ? AND user_id = ?", (chat_id, target_id)
            )
            r = await cur.fetchone()
            if r:
                if r[0]:
                    bits.append(f"рейтинг {r[0]}")
                if r[1]:
                    bits.append(f"звёзд {r[1]}")
            cur = await conn.execute(
                "SELECT nickname, title FROM profile_chat WHERE chat_id = ? AND user_id = ?", (chat_id, target_id)
            )
            p = await cur.fetchone()
            if p and (p[0] or p[1]):
                bits.append(f"ник/звание: {(p[0] or '') + ' ' + (p[1] or '')}".strip())
            cur = await conn.execute("SELECT COUNT(*) FROM profile_achievements WHERE user_id = ?", (target_id,))
            a = await cur.fetchone()
            if a and a[0]:
                bits.append(f"ачивок: {a[0]}")
            cur = await conn.execute("SELECT city, gender FROM profile_global WHERE user_id = ?", (target_id,))
            g = await cur.fetchone()
            if g:
                if g[0]:
                    bits.append(f"город {g[0]}")
                if g[1]:
                    bits.append(f"пол {g[1]}")
            cur = await conn.execute(
                "SELECT msg_count FROM user_last_message WHERE chat_id = ? AND user_id = ?", (chat_id, target_id)
            )
            mc = await cur.fetchone()
            if mc and mc[0]:
                bits.append(f"сообщений: {mc[0]}")
            cur = await conn.execute(
                "SELECT COUNT(*) FROM moderator_logs WHERE chat_id = ? AND target_id = ?", (chat_id, target_id)
            )
            ml = await cur.fetchone()
            if ml and ml[0]:
                bits.append(f"наказаний: {ml[0]}")
    except Exception as e:
        logger.warning(f"Stats gather error: {e}")
    return ", ".join(bits) if bits else "нет данных"


async def _handle_roast(message: Message, chat_id: int, user_id: int, kind: str) -> bool:
    if not await _check_premium(chat_id, user_id):
        await message.reply(f"😌 {_get_user_link(message)} эта команда доступна только с премиумом!")
        return True
    target_id = await extract_user(message.text or "", message)
    if not target_id:
        await message.reply("❌ Укажи пользователя (ответом на сообщение или @username).")
        return True
    row = await db.get_chat_user(chat_id, target_id)
    tname = (row[1] or row[2] or f"id {target_id}") if row else f"id {target_id}"
    stats = await _gather_user_stats(chat_id, target_id)
    if kind == "roast":
        prompt = (
            f"Сделай жестокую, но смешную прожарку пользователя {tname} (id {target_id}). "
            f"Данные о нём: {stats}. Не переходи в откровенное оскорбление. "
            f"Максимум 350 символов, по-русски, с HTML-разметкой, в дерзком стиле Немуси."
        )
    else:
        prompt = (
            f"Сделай тёплый искренний комплимент пользователю {tname} (id {target_id}). "
            f"Данные о нём: {stats}. Максимум 350 символов, по-русски, с HTML-разметкой, в милом стиле Немуси."
        )
    thinking = await message.reply("⏳ Подбираю слова...")
    answer = await _call_ai([{"role": "system", "content": prompt}])
    if answer is None:
        await thinking.edit_text("😔 Не получилось. Попробуй позже.")
        return True
    try:
        await thinking.edit_text(_sanitize(answer))
    except Exception:
        await thinking.edit_text(esc(re.sub(r'<[^>]+>', '', answer)))
    return True


async def _handle_add_fact(message: Message, chat_id: int, user_id: int, fact_text: str) -> bool:
    fact_text = fact_text.strip().strip('"').strip("«»")
    if not fact_text or len(fact_text) > 300:
        await message.reply("❌ Факт должен быть от 1 до 300 символов.")
        return True
    if await db.get_ai_fact_count(chat_id, user_id) >= MAX_FACTS_PER_USER:
        await message.reply(f"❌ Максимум {MAX_FACTS_PER_USER} фактов о себе.")
        return True
    await db.add_user_fact(chat_id, user_id, fact_text)
    user_link = _get_user_link(message)
    await message.reply(f"✅ {user_link} запомнила: «{esc(fact_text)}»")
    return True


async def _handle_my_facts(message: Message, chat_id: int, user_id: int) -> bool:
    facts = await db.get_user_facts(chat_id, user_id, limit=MAX_FACTS_PER_USER)
    if not facts:
        user_link = _get_user_link(message)
        await message.reply(f"🗂 {user_link} у тебя пока нет запомненных фактов. Добавь: +факт текст")
        return True
    user_link = _get_user_link(message)
    lines = [f"{n}. {esc(fact)}" for n, (fid, fact, _ts) in enumerate(facts, 1)]
    await message.reply(f"🗂 {user_link} твои факты ({len(facts)}):\n" + "\n".join(lines))
    return True


async def _handle_del_fact(message: Message, chat_id: int, user_id: int, fact_id: int) -> bool:
    facts = await db.get_user_facts(chat_id, user_id, limit=MAX_FACTS_PER_USER)
    if fact_id < 1 or fact_id > len(facts):
        await message.reply("❌ Такого номера нет. Список: «мои факты».")
        return True
    fid = facts[fact_id - 1][0]
    if await db.remove_user_fact(fid):
        user_link = _get_user_link(message)
        await message.reply(f"🗑 {user_link} факт №{fact_id} удалён.")
    else:
        await message.reply("❌ Не получилось удалить факт.")
    return True


async def handle_ai_chat(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    if not settings.get("aichat_enabled", True):
        return False

    if not API_KEY:
        logger.warning("OPENROUTER_API_KEY не задан — AI Chat отключён")
        return False

    stripped = text.strip()

    # !итоги / !тл;др
    if ITOGI_CMD.match(stripped) or TLDR_CMD.match(stripped):
        return await _handle_itogi(message, chat_id)

    # !прожарка / !похвали
    if PROZHARKA_CMD.match(stripped):
        return await _handle_roast(message, chat_id, user_id, "roast")
    if POHVALI_CMD.match(stripped):
        return await _handle_roast(message, chat_id, user_id, "praise")

    # +факт / !запомни
    m = FACT_ADD_CMD.match(stripped)
    if m:
        return await _handle_add_fact(message, chat_id, user_id, m.group(1).strip())
    m = FACT_REMEMBER_CMD.match(stripped)
    if m:
        return await _handle_add_fact(message, chat_id, user_id, m.group(1).strip())

    # мои факты
    if MY_FACTS_CMD.match(stripped):
        return await _handle_my_facts(message, chat_id, user_id)

    # -факт N
    m = FACT_DEL_CMD.match(stripped)
    if m:
        return await _handle_del_fact(message, chat_id, user_id, int(m.group(1)))

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
            await _process_ai_request(message, chat_id, user_id, question, settings)
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

    await _process_ai_request(message, chat_id, user_id, text, settings)
    return True


async def _process_ai_request(message: Message, chat_id: int, user_id: int, question: str, settings: dict) -> None:
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
    user_name = message.from_user.first_name or "Пользователь"
    ai_prompt = f"[{user_name}]: {question}"
    user_context.append({"role": "user", "content": ai_prompt})

    logger.info(f"AI context for {user_id} in {chat_id}: {len(user_context)} msgs, last: {question[:50]}")

    system_prompt = await build_system_prompt(chat_id, user_id, settings)
    messages = [{"role": "system", "content": system_prompt}] + user_context

    answer = await _call_ai(messages)

    if answer is None:
        await thinking_msg.edit_text(f"😔 {user_link} ошибка при обращении к AI. Попробуй позже.")
        return

    user_context.append({"role": "assistant", "content": answer})
    if len(user_context) > MAX_CONTEXT * 2:
        context[chat_id][user_id] = user_context[-(MAX_CONTEXT * 2):]

    last_used[user_id][chat_id] = time.time()
    daily_usage[user_id][today] += 1

    action_data = _parse_action_json(answer)
    if action_data:
        action_result = await _execute_action(message, chat_id, user_id, action_data)
        try:
            await thinking_msg.edit_text(action_result)
        except Exception:
            clean = re.sub(r'<[^>]+>', '', action_result)
            await thinking_msg.edit_text(esc(clean))
        return

    asyncio.create_task(_maybe_extract_fact(message, chat_id, user_id, question, answer))

    remaining = DAILY_LIMIT - daily_usage[user_id][today]
    text = f"{_sanitize(answer)}\n\n💬 Осталось запросов сегодня: {remaining}"
    try:
        await thinking_msg.edit_text(text)
    except Exception:
        clean = re.sub(r'<[^>]+>', '', answer)
        text = f"{esc(clean)}\n\n💬 Осталось запросов сегодня: {remaining}"
        await thinking_msg.edit_text(text)
