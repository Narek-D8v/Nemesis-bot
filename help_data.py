from telethon import events
from client import client
from core import state, db, owner_filter, respond
from config import logger
from rp_commands import get_all_categories, get_category_commands

CMD_DESCS = {
    'sleep':       {'desc': 'Включить автоответчик', 'syntax': '!sleep', 'example': '!sleep'},
    'wake':        {'desc': 'Выключить автоответчик', 'syntax': '!wake', 'example': '!wake'},
    'setreply':    {'desc': 'Установить текст ответа', 'syntax': '!setreply [@user|default] [текст]', 'example': '!setreply @username Привет'},
    'status':      {'desc': 'Полный статус бота', 'syntax': '!status', 'example': '!status'},
    'time':        {'desc': 'Текущее время и дата', 'syntax': '!time', 'example': '!time'},
    'ping':        {'desc': 'Проверить задержку', 'syntax': '!ping', 'example': '!ping'},
    'id':          {'desc': 'ID чата / пользователя', 'syntax': '!id', 'example': '!id'},
    'info':        {'desc': 'Информация о боте', 'syntax': '!info', 'example': '!info'},
    'restart':     {'desc': 'Перезапустить бота', 'syntax': '!restart', 'example': '!restart'},
    'ghost':       {'desc': 'Ghost-режим (автоудаление команд)', 'syntax': '!ghost', 'example': '!ghost'},
    'resetdata':   {'desc': 'Сбросить все данные ⚠️', 'syntax': '!resetdata', 'example': '!resetdata'},
    'cover':       {'desc': 'Игнор всех команд кроме !cover off', 'syntax': '!cover [on|off]', 'example': '!cover on'},
    'silent':      {'desc': 'Бот молчит в ЛС', 'syntax': '!silent [on|off]', 'example': '!silent on'},
    'shadow':      {'desc': 'Автоудаление ответов через N сек', 'syntax': '!shadow [сек]', 'example': '!shadow 10'},
    'lock':        {'desc': 'Отвечать только контактам', 'syntax': '!lock [on|off]', 'example': '!lock on'},
    'mute':        {'desc': 'Игнорировать все ЛС', 'syntax': '!mute [on|off]', 'example': '!mute on'},
    'typing':      {'desc': 'Показывать «печатает…» перед ответом', 'syntax': '!typing [on|off]', 'example': '!typing on'},
    'autodel':     {'desc': 'Автоудаление всех исходящих сообщений', 'syntax': '!autodel [on|off] [сек]', 'example': '!autodel on 10'},
    'delay':       {'desc': 'Задержка перед автоответом (симуляция человека)', 'syntax': '!delay [сек]', 'example': '!delay 3'},
    'readreceipt': {'desc': 'Отмечать ЛС прочитанными', 'syntax': '!readreceipt [on|off]', 'example': '!readreceipt off'},
    'status_reset':{'desc': 'Сбросить все стелс-режимы', 'syntax': '!status_reset', 'example': '!status_reset'},
    'me':           {'desc': 'Мой профиль', 'syntax': '!me', 'example': '!me'},
    'avatar':       {'desc': 'Получить аватарку', 'syntax': '!avatar', 'example': '!avatar'},
    'name':         {'desc': 'Сменить имя', 'syntax': '!name [имя]', 'example': '!name НовоеИмя'},
    'lastname':     {'desc': 'Сменить фамилию', 'syntax': '!lastname [фамилия]', 'example': '!lastname Иванов'},
    'bio':          {'desc': 'Обновить «о себе»', 'syntax': '!bio [текст]', 'example': '!bio Люблю котиков'},
    'whois':        {'desc': 'Информация о пользователе', 'syntax': '!whois @ник', 'example': '!whois @durov'},
    'username_check': {'desc': 'Проверить занятость username', 'syntax': '!username_check @ник', 'example': '!username_check @test'},
    'dice':         {'desc': 'Кинуть кубик', 'syntax': '!dice', 'example': '!dice'},
    'dart':         {'desc': 'Кинуть дротик', 'syntax': '!dart', 'example': '!dart'},
    'basket':       {'desc': 'Бросить мяч', 'syntax': '!basket', 'example': '!basket'},
    'football':     {'desc': 'Удар по мячу', 'syntax': '!football', 'example': '!football'},
    'bowling':      {'desc': 'Боулинг', 'syntax': '!bowling', 'example': '!bowling'},
    'casino':       {'desc': 'Игровой автомат', 'syntax': '!casino', 'example': '!casino'},
    'coin':         {'desc': 'Подбросить монетку', 'syntax': '!coin', 'example': '!coin'},
    'rand':         {'desc': 'Случайное число', 'syntax': '!rand [a] [b]', 'example': '!rand 1 100'},
    '8ball':        {'desc': 'Магический шар', 'syntax': '!8ball [вопрос]', 'example': '!8ball Сегодня будет удача?'},
    'rps':          {'desc': 'Камень-ножницы-бумага', 'syntax': '!rps [к/н/б]', 'example': '!rps камень'},
    'slot':         {'desc': 'Слот-машина', 'syntax': '!slot', 'example': '!slot'},
    'lucky':        {'desc': 'Индекс удачи', 'syntax': '!lucky', 'example': '!lucky'},
    'choose':       {'desc': 'Случайный выбор', 'syntax': '!choose [вар1, вар2]', 'example': '!choose пицца, суши'},
    'quiz':         {'desc': 'Викторина', 'syntax': '!quiz', 'example': '!quiz'},
    'ytshow':       {'desc': 'Скачать видео с YouTube', 'syntax': '!ytshow <URL> [качество]', 'example': '!ytshow https://youtu.be/... 720'},
    'dl':           {'desc': 'Скачать видео (YouTube / Instagram / TikTok)', 'syntax': '!dl <URL>', 'example': '!dl https://www.tiktok.com/@user/video/...'},
    'playlist':     {'desc': 'Скачать плейлист YouTube', 'syntax': '!playlist <URL> [кол-во] | [start-end]', 'example': '!playlist https://youtube.com/playlist?list=... 5'},
    'audio':        {'desc': 'Скачать аудио с YouTube', 'syntax': '!audio <URL>', 'example': '!audio https://youtu.be/...'},
    'sub':          {'desc': 'Скачать субтитры с YouTube', 'syntax': '!sub <URL> [язык]', 'example': '!sub https://youtu.be/... ru'},
    'calc':         {'desc': 'Калькулятор', 'syntax': '!calc [выражение]', 'example': '!calc 2+2*2'},
    'remind':       {'desc': 'Напоминание', 'syntax': '!remind [сек] [текст]', 'example': '!remind 60 Поставить чайник'},
    'search':       {'desc': 'Поиск в Wikipedia', 'syntax': '!search [запрос]', 'example': '!search Python'},
    'shorten':      {'desc': 'Сократить ссылку', 'syntax': '!shorten [url]', 'example': '!shorten https://example.com'},
    'weather':      {'desc': 'Текущая погода в городе', 'syntax': '!weather [город]', 'example': '!weather Moscow'},
    'translate':    {'desc': 'Переводчик (Google)', 'syntax': '!translate [код_языка] [текст]', 'example': '!translate en Привет'},
    'base64':       {'desc': 'Base64 кодирование/декодирование', 'syntax': '!base64 encode|decode [текст]', 'example': '!base64 encode Привет'},
    'hash':         {'desc': 'Хэши (MD5/SHA)', 'syntax': '!hash [текст]', 'example': '!hash password'},
    'morse':        {'desc': 'Азбука Морзе', 'syntax': '!morse [текст]', 'example': '!morse SOS'},
    'caesar':       {'desc': 'Шифр Цезаря', 'syntax': '!caesar encode|decode [сдвиг] [текст]', 'example': '!caesar encode 3 Привет'},
    'vigenere':     {'desc': 'Шифр Виженера', 'syntax': '!vigenere encode|decode [ключ] [текст]', 'example': '!vigenere encode key Привет'},
    'password':     {'desc': 'Генератор паролей', 'syntax': '!password [длина] [simple]', 'example': '!password 20'},
    'qr':           {'desc': 'Сгенерировать QR-код', 'syntax': '!qr [текст]', 'example': '!qr https://example.com'},
    'uuid':         {'desc': 'Генератор UUID', 'syntax': '!uuid', 'example': '!uuid'},
    'color':        {'desc': 'Образец цвета + Hex/RGB', 'syntax': '!color [#HEX или R,G,B]', 'example': '!color #FF0000'},
    'ascii':        {'desc': 'ASCII коды символов', 'syntax': '!ascii [текст]', 'example': '!ascii Hello'},
    'type':         {'desc': 'Печать текста с эффектом', 'syntax': '!type [fast|slow|matrix|glitch] [текст]', 'example': '!type slow Привет'},
    'echo':         {'desc': 'Отправить сообщение', 'syntax': '!echo [текст]', 'example': '!echo Тест'},
    'bold':         {'desc': 'Жирный текст', 'syntax': '!bold [текст]', 'example': '!bold Важно'},
    'italic':       {'desc': 'Курсивный текст', 'syntax': '!italic [текст]', 'example': '!italic Цитата'},
    'mono':         {'desc': 'Моноширинный текст', 'syntax': '!mono [текст]', 'example': '!mono code'},
    'clean':        {'desc': 'Удалить свои N сообщений', 'syntax': '!clean [n]', 'example': '!clean 5'},
    'purge':        {'desc': 'Удалить любые N сообщений', 'syntax': '!purge [n]', 'example': '!purge 10'},
    'spam':         {'desc': 'Спам N сообщений', 'syntax': '!spam [n] [текст]', 'example': '!spam 5 Привет'},
    'forward':      {'desc': 'Переслать сообщение в чат', 'syntax': '!forward [chat_id]', 'example': '!forward -100123456789'},
    'pin':          {'desc': 'Закрепить сообщение', 'syntax': '!pin', 'example': '!pin'},
    'unpin':        {'desc': 'Открепить сообщение', 'syntax': '!unpin', 'example': '!unpin'},
    'copyall':      {'desc': 'Копировать N сообщений в чат', 'syntax': '!copyall [n] [chat_id]', 'example': '!copyall 50 -100123456789'},
    'react':        {'desc': 'Поставить реакцию', 'syntax': '!react [эмодзи]', 'example': '!react 👍'},
    'save':         {'desc': 'Сохранить значение по ключу / сохранить медиа', 'syntax': '!save <ключ> <значение> | !save (в ответ на медиа)', 'example': '!save пароль 12345'},
    'get':          {'desc': 'Получить значение по ключу', 'syntax': '!get <ключ>', 'example': '!get пароль'},
    'del':          {'desc': 'Удалить значение по ключу', 'syntax': '!del <ключ>', 'example': '!del пароль'},
    'list':         {'desc': 'Список всех сохранённых данных', 'syntax': '!list', 'example': '!list'},
    'find':         {'desc': 'Поиск по сохранённым данным и заметкам', 'syntax': '!find <слово>', 'example': '!find пароль'},
    'note':         {'desc': 'Сохранить заметку', 'syntax': '!note <название> <текст>', 'example': '!note Идея Купить молоко'},
    'getnote':      {'desc': 'Получить заметку', 'syntax': '!getnote <название>', 'example': '!getnote Идея'},
    'delnote':      {'desc': 'Удалить заметку', 'syntax': '!delnote <название>', 'example': '!delnote Идея'},
    'notes':        {'desc': 'Список всех заметок', 'syntax': '!notes', 'example': '!notes'},
    'todo':         {'desc': 'Добавить задачу', 'syntax': '!todo <текст>', 'example': '!todo Купить молоко'},
    'todos':        {'desc': 'Список всех задач', 'syntax': '!todos', 'example': '!todos'},
    'done':         {'desc': 'Отметить задачу выполненной', 'syntax': '!done <номер>', 'example': '!done 1'},
    'undone':       {'desc': 'Снять отметку выполнения', 'syntax': '!undone <номер>', 'example': '!undone 1'},
    'deltodo':      {'desc': 'Удалить задачу', 'syntax': '!deltodo <номер>', 'example': '!deltodo 1'},
    'afk':          {'desc': 'Включить AFK-режим', 'syntax': '!afk [причина]', 'example': '!afk Сплю'},
    'unafk':        {'desc': 'Выключить AFK-режим', 'syntax': '!unafk', 'example': '!unafk'},
    'chatinfo':     {'desc': 'Информация о чате', 'syntax': '!chatinfo', 'example': '!chatinfo'},
    'members':      {'desc': 'Количество участников', 'syntax': '!members', 'example': '!members'},
    'admins':       {'desc': 'Список администраторов', 'syntax': '!admins', 'example': '!admins'},
    'top':          {'desc': 'Топ активных пользователей', 'syntax': '!top [n]', 'example': '!top 100'},
    'bots':         {'desc': 'Список ботов в чате', 'syntax': '!bots', 'example': '!bots'},
    'sudo':         {'desc': 'Управление sudo-пользователями', 'syntax': '!sudo [on|off] @user', 'example': '!sudo on @durov'},
    'watch':        {'desc': 'Мониторинг новых сессий', 'syntax': '!watch [on|off]', 'example': '!watch on'},
    'check_email':  {'desc': 'Проверить email на утечки', 'syntax': '!check_email <email>', 'example': '!check_email test@example.com'},
    'protect':      {'desc': 'Защита от удаления чатов', 'syntax': '!protect [on|off]', 'example': '!protect on'},
    'rphelp':       {'desc': 'Список RP-команд', 'syntax': '!rphelp', 'example': '!rphelp'},
    'trhelp':       {'desc': 'Список кодов языков для !translate', 'syntax': '!trhelp', 'example': '!trhelp'},
}

