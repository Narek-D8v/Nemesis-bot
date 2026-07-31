import re

import aiosqlite
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot import logger
from db import db
from utils import esc
from keyboards import (
    farewell_menu, greeting_menu, whitelist_menu,
    blacklist_menu, daily_rules_menu, night_mode_menu,
    protection_menu, group_tools_menu,
)
from handlers.states import SettingsStates, ProfileStates
from handlers.messages import is_admin
from handlers import _pending_edits

router = Router()


def _get_stored_chat_id(user_id: int) -> int | None:
    edit = _pending_edits.get(user_id)
    if edit:
        return edit.get("chat_id")
    return None


@router.message(SettingsStates.waiting_greeting)
async def set_greeting(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    settings.setdefault("greeting", {})["text"] = message.text
    await db.save_settings(chat_id, settings)
    _pending_edits.pop(user_id, None)
    await state.clear()
    await message.answer(
        f"✅ Приветствие обновлено!\n\n{message.text}",
        reply_markup=greeting_menu(settings)
    )
    logger.info(f"Greeting updated in {chat_id}")


@router.message(SettingsStates.waiting_farewell)
async def set_farewell(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    settings.setdefault("farewell", {})["text"] = message.text
    await db.save_settings(chat_id, settings)
    _pending_edits.pop(user_id, None)
    await state.clear()
    await message.answer(
        f"✅ Прощание обновлено!\n\n{message.text}",
        reply_markup=farewell_menu(settings)
    )
    logger.info(f"Farewell updated in {chat_id}")


@router.message(SettingsStates.waiting_blacklist_word)
async def add_blacklist_word(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    word = message.text.lower().strip()
    if word and word not in settings.get("blacklist_words", []):
        settings.setdefault("blacklist_words", []).append(word)
        await db.save_settings(chat_id, settings)
        await message.answer(
            f"✅ Слово «{word}» добавлено в чёрный список!",
            reply_markup=blacklist_menu()
        )
    else:
        await message.answer(
            "❌ Слово уже в списке или пустое.",
            reply_markup=blacklist_menu()
        )
    await state.clear()


@router.message(SettingsStates.waiting_blacklist_word_remove)
async def remove_blacklist_word(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    word = message.text.lower().strip()
    if word in settings.get("blacklist_words", []):
        settings["blacklist_words"] = [w for w in settings["blacklist_words"] if w != word]
        await db.save_settings(chat_id, settings)
        await message.answer(
            f"✅ Слово «{word}» удалено из чёрного списка!",
            reply_markup=blacklist_menu()
        )
    else:
        await message.answer(
            "❌ Слово не найдено в списке.",
            reply_markup=blacklist_menu()
        )
    await state.clear()


@router.message(SettingsStates.waiting_whitelist_user_add)
async def add_whitelist_user(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    try:
        target_id = int(message.text.strip())
        if target_id not in settings.get("whitelist", []):
            settings.setdefault("whitelist", []).append(target_id)
            await db.save_settings(chat_id, settings)
            await message.answer(
                f"✅ Пользователь {target_id} добавлен в белый список!",
                reply_markup=whitelist_menu()
            )
        else:
            await message.answer(
                "❌ Пользователь уже в белом списке.",
                reply_markup=whitelist_menu()
            )
    except ValueError:
        await message.answer(
            "❌ Введите числовой ID пользователя.",
            reply_markup=whitelist_menu()
        )
    await state.clear()


@router.message(SettingsStates.waiting_whitelist_user_remove)
async def remove_whitelist_user(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    settings = await db.get_settings(chat_id)
    try:
        target_id = int(message.text.strip())
        whitelist = settings.get("whitelist", [])
        if target_id in whitelist:
            settings["whitelist"] = [uid for uid in whitelist if uid != target_id]
            await db.save_settings(chat_id, settings)
            await message.answer(
                f"✅ Пользователь {target_id} удалён из белого списка!",
                reply_markup=whitelist_menu()
            )
        else:
            await message.answer(
                "❌ Пользователь не найден в списке.",
                reply_markup=whitelist_menu()
            )
    except ValueError:
        await message.answer(
            "❌ Введите числовой ID пользователя.",
            reply_markup=whitelist_menu()
        )
    await state.clear()


@router.message(SettingsStates.waiting_daily_rules_text)
async def set_daily_rules_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    content = message.text.strip()
    if not content:
        await message.reply("❌ Текст не может быть пустым.")
        return
    from plugins.group_tools.handlers import _adjust_entities_json, MAX_RULES_LENGTH
    if len(content) > MAX_RULES_LENGTH:
        await message.reply(
            f"❌ Текст слишком длинный! Максимум {MAX_RULES_LENGTH} символов.\n"
            f"Сейчас {len(content)} символов. Пожалуйста, сократите."
        )
        return
    entities_json = _adjust_entities_json(message, content, 0, content)
    settings = await db.get_settings(chat_id)
    settings.setdefault("daily_rules", {})["text"] = content
    settings["daily_rules"]["entities_json"] = entities_json
    await db.save_settings(chat_id, settings)
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO group_rules (chat_id, text, entities_json) VALUES (?, ?, ?)",
            (chat_id, content, entities_json)
        )
        await conn.commit()
    _pending_edits.pop(user_id, None)
    await state.clear()
    await message.answer(
        "✅ Текст правил обновлён!",
        reply_markup=daily_rules_menu(settings)
    )


@router.message(SettingsStates.waiting_daily_rules_time)
async def set_daily_rules_time(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    time_str = message.text.strip()
    if re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
            settings = await db.get_settings(chat_id)
            settings.setdefault("daily_rules", {})["time"] = time_str
            await db.save_settings(chat_id, settings)
            _pending_edits.pop(user_id, None)
            await state.clear()
            await message.answer(
                f"✅ Время автопостинга: {time_str}",
                reply_markup=daily_rules_menu(settings)
            )
            return
    await message.answer("❌ Неверный формат. Используйте ЧЧ:ММ (например, 09:00)")


@router.message(SettingsStates.waiting_night_start)
async def set_night_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    if not await db.is_premium_group(chat_id):
        await message.reply("❌ Ночной режим доступен только для премиум-групп.")
        await state.clear()
        return
    try:
        hour = int(message.text.strip())
        if 0 <= hour < 24:
            settings = await db.get_settings(chat_id)
            settings.setdefault("night_mode", {})["start"] = hour
            await db.save_settings(chat_id, settings)
            _pending_edits.pop(user_id, None)
            await state.clear()
            await message.answer(
                f"✅ Начало ночного режима: {hour}:00",
                reply_markup=night_mode_menu(settings)
            )
            return
    except ValueError:
        pass
    await message.answer("❌ Введите час от 0 до 23")


@router.message(SettingsStates.waiting_night_end)
async def set_night_end(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    if not await db.is_premium_group(chat_id):
        await message.reply("❌ Ночной режим доступен только для премиум-групп.")
        await state.clear()
        return
    try:
        hour = int(message.text.strip())
        if 0 <= hour < 24:
            settings = await db.get_settings(chat_id)
            settings.setdefault("night_mode", {})["end"] = hour
            await db.save_settings(chat_id, settings)
            _pending_edits.pop(user_id, None)
            await state.clear()
            await message.answer(
                f"✅ Конец ночного режима: {hour}:00",
                reply_markup=night_mode_menu(settings)
            )
            return
    except ValueError:
        pass
    await message.answer("❌ Введите час от 0 до 23")


@router.message(SettingsStates.waiting_night_action)
async def set_night_action(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        return
    if not await db.is_premium_group(chat_id):
        await message.reply("❌ Ночной режим доступен только для премиум-групп.")
        await state.clear()
        return
    valid = {"мут": "mute", "бан": "ban", "предупреждение": "warn"}
    text = message.text.strip().lower()
    if text in valid:
        settings = await db.get_settings(chat_id)
        settings.setdefault("night_mode", {})["action"] = valid[text]
        await db.save_settings(chat_id, settings)
        await state.clear()
        await message.answer(
            "✅ Действие ночного режима обновлено!",
            reply_markup=night_mode_menu(settings)
        )
    else:
        await message.answer("❌ Введите: мут, бан или предупреждение")


@router.message(SettingsStates.waiting_antispam_threshold)
async def set_antispam_threshold(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        await state.clear()
        return
    try:
        threshold = int(message.text.strip())
        if threshold < 1:
            await message.answer("❌ Порог должен быть больше 0")
            return
    except ValueError:
        await message.answer("❌ Введите целое число (например, 25)")
        return
    settings = await db.get_settings(chat_id)
    settings["antispam"]["threshold"] = threshold
    await db.save_settings(chat_id, settings)
    _pending_edits.pop(user_id, None)
    await state.clear()
    await message.answer(
        f"✅ Порог антиспама установлен: {threshold} сообщений/мин",
        reply_markup=protection_menu(settings)
    )
    logger.info(f"Antispam threshold set to {threshold} in {chat_id}")


@router.message(SettingsStates.waiting_gt_rules_text)
async def set_gt_rules_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        await state.clear()
        return
    content = message.text.strip()
    if not content:
        await message.answer("❌ Текст не может быть пустым.")
        return
    from plugins.group_tools.handlers import _adjust_entities_json, MAX_RULES_LENGTH
    if len(content) > MAX_RULES_LENGTH:
        await message.answer(
            f"❌ Текст слишком длинный! Максимум {MAX_RULES_LENGTH} символов.\n"
            f"Сейчас {len(content)} символов. Пожалуйста, сократите."
        )
        return
    entities_json = _adjust_entities_json(message, content, 0, content)
    settings = await db.get_settings(chat_id)
    settings.setdefault("daily_rules", {})["text"] = content
    settings["daily_rules"]["entities_json"] = entities_json
    settings["daily_rules"]["enabled"] = True
    await db.save_settings(chat_id, settings)
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO group_rules (chat_id, text, entities_json) VALUES (?, ?, ?)",
            (chat_id, content, entities_json)
        )
        await conn.commit()
    await state.clear()
    await message.answer(
        "✅ Текст правил сохранён, автопостинг включён!",
        reply_markup=await group_tools_menu(settings, chat_id)
    )
    logger.info(f"Group tools: rules updated in {chat_id}")


@router.message(SettingsStates.waiting_gt_rules_time)
async def set_gt_rules_time(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        await state.clear()
        return
    time_str = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await message.answer("❌ Неверный формат. Используйте ЧЧ:ММ (например, 09:00)")
        return
    settings = await db.get_settings(chat_id)
    settings.setdefault("daily_rules", {})["time"] = time_str
    await db.save_settings(chat_id, settings)
    await state.clear()
    await message.answer(
        f"✅ Время автопостинга правил: {time_str}",
        reply_markup=await group_tools_menu(settings, chat_id)
    )


@router.message(SettingsStates.waiting_gt_autokick_silent)
async def set_gt_autokick_silent(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        await state.clear()
        return
    try:
        days = int(message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число дней (0 — выключить).")
        return
    settings = await db.get_settings(chat_id)
    if days == 0:
        settings.pop("autokick_silent_days", None)
    else:
        settings["autokick_silent_days"] = days
    await db.save_settings(chat_id, settings)
    await state.clear()
    if days == 0:
        await message.answer(
            "✅ Автокик молчунов выключен.",
            reply_markup=await group_tools_menu(settings, chat_id)
        )
    else:
        await message.answer(
            f"✅ Автокик молчунов: {days} дней без сообщений -> кик.",
            reply_markup=await group_tools_menu(settings, chat_id)
        )


@router.message(SettingsStates.waiting_gt_minreg)
async def set_gt_minreg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    if not await is_admin(chat_id, user_id):
        await message.reply("❌ Только для администраторов")
        await state.clear()
        return
    try:
        days = int(message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число дней (0 — выключить).")
        return
    settings = await db.get_settings(chat_id)
    settings["min_account_age_days"] = days
    await db.save_settings(chat_id, settings)
    await state.clear()
    if days == 0:
        await message.answer(
            "✅ Минимальная регистрация отключена.",
            reply_markup=await group_tools_menu(settings, chat_id)
        )
    else:
        await message.answer(
            f"✅ Минимальный возраст аккаунта: {days} дней.",
            reply_markup=await group_tools_menu(settings, chat_id)
        )


async def _finish_profile_edit(message: Message, state: FSMContext, text: str, chat_id: int, user_id: int):
    _pending_edits.pop(user_id, None)
    await state.clear()
    await message.answer(text)
    from plugins.profile.handlers import _show_card
    await _show_card(message, chat_id, user_id)


@router.message(ProfileStates.waiting_gender)
async def set_profile_gender(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import GENDER_MAX
    if not val:
        await message.answer("❌ Пол не может быть пустым.")
        return
    if len(val) > GENDER_MAX:
        await message.answer(f"❌ Пол слишком длинный (макс. {GENDER_MAX} символов).")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, gender) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET gender = ?",
            (user_id, val, val)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ Пол установлен: {esc(val)}", chat_id, user_id)


@router.message(ProfileStates.waiting_city)
async def set_profile_city(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import CITY_MAX, _resolve_city, CITIES_BASE_URL, esc
    if not val:
        await message.answer("❌ Город не может быть пустым.")
        return
    if len(val) > CITY_MAX:
        await message.answer(f"❌ Город слишком длинный (макс. {CITY_MAX} символов).")
        return
    found = _resolve_city(val)
    if not found:
        await message.answer(f"❌ Город «{esc(val)}» не найден в базе. Проверьте название или напишите город полностью.")
        return
    city, city_id = found
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, city) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET city = ?",
            (user_id, city, city)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ Город установлен: {esc(city)} ({CITIES_BASE_URL.format(city_id)})", chat_id, user_id)


@router.message(ProfileStates.waiting_birthday)
async def set_profile_birthday(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import _normalize_bday
    bday = _normalize_bday(val)
    if bday is None:
        await message.answer("❌ Неверная дата. Формат: ДД.ММ.ГГГГ (например, 01.01.2000)")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, birthday) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET birthday = ?",
            (user_id, bday, bday)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ День рождения установлен: {bday}", chat_id, user_id)


@router.message(ProfileStates.waiting_birthday_visibility)
async def set_profile_birthday_visibility(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip().lower()
    from plugins.profile.handlers import _normalize_vis
    vis = _normalize_vis(val)
    if vis not in ("full", "месяц", "год"):
        await message.answer("❌ Варианты: все / месяц / год")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, birthday_visibility) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET birthday_visibility = ?",
            (user_id, vis, vis)
        )
        await conn.commit()
    labels = {"full": "все", "месяц": "месяц и год", "год": "только год"}
    await _finish_profile_edit(message, state, f"✅ Видимость ДР: {labels[vis]}", chat_id, user_id)


@router.message(ProfileStates.waiting_motto)
async def set_profile_motto(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import MOTTO_MAX
    if not val:
        await message.answer("❌ Девиз не может быть пустым.")
        return
    if len(val) > MOTTO_MAX:
        await message.answer(f"❌ Девиз слишком длинный (макс. {MOTTO_MAX} символов).")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, motto) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET motto = ?",
            (user_id, val, val)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ Девиз установлен: «{esc(val)}»", chat_id, user_id)


@router.message(ProfileStates.waiting_description)
async def set_profile_description(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import DESCR_MAX
    if not val:
        await message.answer("❌ Описание не может быть пустым.")
        return
    if len(val) > DESCR_MAX:
        await message.answer(f"❌ Описание слишком длинное (макс. {DESCR_MAX} символов).")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_global (user_id, description) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET description = ?",
            (user_id, val, val)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, "✅ Описание сохранено!", chat_id, user_id)


@router.message(ProfileStates.waiting_nickname)
async def set_profile_nickname(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import NICK_MAX, _get_restriction
    mr = await _get_restriction(chat_id, 'set_nick')
    if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
        await message.reply("❌ Недостаточно прав.")
        await state.clear()
        return
    if not val:
        await message.answer("❌ Ник не может быть пустым.")
        return
    if len(val) > NICK_MAX:
        await message.answer(f"❌ Ник слишком длинный (макс. {NICK_MAX} символов).")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_chat (chat_id, user_id, nickname) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET nickname = ?",
            (chat_id, user_id, val, val)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ Ник установлен: {esc(val)}", chat_id, user_id)


@router.message(ProfileStates.waiting_title)
async def set_profile_title(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = _get_stored_chat_id(user_id) or message.chat.id
    val = message.text.strip()
    from plugins.profile.handlers import TITLE_MAX, _get_restriction
    mr = await _get_restriction(chat_id, 'set_title')
    if (await db.get_user_rank(chat_id, user_id) or 0) < mr:
        await message.reply("❌ Недостаточно прав.")
        await state.clear()
        return
    if not val:
        await message.answer("❌ Звание не может быть пустым.")
        return
    if len(val) > TITLE_MAX:
        await message.answer(f"❌ Звание слишком длинное (макс. {TITLE_MAX} символов).")
        return
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO profile_chat (chat_id, user_id, title) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET title = ?",
            (chat_id, user_id, val, val)
        )
        await conn.commit()
    await _finish_profile_edit(message, state, f"✅ Звание установлено: {esc(val)}", chat_id, user_id)



