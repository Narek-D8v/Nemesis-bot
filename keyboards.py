from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔐 Защита", callback_data="menu:protection"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")
    )
    b.row(
        InlineKeyboardButton(text="💎 Премиум", callback_data="menu:premium"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")
    )
    b.row(
        InlineKeyboardButton(text="📋 Логи", callback_data="menu:logs"),
        InlineKeyboardButton(text="👥 Админы", callback_data="menu:admins")
    )
    b.row(
        InlineKeyboardButton(text="🛠 Инструменты", callback_data="menu:group_tools"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile")
    )
    return b.as_markup()


def profile_edit_menu(target_id: int):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="⚤ Пол", callback_data=f"pr:field:gender:{target_id}"),
        InlineKeyboardButton(text="🏙️ Город", callback_data=f"pr:field:city:{target_id}"),
    )
    b.row(
        InlineKeyboardButton(text="🎂 День рождения", callback_data=f"pr:field:bday:{target_id}"),
        InlineKeyboardButton(text="👁 Видимость ДР", callback_data=f"pr:bdayvis:{target_id}"),
    )
    b.row(
        InlineKeyboardButton(text="💬 Девиз", callback_data=f"pr:field:motto:{target_id}"),
        InlineKeyboardButton(text="📝 Описание", callback_data=f"pr:field:descr:{target_id}"),
    )
    b.row(
        InlineKeyboardButton(text="📛 Ник", callback_data=f"pr:field:nick:{target_id}"),
        InlineKeyboardButton(text="🎖️ Звание", callback_data=f"pr:field:title:{target_id}"),
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"pr:back:{target_id}"))
    return b.as_markup()


def profile_bdayvis_menu(target_id: int):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🗓 Полностью", callback_data=f"pr:bdayvis_set:full:{target_id}"),
        InlineKeyboardButton(text="🗓 Месяц и год", callback_data=f"pr:bdayvis_set:month:{target_id}"),
    )
    b.row(
        InlineKeyboardButton(text="🗓 Только год", callback_data=f"pr:bdayvis_set:year:{target_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"pr:edit:{target_id}"),
    )
    return b.as_markup()


def profile_activity_menu(target_id: int):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="7 дней", callback_data=f"pr:activity:7:{target_id}"),
        InlineKeyboardButton(text="14 дней", callback_data=f"pr:activity:14:{target_id}"),
        InlineKeyboardButton(text="30 дней", callback_data=f"pr:activity:30:{target_id}"),
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"pr:back:{target_id}"))
    return b.as_markup()


