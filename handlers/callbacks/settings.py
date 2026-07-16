from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import db
from utils import apply_aggression_level
from keyboards import (
    protection_menu, settings_menu, threshold_menu,
    captcha_type_menu, link_action_menu, mute_action_menu,
    warn_count_menu, greeting_menu, farewell_menu,
    stats_menu, bayes_threshold_menu, aggression_menu,
    back_to_main,
)
from handlers.states import SettingsStates
from handlers.messages import is_admin
from handlers import _pending_edits
from . import safe_edit

router = Router()


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
        if len(parts) > 2:
            cap_type = parts[2]
            settings["captcha"]["type"] = cap_type
            await db.save_settings(chat_id, settings)
            await callback.answer(f"Тип капчи: {'Кнопка' if cap_type == 'button' else 'Математика'}")
        else:
            await safe_edit(callback, 
                "Выберите тип капчи:",
                reply_markup=captcha_type_menu()
            )
            await callback.answer()
            return
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
        labels = {"delete": "Удаление", "warn": "Предупреждение", "mute": "Мут", "warn_mute": "Warn+Мут", "ban": "Бан"}
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
        if action == "min_age":
            current = settings.get("min_account_age_days", 3)
            if current > 0:
                settings["min_account_age_days"] = 0
                await callback.answer("✅ Возрастная проверка выключена")
            else:
                settings["min_account_age_days"] = 3
                await callback.answer("✅ Возрастная проверка включена (3 дня)")
            await db.save_settings(chat_id, settings)
            await safe_edit(callback, 
                "⚙️ Настройки", reply_markup=settings_menu(settings)
            )
            return
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
        else:
            await callback.answer()
            return
    else:
        await callback.answer()
        return

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
            await callback.answer("❌ Недостаточно прав", show_alert=True)
            return
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
    from . import menu_callback
    await menu_callback(callback)


@router.callback_query(lambda c: c.data.startswith("logs:"))
async def logs_callbacks(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if action == "refresh":
        from . import menu_callback
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
        _pending_edits[user_id] = {"type": "greeting", "chat_id": chat_id}
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
        _pending_edits[user_id] = {"type": "farewell", "chat_id": chat_id}
        await safe_edit(callback,
            "✏️ Введите новый текст прощания.\n"
            "Используйте <code>{username}</code> для вставки имени пользователя."
        )
        await state.set_state(SettingsStates.waiting_farewell)

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
