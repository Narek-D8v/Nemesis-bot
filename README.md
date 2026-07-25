# 🤖 Немуся (Nemesis) — Telegram Moderation Bot

**Немуся** — мощный многофункциональный модератор для Telegram групп с системой рангов, байесовским антиспамом, VirusTotal, премиум-подпиской и **плагинной архитектурой**.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/aiogram-3.x-blue?logo=telegram" alt="aiogram">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Технологии](#-технологии)
- [Архитектура](#-архитектура)
- [Установка](#-установка)
- [Команды](#-команды)
- [Плагины](#-плагины)
- [Лицензия](#-лицензия)

---

## 🚀 Возможности

| Категория | Описание |
|-----------|----------|
| **Модерация** | Система рангов (0–5), варны, муты, баны, кики, наследство, завещания |
| **Антиспам** | Байесовский самообучающийся фильтр, капча (кнопка/математика), антифлуд |
| **Безопасность** | VirusTotal (ссылки + файлы), чёрный список слов, блокировка инвайтов |
| **Автоматизация** | Автопостинг правил (с таймзоной), ночной режим, автоочистка логов |
| **Фильтры** | Мат-фильтр (замена/удаление), блокировка повторов, масок, @all, пересланных сообщений |
| **Премиум** | Личный (10⭐) и групповой (5⭐) через Telegram Stars |
| **Аналитика** | Статистика, топ нарушителей, экспорт логов в CSV, расширенная статистика |
| **Плагины** | Модульная архитектура — легко добавлять новые функции (РП, игры и т.д.) |

---

## 🛠 Технологии

- **Python 3.11+**
- **aiogram 3.x** — асинхронный Telegram Bot API
- **SQLite (aiosqlite)** — встроенная БД без настройки
- **vt-py** — VirusTotal API
- **Байесовский классификатор** — собственная реализация с поддержкой эмодзи
- **Telegram Stars API** — платежи
- **zoneinfo** — часовые пояса (без pytz)
- **Plugin System** — динамическая загрузка модулей

---

## 🏗 Архитектура

```
nemesis-bot/
├── core/                          # Ядро
│   ├── __init__.py
│   └── plugin_manager.py          # BasePlugin, PluginManager
├── plugins/                       # Плагины
│   ├── __init__.py
│   └── example/                   # Example plugin
│       ├── __init__.py
│       ├── plugin.py
│       └── handlers.py
├── handlers/                      # Легаси-обработчики
│   ├── admin.py                   #   Админ-команды
│   ├── messages.py                #   Обработка сообщений
│   ├── callbacks.py               #   Inline-кнопки
│   └── ...
├── utils/                         # Утилиты
│   ├── __init__.py                #   Фильтры, форматирование
│   ├── virustotal.py              #   VirusTotal API
│   ├── mentions.py                #   Извлечение пользователей
│   └── time_parser.py             #   Парсер времени
├── middlewares.py                 # Global middleware
├── bot.py                         # Bot + Dispatcher
├── db.py                          # Database layer
├── config.py                      # Env config
├── config.yaml                    # Plugin config
├── main.py                        # Entry point
└── README_PLUGINS.md              # Plugin development guide
```

---

## 📦 Установка

```bash
# 1. Клонировать
git clone https://github.com/Narek-D8v/Nemesis-bot.git
cd Nemesis-bot

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Настроить .env
cp .env.example .env
# Отредактировать .env:
#   BOT_TOKEN=...
#   ADMIN_ID=...
#   VIRUSTOTAL_API_KEY=...

# 4. Запустить
python main.py
```

### Переменные окружения (.env)

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `BOT_TOKEN` | ✅ | Токен от @BotFather |
| `ADMIN_ID` | ✅ | Telegram ID владельца |
| `VIRUSTOTAL_API_KEY` | ❌ | API ключ VirusTotal |
| `PORT` | ❌ | Порт для health check (по умолч. 8080) |

---

## 📟 Команды

### Для @BotFather

```
start - Открыть главное меню
help - Показать справку
report - Отправить жалобу (ответом)
clear - Очистить сообщения
markspam - Отметить как спам
markham - Отметить как хорошее
commands - Документация команд
warn - Предупреждение
mute - Заглушить
ban - Забанить
kick - Исключить
unban - Разбанить
unmute - Снять мут
staff - Список модераторов
warns - Предупреждения
scan - Проверить ссылку/файл
export - Экспорт статистики (CSV)
```

### Полная документация

👉 **[Открыть документацию команд](https://narek-d8v.github.io/Nemesis-bot-documentation/)**

---

## 🔌 Плагины

Бот поддерживает **динамическую загрузку плагинов**. Каждый плагин — отдельная папка в `plugins/` со своим `plugin.py`.

### Создание плагина в 3 шага

```python
# plugins/myplugin/plugin.py
from core.plugin_manager import BasePlugin

class MyPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        from .handlers import setup_handlers
        setup_handlers(self.router)

    async def on_unload(self):
        pass

    async def my_api(self):
        return "API method"
```

```python
# plugins/myplugin/handlers.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

def setup_handlers(router: Router):
    @router.message(Command("mycmd"))
    async def handler(message: Message):
        await message.reply("Hello from plugin!")
```

```yaml
# config.yaml
plugins:
  myplugin:
    enabled: true
    version: 1.0.0
```

Подробнее: [`README_PLUGINS.md`](README_PLUGINS.md)

---

## 🎯 Ключевые особенности

| Фича | Статус |
|------|--------|
| ✅ Система рангов (0–5) | Реализована |
| ✅ Байесовский антиспам | Реализован |
| ✅ VirusTotal (ссылки + файлы) | Реализован |
| ✅ Часовые пояса (zoneinfo) | Реализованы |
| ✅ Капча (кнопка/математика) | Реализована |
| ✅ Ночной режим | Реализован |
| ✅ Автопостинг правил | Реализован |
| ✅ Триггеры (автонаказания) | Реализованы |
| ✅ Премиум (Telegram Stars) | Реализован |
| ✅ Плагинная архитектура | Реализована |
| ✅ Экспорт статистики (CSV) | Реализован |
| ✅ Модераторские логи | Реализованы |
| ✅ Наследство / завещания | Реализованы |

---

## 🤝 Лицензия

**MIT** — свободное использование, модификация и распространение.

## 👤 Автор

Разработано [**Narek-D8v**](https://github.com/Narek-D8v)

---

<p align="center">
  <b>Если бот полезен — поставьте ⭐ на GitHub!</b>
</p>
