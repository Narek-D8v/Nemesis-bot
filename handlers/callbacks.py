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
    bayes_threshold_menu,
)
from handlers.states import SettingsStates
from handlers.messages import is_admin

router = Router()


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass


@router.callback_query(lambda c: c.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if action not in ("main", "stats", "logs", "reports", "premium"):
        if not await is_admin(chat_id, user_id):
            await callback.answer("❌ Только для администраторов", show_alert=True)
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
        return

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
        return

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


@router.callback_query(lambda c: c.data.startswith("aggression:"))
async def set_aggression(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3 or parts[1] != "set":
        await callback.answer()
        return
    try:
        level = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Некорректный уровень", show_alert=True)
        return
    if level not in (0, 1, 2, 3):
        await callback.answer("❌ Недопустимый уровень", show_alert=True)
        return

    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    if not await db.is_premium_group(chat_id):
        await callback.answer("❌ Только для премиум-групп", show_alert=True)
        return

    settings = await db.get_settings(chat_id)
    settings["aggression_level"] = level
    apply_aggression_level(settings, level)
    await db.save_settings(chat_id, settings)

    names = ["Мягкий", "Средний", "Строгий", "Параноик"]
    await safe_edit(callback, 
        f"🎯 Уровень агрессивности установлен на: <b>{names[level]}</b>\n\n"
        "Все фильтры обновлены в соответствии с выбранным уровнем.",
        reply_markup=aggression_menu(settings)
    )
    await callback.answer(f"Уровень изменён на {names[level]}")


@router.callback_query(lambda c: c.data.startswith("a:"))
async def antispam_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["antispam"]["enabled"] = not settings["antispam"]["enabled"]
        await db.save_settings(chat_id, settings)
        status = "включён" if settings["antispam"]["enabled"] else "выключен"
        await callback.answer(f"Антиспам {status}")
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "🔐 Настройка защиты", reply_markup=protection_menu(settings)
        )
    elif action == "threshold":
        await safe_edit(callback, 
            "Выберите порог сообщений в минуту:",
            reply_markup=threshold_menu()
        )
    elif action == "s":
        try:
            threshold = int(parts[2])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректное значение", show_alert=True)
            return
        if threshold not in (0, 3, 5, 10, 15):
            await callback.answer("❌ Недопустимый порог", show_alert=True)
            return
        settings["antispam"]["threshold"] = threshold
        await db.save_settings(chat_id, settings)
        label = "∞" if threshold == 0 else str(threshold)
        await callback.answer(f"Порог: {label}")
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback, 
            "🔐 Настройка защиты", reply_markup=protection_menu(settings)
        )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("c:"))
async def captcha_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["captcha"]["enabled"] = not settings["captcha"]["enabled"]
        await db.save_settings(chat_id, settings)
        status = "включена" if settings["captcha"]["enabled"] else "выключена"
        await callback.answer(f"Капча {status}")
    elif action == "type":
        await safe_edit(callback, 
            "Выберите тип капчи:",
            reply_markup=captcha_type_menu()
        )
        await callback.answer()
        return
    elif action.startswith("type:"):
        cap_type = parts[2]
        settings["captcha"]["type"] = cap_type
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Тип капчи: {'Кнопка' if cap_type == 'button' else 'Математика'}")
    else:
        await callback.answer()

    settings["_vt_premium"] = await db.is_premium_group(chat_id)
    await safe_edit(callback, 
        "🔐 Настройка защиты", reply_markup=protection_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("fl:"))
async def filter_links_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["filter_links"]["enabled"] = not settings["filter_links"]["enabled"]
        await db.save_settings(chat_id, settings)
        status = "включён" if settings["filter_links"]["enabled"] else "выключен"
        await callback.answer(f"Фильтр ссылок {status}")
    elif action == "action":
        await safe_edit(callback, 
            "Выберите действие для ссылок:",
            reply_markup=link_action_menu()
        )
        await callback.answer()
        return
    elif action == "a":
        act = parts[2]
        settings["filter_links"]["action"] = act
        await db.save_settings(chat_id, settings)
        labels = {"delete": "Удаление", "warn": "Предупреждение", "mute": "Мут"}
        await callback.answer(f"Действие: {labels.get(act, act)}")

    settings["_vt_premium"] = await db.is_premium_group(chat_id)
    await safe_edit(callback, 
        "🔐 Настройка защиты", reply_markup=protection_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("m:"))