def protection_menu(settings: dict):
    b = InlineKeyboardBuilder()

    antispam = settings.get("antispam", {})
    antispam_status = "✅ Вкл" if antispam.get("enabled") else "❌ Выкл"
    b.row(
        InlineKeyboardButton(text=f"🚫 Антиспам {antispam_status}", callback_data="a:t"),
        InlineKeyboardButton(text=f"📊 Порог: {antispam.get('threshold', 60)}" if antispam.get('enabled') else "📊 Порог: 🔒", callback_data="a:threshold")
    )

    captcha = settings.get("captcha", {})
    captcha_status = "✅ Вкл" if captcha.get("enabled") else "❌ Выкл"
    captcha_type_label = "🔘 Кнопка" if captcha.get("type") == "button" else "🔢 Математика"
    b.row(
        InlineKeyboardButton(text=f"🧩 Капча {captcha_status}", callback_data="c:t"),
        InlineKeyboardButton(text=captcha_type_label, callback_data="c:type")
    )

    filter_links = settings.get("filter_links", {})
    links_status = "✅ Вкл" if filter_links.get("enabled") else "❌ Выкл"
    links_action = {"delete": "🗑 Удалять", "warn": "⚠️ Предупреждать", "mute": "🔇 Мутить", "warn_mute": "⚠️+🔇", "ban": "⛔ Бан"}.get(
        filter_links.get("action", "delete"), "🗑 Удалять"
    )
    b.row(
        InlineKeyboardButton(text=f"🔗 Ссылки {links_status}", callback_data="fl:t"),
        InlineKeyboardButton(text=links_action, callback_data="fl:action")
    )

    mute = settings.get("filter_mute", {})
    mute_status = "✅ Вкл" if mute.get("enabled") else "❌ Выкл"
    replace_status = "⭐ Замена" if mute.get("replace_with_stars") else "🗑 Удаление"
    b.row(
        InlineKeyboardButton(text=f"🤬 Мат {mute_status}", callback_data="m:t"),
        InlineKeyboardButton(text=replace_status, callback_data="m:replace")
    )

    b.row(
        InlineKeyboardButton(text="🔁 Повторы", callback_data="menu:duplicate"),
        InlineKeyboardButton(text="📢 Упоминания", callback_data="menu:mentions")
    )
    b.row(
        InlineKeyboardButton(text="👋 Приветствие", callback_data="menu:greeting"),
        InlineKeyboardButton(text="🚪 Прощание", callback_data="menu:farewell")
    )

    bayes_enabled = settings.get("bayes_enabled", True)
    b.row(InlineKeyboardButton(
        text=f"🧠 Байес {'✅ Вкл' if bayes_enabled else '❌ Выкл'}",
        callback_data="bayes:toggle"
    ))
    if bayes_enabled:
        threshold = settings.get("bayes_threshold", 0.7)
        b.row(InlineKeyboardButton(
            text=f"🎯 Порог: {threshold:.0%}",
            callback_data="bayes:threshold"
        ))

    vt_enabled = settings.get("virus_total_enabled", False)
    vt_scan_files = settings.get("virus_total_scan_files", False)
    vt_premium = settings.get("_vt_premium", False)
    if vt_premium:
        vt_status = "✅ Вкл" if vt_enabled else "❌ Выкл"
        b.row(InlineKeyboardButton(
            text=f"🛡️ VirusTotal {vt_status}",
            callback_data="vt:toggle"
        ))
        files_status = "✅ Вкл" if vt_scan_files else "❌ Выкл"
        b.row(InlineKeyboardButton(
            text=f"📁 Сканировать файлы {files_status}",
            callback_data="vt:files:toggle"
        ))
    else:
        b.row(InlineKeyboardButton(
            text="🔒 VirusTotal (Premium)",
            callback_data="vt:premium_locked"
        ))

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    return b.as_markup()


async def settings_menu(settings: dict, chat_id: int = 0):
    from db import db
    is_premium = await db.is_premium_group(chat_id) if chat_id else False
    b = InlineKeyboardBuilder()

    warn_system = settings.get("warn_system", True)
    b.row(
        InlineKeyboardButton(
            text=f"⚠️ Предупреждения {'✅' if warn_system else '❌'}",
            callback_data="s:warn_system"
        ),
        InlineKeyboardButton(
            text=f"🔄 После {settings.get('auto_mute_after_warns', 3)}",
            callback_data="s:warn_count"
        )
    )

    bot_ban = settings.get("auto_ban_bots", True)
    b.row(
        InlineKeyboardButton(text=f"🤖 Бан ботов {'✅' if bot_ban else '❌'}", callback_data="s:ban_bots"),
        InlineKeyboardButton(text="📅 Возраст 3дн", callback_data="s:min_age")
    )

    no_avatar = settings.get("block_no_avatar", False)
    b.row(
        InlineKeyboardButton(text=f"🖼 Без аватарки {'✅' if no_avatar else '❌'}", callback_data="s:no_avatar"),
        InlineKeyboardButton(text="🚫 Инвайт-ссылки", callback_data="s:invite")
    )

    enable_logging = settings.get("logging_enabled", True)
    report_enabled = settings.get("report_enabled", True)
    b.row(
        InlineKeyboardButton(text=f"📝 Логи {'✅' if enable_logging else '❌'}", callback_data="s:logging"),
        InlineKeyboardButton(text=f"📮 Репорты {'✅' if report_enabled else '❌'}", callback_data="s:reports")
    )

    clear_chat = settings.get("clear_chat_enabled", True)
    block_commands = settings.get("block_bot_commands", True)
    count_cmds = settings.get("count_commands_as_spam", False)
    b.row(
        InlineKeyboardButton(text=f"🧹 Очистка {'✅' if clear_chat else '❌'}", callback_data="s:clear"),
        InlineKeyboardButton(text=f"🚫 Команды {'✅' if block_commands else '❌'}", callback_data="s:commands")
    )
    b.row(
        InlineKeyboardButton(text=f"📢 Команды = спам {'✅' if count_cmds else '❌'}", callback_data="s:count_cmds")
    )
    b.row(
        InlineKeyboardButton(text="🎯 Уровень агрессивности", callback_data="menu:aggression")
    )

    captcha_susp = settings.get("captcha_for_suspicious", True)
    duplicate = settings.get("duplicate_block", True)
    mention = settings.get("mention_block", True)
    forward = settings.get("forward_block", True)
    mask = settings.get("mask_check", True)
    auto_ban = settings.get("auto_ban_spam", True)

    extra_labels = [
        f"Капча подозр {'✅' if captcha_susp else '❌'}",
        f"Повторы {'✅' if duplicate else '❌'}",
        f"@all {'✅' if mention else '❌'}",
        f"Форварды {'✅' if forward else '❌'}",
        f"Маскировка {'✅' if mask else '❌'}",
        f"Автобан спам {'✅' if auto_ban else '❌'}",
    ]
    for i in range(0, 6, 2):
        btns = []
        for j in range(2):
            if i + j < 6:
                btns.append(InlineKeyboardButton(text=extra_labels[i + j], callback_data=f"s:extra_{i+j}"))
        if btns:
            b.row(*btns)

    aichat_enabled = settings.get("aichat_enabled", True)
    if is_premium:
        b.row(InlineKeyboardButton(
            text=f"🤖 ИИ чат {'✅' if aichat_enabled else '❌'}",
            callback_data="s:aichat"
        ))
    else:
        b.row(InlineKeyboardButton(
            text="🔒 ИИ чат (Premium)",
            callback_data="s:aichat_locked"
        ))

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    return b.as_markup()


