from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import bot
from db import db
from utils import esc
from keyboards import (
    protection_menu, whitelist_menu, blacklist_menu,
    night_mode_menu, daily_rules_menu, bayes_threshold_menu,
)
from handlers.states import SettingsStates
from handlers.messages import is_admin
from handlers import _pending_edits
from . import safe_edit

router = Router()


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
        _pending_edits[user_id] = {"type": "daily_rules_time", "chat_id": chat_id}
        await safe_edit(callback, 
            "⏰ Введите время для автопостинга (ЧЧ:ММ, например 09:00):"
        )
        await state.set_state(SettingsStates.waiting_daily_rules_time)
        await callback.answer()
        return
    elif action == "edit":
        _pending_edits[user_id] = {"type": "daily_rules_text", "chat_id": chat_id}
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
        from . import menu_callback
        await menu_callback(callback)


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
            try:
                await bot.send_invoice(
                    chat_id=user_id,
                    title="Личный премиум",
                    description="Доступ ко всем премиум-функциям на 30 дней",
                    payload="personal_premium",
                    currency="XTR",
                    prices=[{"label": "30 дней", "amount": 10}],
                    start_parameter="personal_premium_30",
                )
            except Exception:
                await callback.answer("❌ Напишите боту в личные сообщения, чтобы оплатить", show_alert=True)
                return
        elif sub_type == "group":
            if not await is_admin(chat_id, user_id):
                await callback.answer("❌ Только админы могут купить групповой премиум", show_alert=True)
                return
            try:
                payload = f"group_premium:{chat_id}"
                await bot.send_invoice(
                    chat_id=user_id,
                    title="Премиум для группы",
                    description="Доступ ко всем премиум-функциям для группы на 30 дней",
                    payload=payload,
                    currency="XTR",
                    prices=[{"label": "30 дней", "amount": 5}],
                    start_parameter="group_premium_30",
                )
            except Exception:
                await callback.answer("❌ Напишите боту в личные сообщения, чтобы оплатить", show_alert=True)
                return
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
