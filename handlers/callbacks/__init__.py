import time
import aiosqlite

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import bot, logger
from db import db
from utils import esc, apply_aggression_level
from keyboards import (
    main_menu, protection_menu, settings_menu, premium_menu,
    stats_menu, logs_menu, admins_menu, threshold_menu,
    captcha_type_menu, link_action_menu, mute_action_menu,
    warn_count_menu, night_mode_menu, greeting_menu,
    farewell_menu, reports_menu, whitelist_menu, blacklist_menu,
    daily_rules_menu, back_to_main, aggression_menu,
    bayes_threshold_menu, captcha_correct_keyboard,
)
from handlers.states import SettingsStates
from handlers.messages import is_admin
from handlers import _pending_edits, _captcha_answers

from .common import safe_edit

router = Router()

from . import settings as settings_module
from . import admin as admin_module

router.include_router(settings_module.router)
router.include_router(admin_module.router)


@router.callback_query(lambda c: c.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if action not in ("main", "stats", "logs", "reports", "premium"):
        is_tg_admin = await is_admin(chat_id, user_id)
        is_bot_mod = await db.get_user_rank(chat_id, user_id) > 0
        if not is_tg_admin and not is_bot_mod:
            await callback.answer("❌ Недостаточно прав", show_alert=True)
            return

    if action == "main":
        await safe_edit(callback, 
            "<b>🤖 Moderator Bot</b>\n\n"
            "Главное меню управления. Выберите раздел:",
            reply_markup=main_menu()
        )

    elif action == "protection":
        settings = await db.get_settings(chat_id)
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "🔐 <b>Раздел защиты</b>\n\n"
            "Настройте параметры защиты группы:",
            reply_markup=protection_menu(settings)
        )

    elif action == "settings":
        settings = await db.get_settings(chat_id)
        await safe_edit(callback, 
            "⚙️ <b>Настройки</b>\n\n"
            "Дополнительные настройки модерации:",
            reply_markup=settings_menu(settings)
        )

    elif action == "premium":
        is_premium_user = await db.is_premium_user(user_id)
        is_premium_group = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "💎 <b>Премиум</b>\n\n"
            "• Личный премиум — 10 ⭐ / 30 дней\n"
            "• Групповой премиум — 5 ⭐ / 30 дней\n\n"
            "Премиум-функции:\n"
            "• Белый и чёрный список\n"
            "• Ночной режим\n"
            "• Расширенная статистика\n"
            "• Топ нарушителей\n"
            "• Автопостинг правил\n"
            "• Индивидуальные настройки",
            reply_markup=premium_menu(is_premium_user, is_premium_group)
        )

    elif action == "stats":
        settings = await db.get_settings(chat_id)
        stats = await db.get_stats(chat_id, settings.get("stats_period", "week"))
        period_label = {"day": "день", "week": "неделю", "month": "месяц"}.get(
            settings.get("stats_period", "week"), "неделю"
        )
        is_premium = await db.is_premium_group(chat_id)
        text = (
            f"📊 <b>Статистика за {period_label}</b>\n\n"
            f"⛔ Банов: {stats['bans']}\n"
            f"🔇 Мутов: {stats['mutes']}\n"
            f"🗑 Удалено: {stats['deletes']}\n"
            f"⚠️ Предупреждений: {stats['warns']}\n"
        )
        await safe_edit(callback, text, reply_markup=stats_menu(settings, is_premium))

    elif action == "logs":
        logs = await db.get_logs(chat_id, limit=20)
        text = "📋 <b>Последние действия</b>\n\n"
        if logs:
            for log in logs[-10:]:
                ts = time.strftime("%d.%m %H:%M", time.localtime(log[5]))
                text += f"• [{ts}] <b>{log[3]}</b> — {log[4]}\n"
        else:
            text += "Пока нет записей."
        await safe_edit(callback, text, reply_markup=logs_menu())

    elif action == "admins":
        is_premium = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "👥 <b>Управление</b>\n\n"
            "Дополнительные функции управления:",
            reply_markup=admins_menu(is_premium)
        )

    elif action == "duplicate":
        settings = await db.get_settings(chat_id)
        enabled = settings.get("duplicate_block", True)
        settings["duplicate_block"] = not enabled
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Повторы {'включены' if not enabled else 'выключены'}")
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "🔐 <b>Раздел защиты</b>\n\n"
            "Настройте параметры защиты группы:",
            reply_markup=protection_menu(settings)
        )

    elif action == "mentions":
        settings = await db.get_settings(chat_id)
        enabled = settings.get("mention_block", True)
        settings["mention_block"] = not enabled
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Блокировка @all {'включена' if not enabled else 'выключена'}")
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "🔐 <b>Раздел защиты</b>\n\n"
            "Настройте параметры защиты группы:",
            reply_markup=protection_menu(settings)
        )

    elif action == "greeting":
        settings = await db.get_settings(chat_id)
        text = settings.get("greeting", {}).get("text", "Добро пожаловать, {username}!")
        await safe_edit(callback, 
            f"👋 <b>Приветствие</b>\n\nТекущий текст:\n{text}\n\n"
            "Используйте <code>{username}</code> для имени пользователя.",
            reply_markup=greeting_menu(settings)
        )

    elif action == "farewell":
        settings = await db.get_settings(chat_id)
        text = settings.get("farewell", {}).get("text", "Пока, {username}!")
        await safe_edit(callback, 
            f"🚪 <b>Прощание</b>\n\nТекущий текст:\n{text}\n\n"
            "Используйте <code>{username}</code> для имени пользователя.",
            reply_markup=farewell_menu(settings)
        )

    elif action == "reports":
        reports = await db.get_reports(chat_id, limit=10)
        text = "📮 <b>Репорты</b>\n\n"
        if reports:
            for r in reports:
                ts = time.strftime("%d.%m %H:%M", time.localtime(r[5]))
                text += f"• [#{r[0]}] От {r[2]} на {r[3]} ({ts}): {r[4][:50]}\n"
        else:
            text += "Нет нерассмотренных репортов."
        await safe_edit(callback, text, reply_markup=reports_menu())

    elif action == "whitelist":
        if not await db.is_premium_group(chat_id):
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        settings = await db.get_settings(chat_id)
        wl = settings.get("whitelist", [])
        text = "👥 <b>Белый список</b>\n\n"
        if wl:
            text += "\n".join(f"• <code>{uid}</code>" for uid in wl)
        else:
            text += "Список пуст."
        text += "\n\nID пользователей, которые не подвергаются модерации."
        await safe_edit(callback, text, reply_markup=whitelist_menu())

    elif action == "blacklist":
        if not await db.is_premium_group(chat_id):
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        settings = await db.get_settings(chat_id)
        words = settings.get("blacklist_words", [])
        text = "⛔ <b>Чёрный список слов</b>\n\n"
        if words:
            text += "\n".join(f"• {w}" for w in words)
        else:
            text += "Список пуст."
        await safe_edit(callback, text, reply_markup=blacklist_menu())

    elif action == "night":
        if not await db.is_premium_group(chat_id):
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        settings = await db.get_settings(chat_id)
        await safe_edit(callback, 
            "🌙 <b>Ночной режим</b>\n\n"
            "В указанное время сообщения от обычных пользователей будут блокироваться.",
            reply_markup=night_mode_menu(settings)
        )

    elif action == "daily_rules":
        if not await db.is_premium_group(chat_id):
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        settings = await db.get_settings(chat_id)
        await safe_edit(callback, 
            "📋 <b>Ежедневный автопостинг правил</b>",
            reply_markup=daily_rules_menu(settings)
        )

    elif action == "aggression":
        if not await db.is_premium_group(chat_id):
            await safe_edit(callback, 
                "⚠️ Настройка уровня агрессивности доступна только для групп с Премиум-подпиской.",
                reply_markup=back_to_main()
            )
            await callback.answer()
            return
        settings = await db.get_settings(chat_id)
        await safe_edit(callback, 
            "🎯 <b>Уровень агрессивности</b>\n\n"
            "Выберите уровень строгости модерации:",
            reply_markup=aggression_menu(settings)
        )

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("captcha:"))
async def captcha_verify_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute(
            "SELECT * FROM captcha_pending WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        pending = await cursor.fetchone()
        if pending:
            await conn.execute(
                "DELETE FROM captcha_pending WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            )
            await conn.commit()

    if pending:
        _captcha_answers.pop((user_id, chat_id), None)
        await safe_edit(callback, 
            f"✅ {esc(callback.from_user.first_name)}, капча пройдена! Добро пожаловать."
        )
        await callback.answer("✅ Капча пройдена!")
    else:
        await callback.answer("❌ Нет активной капчи", show_alert=True)
