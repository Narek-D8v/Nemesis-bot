import random

from aiogram import Router
from aiogram.types import Message

from bot import logger
from utils import esc

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


@router.message(lambda msg: msg.text and msg.text.lower().strip() == 'немуся')
async def nemusya_reply(message: Message):
    if message.from_user is None:
        logger.debug(f"nemusya_reply: no from_user (chat={message.chat.id})")
        return
    if message.from_user.is_bot:
        logger.debug(f"nemusya_reply: from_user is bot (chat={message.chat.id})")
        return
    username = esc(message.from_user.first_name or "дорогой пользователь")
    reply = random.choice(NEMUSYA_REPLIES)
    logger.info(f"Easter egg triggered: 'Немуся' by {message.from_user.id} in {message.chat.id} (type={message.chat.type})")
    try:
        await message.reply(f"{reply} {username}!")
    except Exception as e:
        logger.error(f"nemusya_reply: message.reply failed: {e}")
