import asyncio
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import aiosqlite

from aiohttp import web

from bot import bot, dp, logger
from db import db
from middlewares import AntiFloodMiddleware, NightModeMiddleware, ChatInitMiddleware
from core.plugin_manager import PluginManager

from handlers import start, callbacks, messages, state_handlers, payments, admin, cleanup, commands, scan, export_stats
from config import ADMIN_ID


async def daily_rules_scheduler():
    last_posted: dict[int, str] = {}
    while True:
        try:
            all_settings = {}
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute("SELECT chat_id, config FROM group_settings")
                rows = await cursor.fetchall()
            for chat_id, config_json in rows:
                try:
                    all_settings[chat_id] = json.loads(config_json)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Invalid config JSON for chat {chat_id}, skipping")

            today_str = None
            for chat_id, settings in all_settings.items():
                tz_name = settings.get("timezone", "UTC")
                try:
                    tz = ZoneInfo(tz_name)
                except (KeyError, TypeError):
                    tz = ZoneInfo("UTC")
                now = datetime.now(tz)
                if today_str is None:
                    today_str = f"{now.year}-{now.month:02d}-{now.day:02d}"
                current_time = f"{now.hour:02d}:{now.minute:02d}"

                dr = settings.get("daily_rules", {})
                if dr.get("enabled") and dr.get("time") == current_time:
                    posted_key = last_posted.get(chat_id)
                    if posted_key == today_str:
                        continue
                    is_premium = await db.is_premium_group(chat_id)
                    if is_premium:
                        try:
                            await bot.send_message(
                                chat_id,
                                f"📋 <b>Правила группы</b>\n\n{dr.get('text', 'Правила группы...')}"
                            )
                            last_posted[chat_id] = today_str
                            logger.info(f"Daily rules posted to {chat_id}")
                        except Exception as e:
                            logger.warning(f"Failed to post daily rules to {chat_id}: {e}")

            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Daily rules scheduler error: {e}")
            await asyncio.sleep(60)


async def on_startup(plugin_manager: PluginManager | None = None):
    await db.init_db()
    logger.info("Database initialized")

    if ADMIN_ID:
        await db.activate_premium_user(ADMIN_ID, 36500)
        logger.info(f"Owner {ADMIN_ID} premium activated (100 years)")
    else:
        logger.warning("ADMIN_ID is 0 — owner premium not activated. Set ADMIN_ID in .env")

    dp.message.middleware(ChatInitMiddleware())
    dp.message.middleware(AntiFloodMiddleware())
    dp.message.middleware(NightModeMiddleware())

    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(scan.router)
    dp.include_router(export_stats.router)
    dp.include_router(state_handlers.router)
    dp.include_router(callbacks.router)
    dp.include_router(payments.router)
    dp.include_router(cleanup.router)
    dp.include_router(admin.router)
    dp.include_router(messages.router)

    logger.info("Legacy handlers registered")

    if plugin_manager:
        await plugin_manager.load_config()
        await plugin_manager._discover_and_register()
        logger.info(f"Plugin system: {len(plugin_manager.plugins)} plugins loaded")
        for name, p in plugin_manager.plugins.items():
            status = "✅" if p.is_enabled() else "❌"
            logger.info(f"  {status} {name} v{p.get_version()}")

    asyncio.create_task(daily_rules_scheduler())
    logger.info("Daily rules scheduler started")

    asyncio.create_task(cleanup_old_logs())
    logger.info("Old logs cleanup task started")

    asyncio.create_task(run_health_server())
    logger.info("Health check server started")


async def run_health_server():
    app = web.Application()

    async def handle(request):
        return web.Response(text="Bot is running")

    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server listening on 0.0.0.0:{port}")
    await asyncio.Event().wait()


async def cleanup_old_logs():
    while True:
        try:
            deleted = await db.delete_old_logs(days=90)
            logger.info(f"🗑️ Удалено {deleted} старых записей из moderator_logs (старше 90 дней)")
        except Exception as e:
            logger.error(f"Ошибка при удалении старых логов: {e}")
        await asyncio.sleep(86400)


async def main():
    logger.info("Starting bot...")

    plugin_manager = PluginManager(dp, config_path="config.yaml")
    await on_startup(plugin_manager)

    logger.info("Bot started polling")
    await dp.start_polling(bot, allowed_updates=[
        "message",
        "callback_query",
        "chat_member",
        "my_chat_member",
        "pre_checkout_query",
        "message_reaction",
    ])


if __name__ == "__main__":
    asyncio.run(main())
