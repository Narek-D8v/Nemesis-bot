# Plugin System for Nemesis Bot

## Структура

```
nemesis-bot/
├── core/
│   ├── __init__.py
│   └── plugin_manager.py      # BasePlugin, PluginConfig, PluginManager
├── plugins/
│   ├── __init__.py
│   ├── example/               # Example plugin
│   │   ├── __init__.py
│   │   ├── plugin.py          # Main plugin class
│   │   ├── handlers.py        # Message handlers
│   │   └── config.py          # Default settings
│   └── ... (other plugins)
├── config.yaml                # Plugin configuration
└── main.py                    # Entry point
```

## Как создать новый плагин

### 1. Создать структуру

```bash
mkdir -p plugins/myplugin
touch plugins/myplugin/__init__.py
touch plugins/myplugin/plugin.py
touch plugins/myplugin/handlers.py
```

### 2. Создать класс плагина (`plugin.py`)

```python
import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger(__name__)

class MyPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        logger.info("MyPlugin loaded")
        from .handlers import setup_handlers
        setup_handlers(self.router)

    async def on_unload(self):
        logger.info("MyPlugin unloaded")

    # API for other plugins
    async def my_method(self):
        return "Hello from MyPlugin"
```

### 3. Создать обработчики (`handlers.py`)

```python
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

def setup_handlers(router: Router):

    @router.message(Command("mycmd"))
    async def cmd_mycmd(message: Message):
        await message.reply("This is my plugin command!")
```

### 4. Добавить конфиг (`config.yaml`)

```yaml
plugins:
  myplugin:
    enabled: true
    version: 1.0.0
    settings:
      my_setting: value
```

## Взаимодействие между плагинами

```python
from core.plugin_manager import PluginManager

async def some_function(plugin_manager: PluginManager):
    other = plugin_manager.get_plugin("other_plugin_name")
    if other and hasattr(other, "some_method"):
        result = await other.some_method()
```

## API для других модулей

Через `plugin_manager.get_plugin("name")` можно получить любой зарегистрированный плагин и вызывать его методы.

```python
# main.py
pm = PluginManager(dp)
await pm.load_config()
pm._discover_and_register()

plugin = pm.get_plugin("example")
if plugin:
    await plugin.greet_user(user_id, name)
```
