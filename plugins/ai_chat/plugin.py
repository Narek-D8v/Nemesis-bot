import logging

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)


class AiChatPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        from .handlers import handle_ai_chat
        register_hook("ai_chat", handle_ai_chat)
        key_status = "✅ задан" if OPENROUTER_API_KEY else "❌ не задан"
        logger.info(f"AI Chat plugin loaded (OPENROUTER_API_KEY: {key_status})")

    async def on_unload(self):
        unregister_hook("ai_chat")
        logger.info("AI Chat plugin unloaded")
