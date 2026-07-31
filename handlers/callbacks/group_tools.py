import aiosqlite

from aiogram import Router
from aiogram.types import CallbackQuery, ChatPermissions
from aiogram.fsm.context import FSMContext

from bot import bot, logger
from db import db
from keyboards import group_tools_menu
from handlers.states import SettingsStates
from handlers.messages import is_admin
from .common import safe_edit

router = Router()

HELP_TEXT = (
    "❓ <b>Текстовые команды плагина GroupTools</b>\n\n"
    "📋 <b>Правила:</b>\n"
    "<code>+Правила [текст]</code> — установить правила и включить автопостинг\n"
    "<code>-Правила</code> — удалить правила\n"
    "<code>Правила</code> — показать текущие правила\n\n"
    "👋 <b>Приветствие:</b>\n"
    "<code>+Приветствие [текст]</code> / <code>-Приветствие</code> / <code>Приветствие</code>\n\n"
    "👢 <b>Автокик:</b>\n"
    "<code>+Автокик [число] [минуты] [кик/бан]</code> / <code>-Автокик</code>\n"
    "<code>+Автокик молчунов [дней]</code> / <code>-Автокик молчунов</code>\n\n"
    "🚪 <b>Входы/выходы:</b>\n"
    "<code>+Входы</code>, <code>+Выходы</code>, <code>+Входы-Выходы</code> (и с минусом)\n\n"
    "🔓 <b>Чат/топик:</b>\n"
    "<code>+Чат</code> / <code>-Чат</code> — открыть/закрыть чат\n"
    "<code>+Топик</code> / <code>-Топик</code> — открыть/закрыть топик\n\n"
    "👮 <b>Телеграм-админ:</b>\n"
    "<code>+Тг админ [Должность] @user</code> — назначить\n"
    "<code>-Тг админ @user</code> — снять\n"
    "<code>Тг права @user</code> — показать права\n"
    "<code>+Тг тег Текст @user</code> / <code>-Тг тег @user</code>\n\n"
    "📡 <b>Прочее:</b>\n"
    "<code>+Каналы</code> / <code>-Каналы</code> — разрешить/заблокировать каналы\n"
    "<code>+Минрег [дней]</code> / <code>-Минрег</code>\n"
    "<code>+Автозаявки</code> / <code>-Автозаявки</code>\n"
    "<code>Проверить в чате @user</code>"
)


@router.callback_query(lambda c: c.data.startswith("gt:"))
async def group_tools_callbacks(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if action == "help":
        await safe_edit(callback, HELP_TEXT)
        await callback.answer()
        return

    if not await is_admin(chat_id, user_id):
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return

    settings = await db.get_settings(chat_id)

    if action == "rules_toggle":
        rules = settings.setdefault("daily_rules", {})
        rules["enabled"] = not rules.get("enabled", False)
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Автопостинг правил {'включён' if rules['enabled'] else 'выключен'}")
    elif action == "rules_time":
        await state.set_state(SettingsStates.waiting_gt_rules_time)
        await safe_edit(callback, "⏰ Введите время автопостинга (ЧЧ:ММ, например 09:00):")
        await callback.answer()
        return
    elif action == "rules_edit":
        await state.set_state(SettingsStates.waiting_gt_rules_text)
        await safe_edit(callback, "✏️ Введите текст правил (до 3000 символов):")
        await callback.answer()
        return
    elif action == "join_leave":
        settings["show_join_leave"] = not settings.get("show_join_leave", True)
        settings["show_join"] = settings["show_join_leave"]
        settings["show_leave"] = settings["show_join_leave"]
        await db.save_settings(chat_id, settings)
        await callback.answer(
            f"Уведомления о входах/выходах {'включены' if settings['show_join_leave'] else 'выключены'}"
        )
    elif action == "autokick":
        settings["autokick_on_exit"] = not settings.get("autokick_on_exit", False)
        await db.save_settings(chat_id, settings)
        await callback.answer(f"Автокик {'включён' if settings['autokick_on_exit'] else 'выключен'}")
    elif action == "autokick_silent":
        await state.set_state(SettingsStates.waiting_gt_autokick_silent)
        await safe_edit(callback, "👢 Введите количество дней без сообщений (0 — выключить):")
        await callback.answer()
        return
    elif action == "autojoin":
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT enabled FROM auto_join_requests WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            cur = bool(row and row[0])
            await conn.execute(
                "INSERT OR REPLACE INTO auto_join_requests (chat_id, enabled) VALUES (?, ?)",
                (chat_id, int(not cur))
            )
            await conn.commit()
        await callback.answer(f"Автозаявки {'включены' if not cur else 'выключены'}")
    elif action == "channels":
        settings["block_channels"] = not settings.get("block_channels", False)
        await db.save_settings(chat_id, settings)
        await callback.answer(
            f"Сообщения от каналов {'заблокированы' if settings['block_channels'] else 'разрешены'}"
        )
    elif action == "minreg":
        await state.set_state(SettingsStates.waiting_gt_minreg)
        await safe_edit(callback, "📅 Введите минимальный возраст аккаунта в днях (0 — выключить):")
        await callback.answer()
        return
    elif action == "chat_open":
        try:
            await bot.set_chat_permissions(
                chat_id,
                permissions=ChatPermissions(
                    can_send_messages=True, can_send_media_messages=True,
                    can_send_polls=True, can_send_other_messages=True,
                    can_add_web_page_previews=True, can_change_info=False,
                    can_invite_users=True, can_pin_messages=False,
                ),
            )
            await callback.answer("✅ Чат открыт")
            logger.info(f"Chat opened in {chat_id} by {user_id}")
        except Exception as e:
            await callback.answer(f"❌ Не удалось открыть чат: {e}", show_alert=True)
            return
    elif action == "chat_close":
        try:
            await bot.set_chat_permissions(
                chat_id,
                permissions=ChatPermissions(
                    can_send_messages=False, can_send_media_messages=False,
                    can_send_polls=False, can_send_other_messages=False,
                    can_add_web_page_previews=False, can_change_info=False,
                    can_invite_users=False, can_pin_messages=False,
                ),
            )
            await callback.answer("✅ Чат закрыт")
            logger.info(f"Chat closed in {chat_id} by {user_id}")
        except Exception as e:
            await callback.answer(f"❌ Не удалось закрыть чат: {e}", show_alert=True)
            return
    else:
        await callback.answer("❌ Неизвестная команда", show_alert=True)
        return

    await safe_edit(
        callback,
        "🛠 <b>Инструменты группы</b>\n\nУправление функциями плагина GroupTools:",
        reply_markup=await group_tools_menu(settings, chat_id)
    )
    await callback.answer()