async def mute_filter_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["filter_mute"]["enabled"] = not settings["filter_mute"]["enabled"]
        await db.save_settings(chat_id, settings)
        status = "включён" if settings["filter_mute"]["enabled"] else "выключен"
        await callback.answer(f"Фильтр мата {status}")
    elif action == "replace":
        if len(parts) == 2:
            await safe_edit(callback, 
                "Выберите режим обработки мата:",
                reply_markup=mute_action_menu()
            )
            await callback.answer()
            return
        else:
            settings["filter_mute"]["replace_with_stars"] = (parts[2] == "on")
            await db.save_settings(chat_id, settings)
            await callback.answer(f"Режим: {'Замена' if settings['filter_mute']['replace_with_stars'] else 'Удаление'}")

    settings["_vt_premium"] = await db.is_premium_group(chat_id)
    await safe_edit(callback, 
        "🔐 Настройка защиты", reply_markup=protection_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("s:"))
async def settings_callbacks(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    toggles = {
        "warn_system": ("warn_system",),
        "ban_bots": ("auto_ban_bots",),
        "min_age": (),
        "no_avatar": ("block_no_avatar",),
        "invite": ("invite_block",),
        "logging": ("logging_enabled",),
        "reports": ("report_enabled",),
        "clear": ("clear_chat_enabled",),
        "commands": ("block_bot_commands",),
        "count_cmds": ("count_commands_as_spam",),
    }

    if action in toggles:
        keys = toggles[action]
        if keys:
            key = keys[0]
            settings[key] = not settings.get(key, True)
            await db.save_settings(chat_id, settings)
            await callback.answer(f"{'Включено' if settings[key] else 'Выключено'}")
            await safe_edit(callback, 
                "⚙️ Настройки", reply_markup=settings_menu(settings)
            )
            return

    if action == "warn_count":
        await safe_edit(callback, 
            "Выберите количество предупреждений до мута:",
            reply_markup=warn_count_menu()
        )
        await callback.answer()
        return
    elif action == "w":
        try:
            count = int(parts[2])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректное значение", show_alert=True)
            return
        if count not in (1, 2, 3, 5, 10):
            await callback.answer("❌ Недопустимое количество", show_alert=True)
            return
        settings["auto_mute_after_warns"] = count
        await db.save_settings(chat_id, settings)
        await callback.answer(f"После {count} предупреждений — мут")
    elif action == "extra":
        await callback.answer("Дополнительные настройки")
    elif action.startswith("extra_"):
        extra_idx = int(action.split("_")[1])
        extra_toggles = [
            "captcha_for_suspicious",
            "duplicate_block",
            "mention_block",
            "forward_block",
            "mask_check",
            "auto_ban_spam",
        ]
        if extra_idx < len(extra_toggles):
            key = extra_toggles[extra_idx]
            settings[key] = not settings.get(key, True)
            await db.save_settings(chat_id, settings)
            await callback.answer(f"{'Включено' if settings[key] else 'Выключено'}")

    await callback.answer()
    await safe_edit(callback, 
        "⚙️ Настройки", reply_markup=settings_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("st:"))
async def stats_callbacks(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    settings = await db.get_settings(chat_id)
    is_premium = await db.is_premium_group(chat_id)

    if action == "period":
        if not await is_admin(chat_id, user_id):
            await callback.answer("❌ Только для администраторов", show_alert=True)
            return

    if action == "period":
        periods = ["day", "week", "month"]
        current = settings.get("stats_period", "week")
        idx = (periods.index(current) + 1) % len(periods) if current in periods else 0
        settings["stats_period"] = periods[idx]
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Период: {periods[idx]}")

    elif action == "refresh":
        pass

    elif action == "top":
        if not is_premium:
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        violators = await db.get_top_violators(chat_id, settings.get("stats_period", "week"))
        text = "🏆 <b>Топ нарушителей</b>\n\n"
        if violators:
            for i, (uid, cnt) in enumerate(violators[:10], 1):
                text += f"{i}. <code>{uid}</code> — {cnt} нарушений\n"
        else:
            text += "Нет данных."
        await safe_edit(callback, text, reply_markup=stats_menu(settings, is_premium))
        await callback.answer()
        return

    elif action == "extended":
        if not is_premium:
            await callback.answer("❌ Только для премиум-групп", show_alert=True)
            return
        stats = await db.get_stats(chat_id, settings.get("stats_period", "week"))
        violators = await db.get_top_violators(chat_id, settings.get("stats_period", "week"), 5)
        period_label = {"day": "день", "week": "неделю", "month": "месяц"}.get(
            settings.get("stats_period", "week"), "неделю"
        )
        text = (
            f"📈 <b>Расширенная статистика за {period_label}</b>\n\n"
            f"⛔ Банов: {stats['bans']}\n"
            f"🔇 Мутов: {stats['mutes']}\n"
            f"🗑 Удалено: {stats['deletes']}\n"
            f"⚠️ Предупреждений: {stats['warns']}\n\n"
            f"<b>Топ-5 нарушителей:</b>\n"
        )
        if violators:
            for uid, cnt in violators:
                text += f"• <code>{uid}</code> — {cnt}\n"
        else:
            text += "Нет данных."
        await safe_edit(callback, text, reply_markup=stats_menu(settings, is_premium))
        await callback.answer()
        return

    await callback.answer()
    await menu_callback(callback)


@router.callback_query(lambda c: c.data.startswith("logs:"))
async def logs_callbacks(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if action == "refresh":
        await menu_callback(callback)
        await callback.answer("Обновлено")
    elif action == "clear":
        await callback.answer("Логи можно очистить только через БД", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("g:"))
async def greeting_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["greeting"]["enabled"] = not settings["greeting"].get("enabled", True)
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Приветствие {'включено' if settings['greeting']['enabled'] else 'выключено'}")
        await safe_edit(callback, 
            "👋 Приветствие", reply_markup=greeting_menu(settings)
        )
    elif action == "edit":
        await safe_edit(callback, 
            "✏️ Введите новый текст приветствия.\n"
            "Используйте <code>{username}</code> для вставки имени пользователя."
        )
        await state.set_state(SettingsStates.waiting_greeting)

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("f:"))
async def farewell_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "t":
        settings["farewell"]["enabled"] = not settings["farewell"].get("enabled", True)
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Прощание {'включено' if settings['farewell']['enabled'] else 'выключено'}")
        await safe_edit(callback, 
            "🚪 Прощание", reply_markup=farewell_menu(settings)
        )
    elif action == "edit":
        await safe_edit(callback, 
            "✏️ Введите новый текст прощания.\n"
            "Используйте <code>{username}</code> для вставки имени пользователя."
        )
        await state.set_state(SettingsStates.waiting_farewell)

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("wl:"))
async def whitelist_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return

    if not await db.is_premium_group(chat_id):
        await callback.answer("❌ Только для премиум-групп", show_alert=True)
        return

    if action == "add":
        await safe_edit(callback, 
            "➕ Введите ID пользователя для добавления в белый список:"
        )
        await state.set_state(SettingsStates.waiting_whitelist_user_add)
    elif action == "remove":
        await safe_edit(callback, 
            "➖ Введите ID пользователя для удаления из белого списка:"
        )
        await state.set_state(SettingsStates.waiting_whitelist_user_remove)
    elif action == "list":
        settings = await db.get_settings(chat_id)
        wl = settings.get("whitelist", [])
        text = "👥 <b>Белый список</b>\n\n"
        if wl:
            text += "\n".join(f"• <code>{uid}</code>" for uid in wl)
        else:
            text += "Список пуст."
        await safe_edit(callback, text, reply_markup=whitelist_menu())

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("bl:"))
async def blacklist_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if action == "add_word":
        await safe_edit(callback, 
            "➕ Введите слово для добавления в чёрный список:"
        )
        await state.set_state(SettingsStates.waiting_blacklist_word)
    elif action == "remove_word":
        await safe_edit(callback, 
            "➖ Введите слово для удаления из чёрного списка:"
        )
        await state.set_state(SettingsStates.waiting_blacklist_word_remove)
    elif action == "list_words":
        words = settings.get("blacklist_words", [])
        text = "⛔ <b>Чёрный список слов</b>\n\n"
        if words:
            text += "\n".join(f"• {w}" for w in words)
        else:
            text += "Список пуст."
        await safe_edit(callback, text, reply_markup=blacklist_menu())

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("nm:"))
async def night_mode_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if not await db.is_premium_group(chat_id):
        await callback.answer("❌ Только для премиум-групп", show_alert=True)
        return

    if action == "t":
        enabled = settings.get("night_mode", {}).get("enabled", False)
        settings.setdefault("night_mode", {})["enabled"] = not enabled
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Ночной режим {'включён' if not enabled else 'выключен'}")
    elif action == "start":
        await safe_edit(callback, 
            "⏰ Введите час начала ночного режима (0-23):"
        )
        await state.set_state(SettingsStates.waiting_night_start)
        await callback.answer()
        return
    elif action == "end":
        await safe_edit(callback, 
            "⏰ Введите час окончания ночного режима (0-23):"
        )
        await state.set_state(SettingsStates.waiting_night_end)
        await callback.answer()
        return
    elif action == "action":
        actions = ["mute", "ban", "warn"]
        current = settings.get("night_mode", {}).get("action", "mute")
        idx = (actions.index(current) + 1) % len(actions) if current in actions else 0
        settings.setdefault("night_mode", {})["action"] = actions[idx]
        await db.save_settings(chat_id, settings)
        labels = {"mute": "Мут", "ban": "Бан", "warn": "Предупреждение"}
        await callback.answer(f"Действие: {labels[actions[idx]]}")

    await safe_edit(callback, 
        "🌙 Ночной режим", reply_markup=night_mode_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("dr:"))
