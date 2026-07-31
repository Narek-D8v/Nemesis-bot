import aiosqlite

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import bot, logger
from db import db
from utils import esc
from utils.user_name import resolve_name
from keyboards import profile_edit_menu, profile_bdayvis_menu, profile_activity_menu
from handlers.states import ProfileStates
from handlers import _pending_edits
from .common import safe_edit

router = Router()

FIELD_STATES = {
    "gender": ProfileStates.waiting_gender,
    "city": ProfileStates.waiting_city,
    "bday": ProfileStates.waiting_birthday,
    "motto": ProfileStates.waiting_motto,
    "descr": ProfileStates.waiting_description,
    "nick": ProfileStates.waiting_nickname,
    "title": ProfileStates.waiting_title,
}

FIELD_PROMPTS = {
    "gender": "⚤ Введите пол:",
    "city": "🏙️ Введите город:",
    "bday": "🎂 Введите дату рождения (ДД.ММ.ГГГГ, например 01.01.2000):",
    "motto": "💬 Введите девиз:",
    "descr": "📝 Введите описание о себе:",
    "nick": "📛 Введите ник:",
    "title": "🎖️ Введите звание:",
}

BDVIS_STORED = {"full": "full", "month": "месяц", "year": "год"}
BDVIS_LABELS = {"full": "полностью", "month": "месяц и год", "year": "только год"}


async def _user_name(chat_id: int, user_id: int, is_pm: bool) -> str:
    if not is_pm:
        return await resolve_name(chat_id, user_id)
    try:
        chat = await bot.get_chat(user_id)
        return esc(chat.first_name or chat.username or "пользователь")
    except Exception:
        return "пользователь"


async def _own_only(callback: CallbackQuery, target: int, user_id: int) -> bool:
    if target != user_id:
        await callback.answer("❌ Можно управлять только своей анкетой", show_alert=True)
        return False
    return True


