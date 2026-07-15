import logging
from core.plugin_manager import BasePlugin

logger = logging.getLogger(__name__)


class ExamplePlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        logger.info("Example plugin loaded")
        from .handlers import setup_handlers
        setup_handlers(self.router)

    async def on_unload(self):
        logger.info("Example plugin unloaded")

    async def greet_user(self, user_id: int, name: str) -> str:
        return f"Привет, {name}! Твой ID: {user_id}"