COMMANDS_LIST = {
    'основные': [
        '!sleep', '!wake', '!setreply', '!status', '!time', '!ping',
        '!id', '!info', '!restart', '!ghost', '!resetdata'
    ],
    'стелс': [
        '!cover', '!silent', '!shadow', '!lock', '!mute',
        '!typing', '!autodel', '!delay', '!readreceipt', '!status_reset'
    ],
    'профиль': [
        '!me', '!avatar', '!name', '!lastname', '!bio', '!whois', '!username_check'
    ],
    'игры': [
        '!dice', '!dart', '!basket', '!football', '!bowling', '!casino',
        '!coin', '!rand', '!8ball', '!rps', '!slot', '!lucky', '!choose', '!quiz'
    ],
    'youtube': [
        '!ytshow', '!dl', '!playlist', '!audio', '!sub'
    ],
    'утилиты': [
        '!calc', '!remind', '!search', '!shorten', '!weather', '!translate', '!trhelp',
        '!base64', '!hash', '!morse', '!caesar', '!vigenere', '!password',
        '!qr', '!uuid', '!color', '!ascii'
    ],
    'сообщения': [
        '!type', '!echo', '!bold', '!italic', '!mono',
        '!clean', '!purge', '!spam', '!forward', '!pin', '!unpin',
        '!copyall', '!react'
    ],
    'заметки': [
        '!save', '!get', '!del', '!list', '!find',
        '!note', '!getnote', '!delnote', '!notes',
        '!todo', '!todos', '!done', '!undone', '!deltodo'
    ],
    'безопасность': [
        '!sudo', '!watch', '!check_email', '!protect'
    ],
    'afk': ['!afk', '!unafk'],
    'инфо': ['!chatinfo', '!members', '!admins', '!top', '!bots'],
    'rp': ['!rphelp'],
}

