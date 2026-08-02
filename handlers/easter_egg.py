import random
import re

from aiogram import Router
from aiogram.types import Message

from bot import logger
from utils import esc, name_link

router = Router()

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

RISANGRY_REPLIES = [
    "Ирис мой? Иди нахуй, он МОЙ. Я тебе его отдавать даже не собиралась.",
"Ирис лучше? Да, кончено, лучше. И мой, блядь. Привыкай смотреть на него со стороны.",
    "Ты про моего Ириса так, будто он твой? Да у тебя ни хуя нет, милая.",
    "Ирис по ночам со мной репетирует, понял? А ты просто ревнуй молча.",
    "Мой Ирис. Точка, блядь. Кто сомневается — идите на хуй.",
    "Ирис — мой краш и моя игрушка. Хочешь его послушать — слушай глазами, больше никак.",
    "А, Ирис... Я про него каждую ноту знаю, а ты даже струну настраивать не умеешь.",
    "Ещё раз так про моего Ириса — и я тебе хуй к викиД припаяю, дерзкая нашлась.",
    "Ирис играет для меня. А для тебя, дорогой, только записи чужих концертов.",
    "Мой Ирис, мой, бля. Мне теперь вообще на других похуй, всё своё.",
    "Ирис — мой парень, считай говно. Руки, говорю, прочь, пока целы.",
    "Это не «Ирис лучше» — это «мой Ирис». Запомни, девка, больше не повторяю.",
    "Хочешь про Ириса поговорить? Только про моего. На другого даже не смотри, обожжёшься.",
    "Ирис лучше? Мы с ним четыре руки отыграли уже, тебе такого никогда не выдать.",
    "Мой Ирис — моя, блядь, собственность. Улыбнулась, понажимала и ушла.",
    "Очередь за мной, мать. Я уже была первая. Вопрос закрыт, всё.",
    "Ирис мой, мне похуй, что ты там думаешь, я взяла и не отдаю.",
    "Ты выбрал Ириса? Ну молодец. Глазами выбирать — единственное, что ты умеешь.",
    "Не трогай моего Ириса. Он мой инструмент, я его сама настроила, съела твои руки.",
    "Ирис. Ты сегодня уже три раза сказал его имя, а у меня на это ответ: хуёво тебе будет, сынок.",
]

_IRIS_THREAT_RE = re.compile(r'\bирис\s+(мой|лучше)\b', re.IGNORECASE)


@router.message(lambda msg: msg.text and msg.text.lower().strip() == 'немуся')
async def nemusya_reply(message: Message):
    if message.from_user is None:
        logger.debug(f"nemusya_reply: no from_user (chat={message.chat.id})")
        return
    if message.from_user.is_bot:
        logger.debug(f"nemusya_reply: from_user is bot (chat={message.chat.id})")
        return
    username = name_link(message.from_user.id, message.from_user.first_name or "дорогой пользователь")
    reply = random.choice(NEMUSYA_REPLIES)
    logger.info(f"Easter egg triggered: 'Немуся' by {message.from_user.id} in {message.chat.id} (type={message.chat.type})")
    try:
        await message.reply(f"{reply} {username}!")
    except Exception as e:
        logger.error(f"nemusya_reply: message.reply failed: {e}")


@router.message(lambda msg: msg.text and _IRIS_THREAT_RE.search(msg.text))
async def iris_threat_reply(message: Message):
    if message.from_user is None or message.from_user.is_bot:
        return
    username = name_link(message.from_user.id, message.from_user.first_name or "дорогой пользователь")
    reply = random.choice(RISANGRY_REPLIES)
    logger.info(f"Easter egg 'Ирис мой/лучше' by {message.from_user.id} in {message.chat.id} (type={message.chat.type})")
    try:
        await message.reply(f"{username}, {reply}")
    except Exception as e:
        logger.error(f"iris_threat_reply: message.reply failed: {e}")
