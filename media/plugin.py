import logging

from core.plugin_manager import BasePlugin
from core.plugin_hooks import register_hook, unregister_hook

logger = logging.getLogger(__name__)


class MediaPlugin(BasePlugin):
    VERSION = "1.0.0"

    async def on_load(self):
        from .processor import download_font
        await download_font()

        from .handlers import (
            handle_circle,
            handle_bw,
            handle_ascii,
            handle_edges,
            handle_mirror,
            handle_pixelate,
            handle_negative,
            handle_scanlines,
            handle_triggered,
            handle_demotivator,
        )

        register_hook("media_circle", handle_circle)
        register_hook("media_bw", handle_bw)
        register_hook("media_ascii", handle_ascii)
        register_hook("media_edges", handle_edges)
        register_hook("media_mirror", handle_mirror)
        register_hook("media_pixelate", handle_pixelate)
        register_hook("media_negative", handle_negative)
        register_hook("media_scanlines", handle_scanlines)
        register_hook("media_triggered", handle_triggered)
        register_hook("media_demotivator", handle_demotivator)

        logger.info("Media plugin loaded: circle, bw, ascii, edges, mirror, pixelate, negative, scanlines, triggered, demotivator")

    async def on_unload(self):
        unregister_hook("media_circle")
        unregister_hook("media_bw")
        unregister_hook("media_ascii")
        unregister_hook("media_edges")
        unregister_hook("media_mirror")
        unregister_hook("media_pixelate")
        unregister_hook("media_negative")
        unregister_hook("media_scanlines")
        unregister_hook("media_triggered")
        unregister_hook("media_demotivator")
        logger.info("Media plugin unloaded")
