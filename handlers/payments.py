from aiogram import Router
from aiogram.types import PreCheckoutQuery, Message

from bot import bot, logger
from db import db
from handlers.messages import is_admin

router = Router()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(lambda msg: msg.successful_payment is not None)
async def successful_payment_handler(message: Message):
    payload = message.successful_payment.payload
    user_id = message.from_user.id
    chat_id = message.chat.id

    if payload == "personal_premium":
        await db.activate_premium_user(user_id, 30)
        logger.info(f"User {user_id} activated personal premium")
        await message.answer(
            "✅ <b>Личный премиум активирован!</b>\n\n"
            "Спасибо за покупку! Все премиум-функции доступны.\n"
            "Используйте /start для открытия меню."
        )
    elif payload == "group_premium":
        if await is_admin(chat_id, user_id):
            await db.activate_premium_group(chat_id, 30)
            logger.info(f"Group {chat_id} activated group premium by user {user_id}")
            await message.answer(
                "✅ <b>Премиум для группы активирован!</b>\n\n"
                "Спасибо за покупку! Все премиум-функции группы доступны.\n"
                "Используйте /start для открытия меню."
            )
        else:
            await message.answer("❌ Только администраторы могут активировать групповой премиум.")
