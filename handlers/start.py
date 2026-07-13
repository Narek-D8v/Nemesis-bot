from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command

from bot import bot, logger
from config import ADMIN_ID
from db import db
from keyboards import main_menu

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "<b>🤖 Moderator Bot</b>\n\n"
        "Привет! Я бот-модератор для групп. "
        "Я помогаю поддерживать порядок, блокировать спам, "
        "мат, ссылки и многое другое.\n\n"
        "<b>Доступные функции:</b>\n"
        "• Анти-флуд, капча, фильтр ссылок\n"
        "• Блокировка мата, повторов, упоминаний\n"
        "• Защита от ботов и новых аккаунтов\n"
        "• Система предупреждений и многое другое\n\n"
        "Используй кнопки ниже для управления:",
        reply_markup=main_menu()
    )
    logger.info(f"User {message.from_user.id} started the bot")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>🤖 Moderator Bot — Помощь</b>\n\n"
        "Этот бот управляется полностью через инлайн-кнопки.\n"
        "Нажми /start чтобы открыть главное меню.\n\n"
        "<b>Основные разделы:</b>\n"
        "🔐 <b>Защита</b> — антиспам, капча, фильтры\n"
        "⚙️ <b>Настройки</b> — предупреждения, логи, доп. функции\n"
        "💎 <b>Премиум</b> — покупка подписки\n"
        "📊 <b>Статистика</b> — статистика нарушений\n"
        "📋 <b>Логи</b> — просмотр действий\n\n"
        "<i>Для настройки в группе добавьте бота в группу "
        "и дайте права администратора.</i>",
        reply_markup=main_menu()
    )


@router.message(F.text.startswith(".подарить"))
async def gift_premium(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        if message.chat.type in ("group", "supergroup"):
            chat_id = message.chat.id
            await db.activate_premium_group(chat_id, 30)
            logger.info(f"Admin {ADMIN_ID} gifted group premium to chat {chat_id}")
            await message.reply(
                f"✅ <b>Премиум для группы подарен!</b>\n\n"
                f"Группа получила 30 дней группового премиума."
            )
        else:
            await message.reply("❌ Используйте эту команду в группе или ответьте на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user
    if not target or target.is_bot:
        await message.reply("❌ Нельзя подарить премиум боту.")
        return

    await db.activate_premium_user(target.id, 30)
    logger.info(f"Admin {ADMIN_ID} gifted premium to user {target.id} ({target.full_name})")

    await message.reply(
        f"✅ <b>Премиум подарен!</b>\n\n"
        f"Пользователь {target.full_name} (<code>{target.id}</code>) "
        f"получил 30 дней личного премиума."
    )
    try:
        await bot.send_message(
            target.id,
            f"🎉 <b>Вам подарили личный премиум на 30 дней!</b>\n\n"
            f"Теперь вам доступны все премиум-функции бота. "
            f"Нажмите /start чтобы открыть меню."
        )
    except Exception as e:
        logger.warning(f"Could not notify user {target.id} about premium gift: {e}")


RANK_NAMES = {0: "Участник", 1: "Мл.Модер", 2: "Ст.Модер", 3: "Мл.Админ", 4: "Ст.Админ", 5: "Создатель"}


async def ensure_bot_owner_rank(chat_id: int):
    if ADMIN_ID == 0:
        return
    try:
        member = await bot.get_chat_member(chat_id, ADMIN_ID)
        if member.status in ("creator", "administrator"):
            rank = await db.get_user_rank(chat_id, ADMIN_ID)
            if rank != 5:
                await db.set_user_rank(chat_id, ADMIN_ID, 5, ADMIN_ID)
                logger.info(f"Bot owner {ADMIN_ID} set as creator (rank 5) in chat {chat_id}")
    except Exception:
        pass


async def assign_owner_as_creator(chat_id: int):
    try:
        admins = await bot.get_chat_administrators(chat_id)
        owner = None
        for admin in admins:
            if admin.status == "creator":
                owner = admin.user
                break
        if not owner:
            logger.warning(f"No owner found for chat {chat_id}")
            return

        rank = await db.get_user_rank(chat_id, owner.id)
        if rank != 5:
            await db.set_user_rank(chat_id, owner.id, 5, owner.id)
            logger.info(f"Owner {owner.id} assigned as creator (rank 5) in chat {chat_id}")
            try:
                await bot.send_message(
                    owner.id,
                    f"👋 <b>Привет! Я Немесис.</b>\n\n"
                    f"Ты автоматически назначен <b>Создателем</b> группы.\n"
                    f"Тебе доступны все права управления ботом."
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"assign_owner_as_creator error for {chat_id}: {e}")


@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    if event.new_chat_member.status in ("member", "administrator"):
        chat_id = event.chat.id
        if not await db.has_creator(chat_id):
            await assign_owner_as_creator(chat_id)

        await ensure_bot_owner_rank(chat_id)

    if event.new_chat_member.status == "member":
        chat = event.chat
        try:
            await bot.send_message(
                chat.id,
                "⚠️ <b>Дайте мне права администратора!</b>\n\n"
                "Чтобы я мог полноценно работать, выдай мне права "
                "хотя бы на <b>чтение сообщений</b> и <b>участников</b>.\n\n"
                "Без этого я не смогу назначать создателя и выполнять "
                "функции модерации."
            )
        except Exception:
            pass
