import abc
import logging
from typing import Any, Optional, Dict, List, Type
from aiogram import Router, Dispatcher

logger = logging.getLogger(__name__)


class PluginConfig:
    def __init__(self, name: str, version: str, enabled: bool = True):
        self.name = name
        self.version = version
        self.enabled = enabled
        self.settings: Dict[str, Any] = {}

    def load_from_dict(self, data: Dict[str, Any]):
        if not data:
            return
        self.settings = data.get("settings", {})
        self.enabled = data.get("enabled", True)


class BasePlugin(abc.ABC):
    VERSION = "1.0.0"
    REQUIRED_PERMISSIONS: List[str] = []

    def __init__(self, config: PluginConfig):
        self.config = config
        self.router = Router()
        self.logger = logging.getLogger(f"plugin.{config.name}")
        self._middlewares: List = []
        self._background_tasks: List = []
        self._granted_permissions: List[str] = []

    @abc.abstractmethod
    async def on_load(self):
        pass

    @abc.abstractmethod
    async def on_unload(self):
        pass

    async def register_handlers(self, dp: Dispatcher):
        if self.config.enabled:
            dp.include_router(self.router)
            self.logger.info(f"Handlers registered for '{self.config.name}'")

    def add_middleware(self, middleware):
        self._middlewares.append(middleware)

    def add_background_task(self, coro):
        self._background_tasks.append(coro)

    async def get_setting(self, key: str, default: Any = None) -> Any:
        return self.config.settings.get(key, default)

    async def set_setting(self, key: str, value: Any):
        self.config.settings[key] = value

    def get_name(self) -> str:
        return self.config.name

    def get_version(self) -> str:
        return self.config.version

    def is_enabled(self) -> bool:
        return self.config.enabled


class PluginManager:
    def __init__(self, dp: Dispatcher, config_path: str = "config.yaml"):
        self.dp = dp
        self.config_path = config_path
        self.plugins: Dict[str, BasePlugin] = {}
        self._config: Dict[str, Any] = {}

    async def load_config(self):
        import yaml
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"Plugin config loaded from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Config not found: {self.config_path}")
            self._config = {}

    async def register_plugin(self, plugin_class: Type[BasePlugin]):
        plugin_name = plugin_class.__name__.replace("Plugin", "").lower()
        plugin_config_data = self._config.get("plugins", {}).get(plugin_name, {})

        config = PluginConfig(
            name=plugin_name,
            version=getattr(plugin_class, 'VERSION', "1.0.0"),
            enabled=plugin_config_data.get("enabled", True),
        )
        config.load_from_dict(plugin_config_data)

        plugin = plugin_class(config)

        try:
            missing = set(plugin_class.REQUIRED_PERMISSIONS) - set(plugin._granted_permissions)
            if missing:
                plugin.logger.warning(f"Missing permissions: {missing}")
                if not plugin.is_enabled():
                    plugin.logger.warning(f"Plugin '{plugin_name}' disabled due to missing permissions")
                    self.plugins[plugin_name] = plugin
                    return

            await plugin.on_load()
            await plugin.register_handlers(self.dp)

            for middleware in plugin._middlewares:
                self.dp.message.middleware(middleware)

            for task in plugin._background_tasks:
                import asyncio
                asyncio.create_task(task)

            self.plugins[plugin_name] = plugin
            logger.info(f"Plugin '{plugin_name}' v{plugin.get_version()} registered {'✅' if plugin.is_enabled() else '❌'}")
        except Exception as e:
            logger.error(f"Failed to register plugin '{plugin_name}': {e}", exc_info=True)
            raise

    async def load_all_plugins(self):
        await self.load_config()
        self._discover_and_register()

    def _discover_and_register(self):
        import importlib
        import pkgutil
        import plugins

        for importer, modname, ispkg in pkgutil.iter_modules(plugins.__path__):
            if not ispkg or modname.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"plugins.{modname}.plugin")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin):
                        import asyncio
                        asyncio.get_event_loop().run_until_complete(
                            self.register_plugin(attr)
                        )
            except Exception as e:
                logger.error(f"Failed to discover plugin '{modname}': {e}")

    async def register_plugin_by_class(self, plugin_class: Type[BasePlugin]):
        await self.register_plugin(plugin_class)

    async def unload_plugin(self, plugin_name: str):
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            await plugin.on_unload()
            del self.plugins[plugin_name]
            logger.info(f"Plugin '{plugin_name}' unloaded")

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        return self.plugins.get(plugin_name)

    async def enable_plugin(self, plugin_name: str):
        if plugin_name in self.plugins:
            self.plugins[plugin_name].config.enabled = True
            logger.info(f"Plugin '{plugin_name}' enabled")

    async def disable_plugin(self, plugin_name: str):
        if plugin_name in self.plugins:
            self.plugins[plugin_name].config.enabled = False
            logger.info(f"Plugin '{plugin_name}' disabled")