async def daily_rules_callbacks(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return
    settings = await db.get_settings(chat_id)

    if not await db.is_premium_group(chat_id):
        await callback.answer("❌ Только для премиум-групп", show_alert=True)
        return

    if action == "t":
        enabled = settings.get("daily_rules", {}).get("enabled", False)
        settings.setdefault("daily_rules", {})["enabled"] = not enabled
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Автопостинг {'включён' if not enabled else 'выключен'}")
    elif action == "time":
        await safe_edit(callback, 
            "⏰ Введите время для автопостинга (ЧЧ:ММ, например 09:00):"
        )
        await state.set_state(SettingsStates.waiting_daily_rules_time)
        await callback.answer()
        return
    elif action == "edit":
        await safe_edit(callback, 
            "✏️ Введите новый текст правил:"
        )
        await state.set_state(SettingsStates.waiting_daily_rules_text)
        await callback.answer()
        return

    await safe_edit(callback, 
        "📋 Автопостинг правил", reply_markup=daily_rules_menu(settings)
    )


@router.callback_query(lambda c: c.data.startswith("reports:"))
async def reports_callbacks(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if action == "refresh":
        await menu_callback(callback)


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
        await safe_edit(callback, 
            f"✅ {esc(callback.from_user.first_name)}, капча пройдена! Добро пожаловать."
        )
        await callback.answer("✅ Капча пройдена!")
    else:
        await callback.answer("❌ Нет активной капчи", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("bayes:"))
async def bayes_callbacks(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return

    if action == "toggle":
        settings = await db.get_settings(chat_id)
        settings["bayes_enabled"] = not settings.get("bayes_enabled", True)
        await db.save_settings(chat_id, settings)
        status = "включён" if settings["bayes_enabled"] else "выключен"
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback,
            "🧠 Настройка байесовского фильтра",
            reply_markup=protection_menu(settings)
        )
        await callback.answer(f"Байес {status}")
        return

    elif action == "threshold":
        await safe_edit(callback,
            "🎯 Выберите порог чувствительности:\n"
            "Чем выше порог, тем реже будут ложные срабатывания.",
            reply_markup=bayes_threshold_menu()
        )
        await callback.answer()
        return

    elif action == "set_threshold":
        try:
            threshold = float(parts[2])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректное значение", show_alert=True)
            return
        if threshold not in (0.5, 0.6, 0.7, 0.8, 0.9):
            await callback.answer("❌ Недопустимый порог", show_alert=True)
            return
        settings = await db.get_settings(chat_id)
        settings["bayes_threshold"] = threshold
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Порог: {threshold:.0%}")
        settings["_vt_premium"] = await db.is_premium_group(chat_id)
        await safe_edit(callback,
            "🧠 Настройка байесовского фильтра",
            reply_markup=protection_menu(settings)
        )
        return

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("vt:"))
async def virus_total_callbacks(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return

    if action == "premium_locked":
        await callback.answer("⚠️ Эта функция доступна только для премиум-групп", show_alert=True)
        return

    if not await db.is_premium_group(chat_id):
        await callback.answer("⚠️ Эта функция доступна только для премиум-групп", show_alert=True)
        return

    settings = await db.get_settings(chat_id)
    vt_enabled = settings.get("virus_total_enabled", False)

    if action == "toggle":
        settings["virus_total_enabled"] = not vt_enabled
        await db.save_settings(chat_id, settings)
        status = "включена" if settings["virus_total_enabled"] else "выключена"
        await callback.answer(f"✅ Проверка ссылок VirusTotal {status}")
        settings["_vt_premium"] = True
        await safe_edit(callback,
            "🛡️ <b>VirusTotal</b>\n\n"
            "Автоматическая проверка ссылок на вирусы через VirusTotal API.",
            reply_markup=protection_menu(settings)
        )

    elif action == "files":
        sub = callback.data.split(":")[2] if len(callback.data.split(":")) > 2 else ""
        if sub == "toggle":
            files_enabled = settings.get("virus_total_scan_files", False)
            settings["virus_total_scan_files"] = not files_enabled
            await db.save_settings(chat_id, settings)
            status = "включено" if settings["virus_total_scan_files"] else "выключено"
            await callback.answer(f"✅ Сканирование файлов {status}")
            settings["_vt_premium"] = True
            await safe_edit(callback,
                "🛡️ <b>VirusTotal</b>\n\n"
                "Автоматическая проверка ссылок и файлов на вирусы.",
                reply_markup=protection_menu(settings)
            )


@router.callback_query(lambda c: c.data.startswith("p:"))
async def premium_callbacks(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if action == "buy":
        sub_type = parts[2]
        if sub_type == "personal":
            if not await is_admin(chat_id, user_id):
                await callback.answer("❌ Только для администраторов", show_alert=True)
                return
            await bot.send_invoice(
                chat_id=chat_id,
                title="Личный премиум",
                description="Доступ ко всем премиум-функциям на 30 дней",
                payload="personal_premium",
                currency="XTR",
                prices=[{"label": "30 дней", "amount": 10}],
                start_parameter="personal_premium_30",
            )
        elif sub_type == "group":
            if not await is_admin(chat_id, user_id):
                await callback.answer("❌ Только админы могут купить групповой премиум", show_alert=True)
                return
            await bot.send_invoice(
                chat_id=chat_id,
                title="Премиум для группы",
                description="Доступ ко всем премиум-функциям для группы на 30 дней",
                payload="group_premium",
                currency="XTR",
                prices=[{"label": "30 дней", "amount": 5}],
                start_parameter="group_premium_30",
            )
    elif action == "info_user":
        is_premium = await db.is_premium_user(user_id)
        if is_premium:
            await callback.answer("✅ Личный премиум активен", show_alert=True)
        else:
            await callback.answer("❌ Личный премиум не активен", show_alert=True)
    elif action == "info_group":
        is_premium = await db.is_premium_group(chat_id)
        if is_premium:
            await callback.answer("✅ Групповой премиум активен", show_alert=True)
        else:
            await callback.answer("❌ Групповой премиум не активен", show_alert=True)

    await callback.answer()