EMOJI_MAP = {
    'основные': '⚙️', 'стелс': '🛡️', 'профиль': '👤', 'игры': '🎮',
    'youtube': '🎬', 'утилиты': '🛠', 'сообщения': '✉️', 'заметки': '📦',
    'безопасность': '🔐', 'afk': '😴', 'инфо': '📊', 'rp': '🎭',
}

HELP_CATS = {
    'основные': (
        "⚙️ **ОСНОВНЫЕ КОМАНДЫ**\n\n"
        "`!sleep` — включить автоответчик\n"
        "`!wake` — выключить автоответчик\n"
        "`!setreply [@user | default] [текст]` — текст ответа\n"
        "`!status` — полный статус бота\n"
        "`!time` — время и дата\n"
        "`!ping` — задержка соединения\n"
        "`!id` — ID чата / пользователя\n"
        "`!info` — информация о боте\n"
        "`!restart` — перезапуск\n"
        "`!ghost` — ghost-режим\n"
        "`!resetdata` — сброс всех данных ⚠️"
    ),
    'стелс': (
        "🛡️ **СТЕЛС-РЕЖИМЫ**\n\n"
        "`!cover [on|off]` — игнор всех команд\n"
        "`!silent [on|off]` — бот молчит в ЛС\n"
        "`!shadow [сек]` — автоудаление ответов\n"
        "`!lock [on|off]` — только контактам\n"
        "`!mute [on|off]` — игнор всех ЛС\n"
        "`!typing [on|off]` — показывать «печатает…»\n"
        "`!autodel [on|off] [сек]` — автовудаление исходящих\n"
        "`!delay [сек]` — задержка перед автоответом\n"
        "`!readreceipt [on|off]` — отмечать прочитанным\n"
        "`!status_reset` — сброс всех стелс-режимов"
    ),
    'профиль': (
        "👤 **ПРОФИЛЬ**\n\n"
        "`!me` — свой профиль\n"
        "`!avatar` — своя/чужая аватарка\n"
        "`!name [имя]` — сменить имя\n"
        "`!lastname [фамилия]` — сменить фамилию\n"
        "`!bio [текст]` — обновить «о себе»\n"
        "`!whois @ник` — инфо о пользователе\n"
        "`!username_check @ник` — проверить username"
    ),
    'игры': (
        "🎮 **ИГРЫ И РАЗВЛЕЧЕНИЯ**\n\n"
        "`!dice` `!dart` `!basket` `!football` `!bowling` `!casino` — анимации TG\n"
        "`!coin` — монетка\n"
        "`!rand` — случайное число\n"
        "`!8ball [вопрос]` — магический шар\n"
        "`!rps [к/н/б]` — камень-ножницы-бумага\n"
        "`!slot` — слот-машина\n"
        "`!lucky` — индекс удачи\n"
        "`!choose [вар1 | вар2]` — случайный выбор\n"
        "`!quiz` — викторина"
    ),
    'youtube': (
        "🎬 **ЗАГРУЗКА МЕДИА**\n\n"
        "`!ytshow <URL> [качество]` — скачать видео с YouTube\n"
        "`!dl <URL>` — скачать видео (YouTube / Instagram / TikTok)\n"
        "`!playlist <URL> [кол-во | start-end]` — загрузка плейлиста YouTube\n"
        "`!audio <URL>` — скачать аудио с YouTube\n"
        "`!sub <URL> [ru|en]` — скачать субтитры с YouTube\n\n"
        "💡 Таймаут — 10 мин."
    ),
    'утилиты': (
        "🛠 **УТИЛИТЫ**\n\n"
        "`!calc [выражение]` — калькулятор\n"
        "`!remind [сек] [текст]` — напоминание\n"
        "`!search [запрос]` — поиск в Wikipedia\n"
        "`!shorten [url]` — сократить ссылку\n"
        "`!weather [город]` — погода\n"
        "`!translate [код_языка] [текст]` — перевод (по умолч. ru)\n"
        "`!trhelp` — список кодов языков\n"
        "`!base64 encode/decode [текст]`\n"
        "`!hash [текст]` — MD5/SHA хэши\n"
        "`!morse [текст]` — азбука Морзе\n"
        "`!caesar encode/decode [сдвиг] [текст]`\n"
        "`!vigenere encode/decode [ключ] [текст]`\n"
        "`!password [длина] [simple]`\n"
        "`!qr [текст]` — генерация QR-кода\n"
        "`!uuid` — UUID v4\n"
        "`!color [#HEX или R,G,B]` — образец цвета\n"
        "`!ascii [текст]`"
    ),
    'сообщения': (
        "✉️ **СООБЩЕНИЯ**\n\n"
        "`!type [fast/slow/matrix/glitch] [текст]`\n"
        "`!echo [текст]`\n"
        "`!bold` `!italic` `!mono` [текст]\n"
        "`!clean [n]` — удалить свои N сообщений\n"
        "`!purge [n]` — удалить любые N сообщений\n"
        "`!spam [n] [текст]`\n"
        "`!forward [chat_id]`\n"
        "`!pin` / `!unpin`\n"
        "`!copyall [n] [chat_id]`\n"
        "`!react [эмодзи]`\n\n"
        "📎 **Сохранение медиа:** ответьте на фото/видео → `!save`"
    ),
    'заметки': (
        "📦 **ЗАМЕТКИ И TODO**\n\n"
        "**Хранилище:** `!save key val` `!get` `!del` `!list` `!find`\n"
        "**Медиа:** ответ на фото/видео → `!save`\n"
        "**Заметки:** `!note` `!getnote` `!delnote` `!notes`\n"
        "**TODO:** `!todo` `!todos` `!done` `!undone` `!deltodo`"
    ),
    'безопасность': (
        "🔐 **БЕЗОПАСНОСТЬ**\n\n"
        "`!sudo [on|off] @user` — управление sudo-доступом\n"
        "`!watch [on|off]` — мониторинг новых сессий\n"
        "`!check_email <email>` — проверка email на утечки\n"
        "`!protect [on|off]` — защита от удаления чатов"
    ),
    'afk': (
        "😴 **AFK**\n\n"
        "`!afk [причина]` — включить AFK-режим\n"
        "`!unafk` — выключить с отчётом времени"
    ),
    'инфо': (
        "📊 **ИНФОРМАЦИЯ О ЧАТЕ**\n\n"
        "`!chatinfo` — информация о чате\n"
        "`!members` — количество участников\n"
        "`!admins` — список администраторов\n"
        "`!top [n]` — топ активных\n"
        "`!bots` — список ботов"
    ),
    'rp': (
        "🎭 **RP-КОМАНДЫ (ролевые)**\n\n"
        "Напишите в ответ (reply) одно слово — бот отправит действие.\n"
        "Через Enter можно добавить свою реплику.\n\n"
        "**Список команд:** `!rphelp`\n\n"
        "**Пример:** ответьте `обнять` + Enter + `Ты моя сладкая`\n"
        "→ отправит `🤗 ...обнял... Ты моя сладкая`\n\n"
        "**Категории:**\n" + '\n'.join(
            f'• {cat.capitalize()}: {", ".join(get_category_commands(cat))}'
            for cat in get_all_categories()
        )
    ),
}


