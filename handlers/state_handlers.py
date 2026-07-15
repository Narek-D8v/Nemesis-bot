import re

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot import logger
from db import db
from keyboards import (
    farewell_menu, greeting_menu, whitelist_menu,
    blacklist_menu, daily_rules_menu, night_mode_menu,
)
from handlers.states import SettingsStates
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
        settings["blacklist_words"].append(word)
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
        settings["blacklist_words"].remove(word)
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
            whitelist.remove(target_id)
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
    settings = await db.get_settings(chat_id)
    settings.setdefault("daily_rules", {})["text"] = message.text
    await db.save_settings(chat_id, settings)
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



