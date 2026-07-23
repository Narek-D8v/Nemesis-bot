import logging

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook

logger = logging.getLogger(__name__)


class AiChatPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        from .handlers import handle_ai_chat
        register_hook("ai_chat", handle_ai_chat)
        logger.info("AI Chat plugin loaded")

    async def on_unload(self):
        unregister_hook("ai_chat")
        logger.info("AI Chat plugin unloaded")