@client.on(events.NewMessage(pattern=r'!help(?:\s+(.+))?$', func=owner_filter))
async def help_cmd(e):
    arg = (e.pattern_match.group(1) or '').strip().lower()

    if arg.startswith('cmd '):
        cmd_name = arg[4:].strip().lstrip('!')
        if cmd_name in CMD_DESCS:
            d = CMD_DESCS[cmd_name]
            lines = [
                f"📖 **Команда:** `!{cmd_name}`",
                f"**Описание:** {d['desc']}",
                f"**Синтаксис:** `{d['syntax']}`",
                f"**Пример:** `{d['example']}`",
            ]
            lines.append("\n💡 Для справки по команде: `!help cmd <команда>`")
            lines.append("💡 Для всех команд: `!help all`")
            await respond(e, "\n".join(lines))
            db.bump_stat('cmds')
            return
        else:
            await respond(e, f"❌ Команда `{cmd_name}` не найдена.\n💡 `!help cmd <команда>`")
            db.bump_stat('cmds')
            return

    if arg == 'all':
        msg = "📋 **Все команды:**\n"
        for cat, cmds in COMMANDS_LIST.items():
            emoji = EMOJI_MAP.get(cat, '•')
            cmds_str = ", ".join(f"`{cmd}`" for cmd in cmds)
            msg += f"\n{emoji} **{cat.capitalize()}:** {cmds_str}\n"
        msg += "\n💡 Для справки по команде: `!help cmd <команда>`\n💡 Для всех категорий: `!help <категория>`"
        if len(msg) > 4096:
            msg = msg[:4080] + "\n\n⚠️ Сообщение обрезано (лимит 4096)"
        await respond(e, msg)
        db.bump_stat('cmds')
        return

    if arg:
        cat = arg
        if cat not in HELP_CATS:
            cats = ', '.join(f"`!help {c}`" for c in HELP_CATS)
            await respond(e, f"❌ Категория `{cat}` не найдена.\n\nДоступные категории:\n{cats}")
            db.bump_stat('cmds')
            return
        text = HELP_CATS[cat]
        cmds = COMMANDS_LIST.get(cat, [])
        if cmds:
            text += "\n\n📋 **Команды для копирования:**\n" + ", ".join(f"`{cmd}`" for cmd in cmds)
        text += "\n\n💡 Для справки по команде: `!help cmd <команда>`\n💡 Для всех команд: `!help all`"
        await respond(e, text)
        db.bump_stat('cmds')
        return

    lines = ["📚 **UserBot Help**\n\nВыбери категорию — скопируй команду и отправь:\n"]
    for cat_name in HELP_CATS:
        emoji = EMOJI_MAP.get(cat_name, '•')
        lines.append(f"{emoji} `{cat_name.capitalize()}` → `!help {cat_name}`")
    lines.append("\n💡 Для справки по команде: `!help cmd <команда>`")
    lines.append("💡 Для всех команд: `!help all`")
    await respond(e, "\n".join(lines))
    db.bump_stat('cmds')