@router.callback_query(lambda c: c.data.startswith("pr:"))
async def profile_callbacks(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1]
    target = int(parts[-1]) if len(parts) > 2 and parts[-1].isdigit() else callback.from_user.id
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    from plugins.profile.handlers import _show_card

    if action == "refresh":
        await _show_card(callback.message, chat_id, target, viewer_id=user_id)
        await callback.answer()
        return

    if action == "edit":
        if not await _own_only(callback, target, user_id):
            return
        await callback.message.answer(
            "✏️ <b>Редактирование анкеты</b>\n\nВыберите поле:",
            reply_markup=profile_edit_menu(target)
        )
        await callback.answer()
        return

    if action == "back":
        await _show_card(callback.message, chat_id, user_id, viewer_id=user_id)
        await callback.answer()
        return

    if action == "field":
        if not await _own_only(callback, target, user_id):
            return
        field = parts[2] if len(parts) > 2 else ""
        if field not in FIELD_STATES:
            await callback.answer("❌ Неизвестное поле", show_alert=True)
            return
        _pending_edits[user_id] = {"type": "profile_edit", "chat_id": chat_id}
        await state.set_state(FIELD_STATES[field])
        await safe_edit(callback, FIELD_PROMPTS[field])
        await callback.answer()
        return

    if action == "bdayvis":
        if not await _own_only(callback, target, user_id):
            return
        await safe_edit(callback, "👁 <b>Видимость дня рождения</b>\n\nКто сможет её видеть:", reply_markup=profile_bdayvis_menu(target))
        await callback.answer()
        return

    if action == "bdayvis_set":
        if not await _own_only(callback, target, user_id):
            return
        vis = parts[2] if len(parts) > 2 else "full"
        stored = BDVIS_STORED.get(vis, "full")
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT INTO profile_global (user_id, birthday_visibility) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET birthday_visibility = ?",
                (user_id, stored, stored)
            )
            await conn.commit()
        await safe_edit(callback, f"✅ Видимость ДР: {BDVIS_LABELS[vis]}", reply_markup=profile_bdayvis_menu(target))
        await callback.answer()
        return

    if action == "anketa":
        if not await _own_only(callback, target, user_id):
            return
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT profile_visible FROM profile_chat WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
            cur = row[0] if row else 1
            new = 0 if cur else 1
            await conn.execute(
                "INSERT INTO profile_chat (chat_id, user_id, profile_visible) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET profile_visible = ?",
                (chat_id, user_id, new, new)
            )
            await conn.commit()
        await callback.answer(f"✅ Анкета {'скрыта' if not new else 'показана'}")
        await _show_card(callback.message, chat_id, user_id, viewer_id=user_id)
        return

    if action == "subtoggle":
        if target == user_id:
            await callback.answer("❌ Нельзя подписаться на себя", show_alert=True)
            return
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM profile_subscriptions WHERE subscriber_id = ? AND target_id = ?",
                (user_id, target)
            )
            subbed = bool(await cursor.fetchone())
            if subbed:
                await conn.execute(
                    "DELETE FROM profile_subscriptions WHERE subscriber_id = ? AND target_id = ?",
                    (user_id, target)
                )
                await conn.commit()
                tname = await _user_name(chat_id, target, callback.message.chat.type == "private")
                await callback.message.answer(f"✅ Вы отписались от {tname}.")
            else:
                from plugins.profile.handlers import MAX_SUBS
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM profile_subscriptions WHERE subscriber_id = ?",
                    (user_id,)
                )
                cnt = (await cursor.fetchone())[0]
                if cnt >= MAX_SUBS:
                    await callback.answer(f"❌ Максимум {MAX_SUBS} подписок", show_alert=True)
                    return
                import time
                await conn.execute(
                    "INSERT OR IGNORE INTO profile_subscriptions (subscriber_id, target_id, created_at) VALUES (?, ?, ?)",
                    (user_id, target, int(time.time()))
                )
                await conn.commit()
                tname = await _user_name(chat_id, target, callback.message.chat.type == "private")
                await callback.message.answer(f"✅ Вы подписались на {tname}.")
        await callback.answer()
        return

    if action == "subs":
        if not await _own_only(callback, target, user_id):
            return
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT target_id FROM profile_subscriptions WHERE subscriber_id = ? ORDER BY created_at DESC LIMIT 20",
                (user_id,)
            )
            rows = await cursor.fetchall()
        if not rows:
            await callback.message.answer("Вы ни на кого не подписаны.")
            await callback.answer()
            return
        names = []
        for (tid,) in rows:
            names.append(await _user_name(chat_id, tid, callback.message.chat.type == "private"))
        await callback.message.answer(f"📋 <b>Ваши подписки:</b>\n" + ", ".join(names))
        await callback.answer()
        return

    if action == "actmenu":
        await callback.message.answer(
            "📈 <b>Активность</b>\n\nВыберите период:",
            reply_markup=profile_activity_menu(target)
        )
        await callback.answer()
        return

    if action == "activity":
        days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 14
        from plugins.profile.handlers import send_activity_chart
        await send_activity_chart(callback.message, target, days)
        await callback.answer()
        return

    if action == "awards":
        from plugins.profile.handlers import _format_medals
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute(
                "SELECT achievements_visible FROM profile_global WHERE user_id = ?",
                (target,)
            )
            row = await cursor.fetchone()
            hidden = row and not row[0]
        if hidden and target != user_id:
            await callback.message.answer("🔒 Пользователь скрыл свои награды.")
            await callback.answer()
            return
        name = await _user_name(chat_id, target, callback.message.chat.type == "private")
        medals_text = await _format_medals(chat_id, target)
        if not medals_text:
            await callback.message.answer(f"У {name} пока нет наград.")
        else:
            await callback.message.answer(f"🎖️ <b>Награды {name}:</b>\n" + medals_text)
        await callback.answer()
        return

    await callback.answer("❌ Неизвестная команда", show_alert=True)