def premium_menu(is_premium_user: bool, is_premium_group: bool):
    b = InlineKeyboardBuilder()
    user_status = "✅ Активен" if is_premium_user else "❌ Не активен"
    group_status = "✅ Активен" if is_premium_group else "❌ Не активен"
    b.row(
        InlineKeyboardButton(text=f"👤 Личный: {user_status}", callback_data="p:info_user"),
        InlineKeyboardButton(text=f"👥 Групповой: {group_status}", callback_data="p:info_group")
    )
    b.row(
        InlineKeyboardButton(text="💳 Купить личный (10 ⭐)", callback_data="p:buy:personal"),
        InlineKeyboardButton(text="💳 Купить групповой (5 ⭐)", callback_data="p:buy:group")
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    return b.as_markup()


def stats_menu(settings: dict, is_premium: bool):
    b = InlineKeyboardBuilder()
    period = settings.get("stats_period", "week")
    period_labels = {"day": "📅 День", "week": "📆 Неделя", "month": "📅 Месяц"}
    b.row(
        InlineKeyboardButton(text=f"📊 {period_labels.get(period, 'Неделя')}", callback_data="st:period"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="st:refresh")
    )
    if is_premium:
        b.row(
            InlineKeyboardButton(text="🏆 Топ нарушителей", callback_data="st:top"),
            InlineKeyboardButton(text="📈 Расширенная", callback_data="st:extended")
        )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    return b.as_markup()


def logs_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="logs:refresh"),
        InlineKeyboardButton(text="🗑 Очистить", callback_data="logs:clear")
    )
    b.row(
        InlineKeyboardButton(text="📮 Репорты", callback_data="menu:reports"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )
    return b.as_markup()


def admins_menu(is_premium: bool):
    b = InlineKeyboardBuilder()
    if is_premium:
        b.row(
            InlineKeyboardButton(text="👥 Белый список", callback_data="menu:whitelist"),
            InlineKeyboardButton(text="⛔ Чёрный список", callback_data="menu:blacklist")
        )
        b.row(
            InlineKeyboardButton(text="🌙 Ночной режим", callback_data="menu:night"),
            InlineKeyboardButton(text="📋 Правила (авто)", callback_data="menu:daily_rules")
        )
    else:
        b.row(InlineKeyboardButton(text="💎 Купить премиум для доп. функций", callback_data="menu:premium"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    return b.as_markup()


def threshold_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="10", callback_data="a:s:10"),
        InlineKeyboardButton(text="20", callback_data="a:s:20"),
        InlineKeyboardButton(text="30", callback_data="a:s:30")
    )
    b.row(
        InlineKeyboardButton(text="40", callback_data="a:s:40"),
        InlineKeyboardButton(text="50", callback_data="a:s:50"),
        InlineKeyboardButton(text="60", callback_data="a:s:60")
    )
    b.row(
        InlineKeyboardButton(text="✏️ Свой", callback_data="a:s:custom"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection")
    )
    return b.as_markup()


def captcha_type_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔘 Кнопка", callback_data="c:type:button"),
        InlineKeyboardButton(text="🔢 Математика", callback_data="c:type:math")
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection"))
    return b.as_markup()


def link_action_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🗑 Удалять", callback_data="fl:a:delete"),
        InlineKeyboardButton(text="⚠️ Предупреждать", callback_data="fl:a:warn")
    )
    b.row(
        InlineKeyboardButton(text="🔇 Мутить", callback_data="fl:a:mute"),
        InlineKeyboardButton(text="⚠️+🔇 Warn+Mute", callback_data="fl:a:warn_mute")
    )
    b.row(
        InlineKeyboardButton(text="⛔ Банить", callback_data="fl:a:ban"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection")
    )
    return b.as_markup()


def mute_action_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="⭐ Замена на ***", callback_data="m:replace:on"),
        InlineKeyboardButton(text="🗑 Удаление", callback_data="m:replace:off")
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection"))
    return b.as_markup()


def warn_count_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="1", callback_data="s:w:1"),
        InlineKeyboardButton(text="2", callback_data="s:w:2"),
        InlineKeyboardButton(text="3", callback_data="s:w:3")
    )
    b.row(
        InlineKeyboardButton(text="5", callback_data="s:w:5"),
        InlineKeyboardButton(text="10", callback_data="s:w:10"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:settings")
    )
    return b.as_markup()


def night_mode_menu(settings: dict):
    b = InlineKeyboardBuilder()
    night = settings.get("night_mode", {})
    enabled = night.get("enabled", False)
    status = "✅ Вкл" if enabled else "❌ Выкл"
    b.row(InlineKeyboardButton(text=f"🌙 Ночной режим {status}", callback_data="nm:t"))
    b.row(
        InlineKeyboardButton(text=f"⏰ Начало: {night.get('start', 23)}:00", callback_data="nm:start"),
        InlineKeyboardButton(text=f"⏰ Конец: {night.get('end', 7)}:00", callback_data="nm:end")
    )
    action = {"mute": "🔇 Мут", "ban": "⛔ Бан", "warn": "⚠️ Пред."}.get(
        night.get("action", "mute"), "🔇 Мут"
    )
    b.row(InlineKeyboardButton(text=f"⚡ Действие: {action}", callback_data="nm:action"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admins"))
    return b.as_markup()


def greeting_menu(settings: dict):
    b = InlineKeyboardBuilder()
    greeting = settings.get("greeting", {})
    enabled = greeting.get("enabled", True)
    status = "✅ Вкл" if enabled else "❌ Выкл"
    b.row(
        InlineKeyboardButton(text=f"👋 Приветствие {status}", callback_data="g:t"),
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="g:edit")
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection"))
    return b.as_markup()


def farewell_menu(settings: dict):
    b = InlineKeyboardBuilder()
    farewell = settings.get("farewell", {})
    enabled = farewell.get("enabled", True)
    status = "✅ Вкл" if enabled else "❌ Выкл"
    b.row(
        InlineKeyboardButton(text=f"🚪 Прощание {status}", callback_data="f:t"),
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="f:edit")
    )
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection"))
    return b.as_markup()


def reports_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="reports:refresh"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:logs")
    )
    return b.as_markup()


def whitelist_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="wl:add"),
        InlineKeyboardButton(text="➖ Удалить пользователя", callback_data="wl:remove"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Список", callback_data="wl:list"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admins")
    )
    return b.as_markup()