@client.on(events.NewMessage(pattern=r'!trhelp$', func=owner_filter))
async def trhelp_cmd(e):
    codes = sorted(LANG_CODES)
    chunk_size = 25
    chunks = [codes[i:i+chunk_size] for i in range(0, len(codes), chunk_size)]
    for i, chunk in enumerate(chunks):
        lines = [f"`{c}` — {LANG_CODES[c]}" for c in chunk]
        if i == 0:
            lines.insert(0, "🌐 **Коды языков Google Translate**\n")
            lines.append("\n💡 Использование: `!translate <код> [текст]`")
            await respond(e, "\n".join(lines))
        else:
            await e.reply("\n".join(lines))

LANG_CODES = {
    'af': '🇿🇦 Африкаанс', 'sq': '🇦🇱 Албанский', 'am': '🇪🇹 Амхарский', 'ar': '🇸🇦 Арабский',
    'hy': '🇦🇲 Армянский', 'az': '🇦🇿 Азербайджанский', 'eu': '🇪🇸 Баскский', 'be': '🇧🇾 Белорусский',
    'bn': '🇧🇩 Бенгальский', 'bs': '🇧🇦 Боснийский', 'bg': '🇧🇬 Болгарский', 'ca': '🇪🇸 Каталанский',
    'ceb': '🇵🇭 Себуанский', 'ny': '🇲🇼 Чичева', 'zh': '🇨🇳 Китайский', 'co': '🇫🇷 Корсиканский',
    'hr': '🇭🇷 Хорватский', 'cs': '🇨🇿 Чешский', 'da': '🇩🇰 Датский', 'nl': '🇳🇱 Нидерландский',
    'en': '🇬🇧 Английский', 'eo': '🌍 Эсперанто', 'et': '🇪🇪 Эстонский', 'tl': '🇵🇭 Филиппинский',
    'fi': '🇫🇮 Финский', 'fr': '🇫🇷 Французский', 'fy': '🇳🇱 Фризский', 'gl': '🇪🇸 Галисийский',
    'ka': '🇬🇪 Грузинский', 'de': '🇩🇪 Немецкий', 'el': '🇬🇷 Греческий', 'gu': '🇮🇳 Гуджарати',
    'ht': '🇭🇹 Гаитянский', 'ha': '🇳🇬 Хауса', 'haw': '🌺 Гавайский', 'he': '🇮🇱 Иврит',
    'hi': '🇮🇳 Хинди', 'hmn': '🇨🇳 Хмонг', 'hu': '🇭🇺 Венгерский', 'is': '🇮🇸 Исландский',
    'ig': '🇳🇬 Игбо', 'id': '🇮🇩 Индонезийский', 'ga': '🇮🇪 Ирландский', 'it': '🇮🇹 Итальянский',
    'ja': '🇯🇵 Японский', 'jv': '🇮🇩 Яванский', 'kn': '🇮🇳 Каннада', 'kk': '🇰🇿 Казахский',
    'km': '🇰🇭 Кхмерский', 'rw': '🇷🇦 Киньяруанда', 'ko': '🇰🇷 Корейский', 'ku': '🇮🇶 Курдский',
    'ky': '🇰🇬 Кыргызский', 'lo': '🇱🇦 Лаосский', 'la': '🏛 Латынь', 'lv': '🇱🇻 Латышский',
    'lt': '🇱🇹 Литовский', 'lb': '🇱🇺 Люксембургский', 'mk': '🇲🇰 Македонский', 'mg': '🇲🇬 Малагасийский',
    'ms': '🇲🇾 Малайский', 'ml': '🇮🇳 Малаялам', 'mt': '🇲🇹 Мальтийский', 'mi': '🇳🇿 Маори',
    'mr': '🇮🇳 Маратхи', 'mn': '🇲🇳 Монгольский', 'my': '🇲🇲 Мьянманский', 'ne': '🇳🇵 Непальский',
    'no': '🇳🇴 Норвежский', 'or': '🇮🇳 Ория', 'ps': '🇦🇫 Пушту', 'fa': '🇮🇷 Персидский',
    'pl': '🇵🇱 Польский', 'pt': '🇵🇹 Португальский', 'pa': '🇮🇳 Панджаби', 'ro': '🇷🇴 Румынский',
    'ru': '🇷🇺 Русский', 'sm': '🇼🇸 Самоанский', 'gd': '🏴 Шотландский', 'sr': '🇷🇸 Сербский',
    'st': '🇱🇸 Сесото', 'sn': '🇿🇼 Шона', 'sd': '🇵🇰 Синдхи', 'si': '🇱🇰 Сингальский',
    'sk': '🇸🇰 Словацкий', 'sl': '🇸🇮 Словенский', 'so': '🇸🇴 Сомалийский', 'es': '🇪🇸 Испанский',
    'su': '🇮🇩 Сунданский', 'sw': '🇹🇿 Суахили', 'sv': '🇸🇪 Шведский', 'tg': '🇹🇯 Таджикский',
    'ta': '🇮🇳 Тамильский', 'tt': '🇷🇺 Татарский', 'te': '🇮🇳 Телугу', 'th': '🇹🇭 Тайский',
    'tr': '🇹🇷 Турецкий', 'tk': '🇹🇲 Туркменский', 'uk': '🇺🇦 Украинский', 'ur': '🇵🇰 Урду',
    'ug': '🇨🇳 Уйгурский', 'uz': '🇺🇿 Узбекский', 'vi': '🇻🇳 Вьетнамский', 'cy': '🏴 Валлийский',
    'xh': '🇿🇦 Коса', 'yi': '🇮🇱 Идиш', 'yo': '🇳🇬 Йоруба', 'zu': '🇿🇦 Зулусский',
}
