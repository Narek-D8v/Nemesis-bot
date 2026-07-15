from aiogram import Router
from aiogram.types import PreCheckoutQuery, Message

from bot import bot, logger
from db import db
from handlers.messages import is_admin

router = Router()

VALID_PAYLOADS = {"personal_premium", "group_premium"}


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload
    base_payload = payload.split(":")[0] if ":" in payload else payload
    if base_payload not in VALID_PAYLOADS:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False,
            error_message="❌ Неверный payload платежа."
        )
        return
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(lambda msg: msg.successful_payment is not None)
async def successful_payment_handler(message: Message):
    payload = message.successful_payment.payload
    user_id = message.from_user.id

    if payload == "personal_premium":
        await db.activate_premium_user(user_id, 30)
        logger.info(f"User {user_id} activated personal premium")
        await message.answer(
            "✅ <b>Личный премиум активирован!</b>\n\n"
            "Спасибо за покупку! Все премиум-функции доступны.\n"
            "Используйте /start для открытия меню."
        )
    elif payload.startswith("group_premium:"):
        parts = payload.split(":")
        if len(parts) != 2:
            await message.answer("❌ Ошибка: неверный формат платежа.")
            return
        try:
            group_chat_id = int(parts[1])
        except ValueError:
            await message.answer("❌ Ошибка: неверный ID группы.")
            return
        if await is_admin(group_chat_id, user_id):
            await db.activate_premium_group(group_chat_id, 30)
            logger.info(f"Group {group_chat_id} activated group premium by user {user_id}")
            await message.answer(
                "✅ <b>Премиум для группы активирован!</b>\n\n"
                "Спасибо за покупку! Все премиум-функции группы доступны.\n"
                "Используйте /start для открытия меню."
            )
        else:
            await message.answer("❌ Только администраторы могут активировать групповой премиум.")