def blacklist_menu():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Добавить слово", callback_data="bl:add_word"),
        InlineKeyboardButton(text="➖ Удалить слово", callback_data="bl:remove_word"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Слова", callback_data="bl:list_words"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admins")
    )
    return b.as_markup()


def daily_rules_menu(settings: dict):
    b = InlineKeyboardBuilder()
    rules = settings.get("daily_rules", {})
    enabled = rules.get("enabled", False)
    status = "✅ Вкл" if enabled else "❌ Выкл"
    b.row(
        InlineKeyboardButton(text=f"📋 Автопостинг {status}", callback_data="dr:t"),
        InlineKeyboardButton(text=f"⏰ Время: {rules.get('time', '09:00')}", callback_data="dr:time")
    )
    b.row(
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="dr:edit"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:admins")
    )
    return b.as_markup()


async def group_tools_menu(settings: dict, chat_id: int = 0):
    import aiosqlite
    from db import db

    b = InlineKeyboardBuilder()

    rules = settings.get("daily_rules", {})
    rules_status = "✅ Вкл" if rules.get("enabled") else "❌ Выкл"
    b.row(
        InlineKeyboardButton(
            text=f"📋 Правила (автопостинг) {rules_status}",
            callback_data="gt:rules_toggle"
        )
    )
    b.row(
        InlineKeyboardButton(text=f"⏰ Время: {rules.get('time', '09:00')}", callback_data="gt:rules_time"),
        InlineKeyboardButton(text="✏️ Текст правил", callback_data="gt:rules_edit")
    )

    join_leave = settings.get("show_join_leave", True)
    autokick = settings.get("autokick_on_exit", False)
    b.row(
        InlineKeyboardButton(text=f"🚪 Входы/Выходы {'✅' if join_leave else '❌'}", callback_data="gt:join_leave"),
        InlineKeyboardButton(text=f"👢 Автокик {'✅' if autokick else '❌'}", callback_data="gt:autokick")
    )

    silent_days = settings.get("autokick_silent_days")
    silent_label = f"{silent_days}д" if silent_days else "❌"
    autojoin = False
    if chat_id:
        try:
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT enabled FROM auto_join_requests WHERE chat_id = ?", (chat_id,)
                )
                row = await cursor.fetchone()
                autojoin = bool(row and row[0])
        except Exception:
            pass
    b.row(
        InlineKeyboardButton(text=f"👢 Молчуны {silent_label}", callback_data="gt:autokick_silent"),
        InlineKeyboardButton(text=f"📥 Автозаявки {'✅' if autojoin else '❌'}", callback_data="gt:autojoin")
    )

    channels = settings.get("block_channels", False)
    minreg = settings.get("min_account_age_days", 0)
    b.row(
        InlineKeyboardButton(text=f"📡 Каналы {'✅' if not channels else '❌'}", callback_data="gt:channels"),
        InlineKeyboardButton(text=f"📅 Минрег {minreg}дн", callback_data="gt:minreg")
    )

    b.row(
        InlineKeyboardButton(text="🔓 Открыть чат", callback_data="gt:chat_open"),
        InlineKeyboardButton(text="🔒 Закрыть чат", callback_data="gt:chat_close")
    )

    b.row(
        InlineKeyboardButton(text="❓ Команды", callback_data="gt:help"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    )
    return b.as_markup()


def aggression_menu(settings: dict):
    b = InlineKeyboardBuilder()
    levels = ["Мягкий", "Средний", "Строгий", "Параноик"]
    current = settings.get("aggression_level", 2)
    for i, name in enumerate(levels):
        emoji = "✅" if i == current else "➖"
        b.row(InlineKeyboardButton(text=f"{emoji} {name}", callback_data=f"aggression:set:{i}"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:settings"))
    return b.as_markup()


def captcha_correct_keyboard():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Я не робот", callback_data="captcha:verify"))
    return b.as_markup()


def bayes_threshold_menu():
    b = InlineKeyboardBuilder()
    for val in [0.5, 0.6, 0.7, 0.8, 0.9]:
        b.row(InlineKeyboardButton(text=f"{val:.0%}", callback_data=f"bayes:set_threshold:{val}"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:protection"))
    return b.as_markup()


def back_to_main():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu:main"))
    return b.as_markup()
