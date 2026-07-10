import os
import tempfile

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from bot import bot, logger
from db import db
from utils.virustotal import check_url_safety, check_file_safety, extract_urls, SCANNABLE_EXTENSIONS, MAX_FILE_SIZE

router = Router()


def format_url_result(url: str, stats: dict) -> str:
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)

    if malicious + suspicious > 0:
        status = "⚠️ Опасно! Не переходите по ссылке."
        emoji = "🚫"
    else:
        status = "✅ Безопасно"
        emoji = "🔍"

    return (
        f"{emoji} <b>Результат проверки:</b>\n"
        f"Ссылка: {url}\n"
        f"Вредоносных: {malicious}\n"
        f"Подозрительных: {suspicious}\n"
        f"Безопасных: {harmless}\n"
        f"Не обнаружено: {undetected}\n"
        f"Статус: {status}"
    )


def format_file_result(file_name: str, stats: dict) -> str:
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)

    if "error" in stats:
        if stats["error"] == "too_large":
            return f"⚠️ Файл <b>{file_name}</b> слишком большой (>32 МБ). Проверьте вручную на сайте VirusTotal."

    if malicious + suspicious > 0:
        status = "⚠️ Опасно! Файл содержит угрозу."
        emoji = "🚫"
    else:
        status = "✅ Безопасно"
        emoji = "🔍"

    return (
        f"{emoji} <b>Результат проверки файла:</b>\n"
        f"Файл: {file_name}\n"
        f"Вредоносных: {malicious}\n"
        f"Подозрительных: {suspicious}\n"
        f"Безопасных: {harmless}\n"
        f"Не обнаружено: {undetected}\n"
        f"Статус: {status}"
    )


async def has_scan_premium(user_id: int, chat_id: int) -> bool:
    if await db.is_premium_user(user_id):
        return True
    if await db.is_premium_group(chat_id):
        return True
    return False


@router.message(Command("scan"))
async def cmd_scan(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await has_scan_premium(user_id, chat_id):
        await message.reply(
            "⚠️ Эта функция доступна только для премиум-пользователей.\n"
            "Купите личный премиум за 10 ⭐ или групповой за 5 ⭐."
        )
        return

    reply = message.reply_to_message

    if reply:
        urls = []
        if reply.text:
            urls = extract_urls(reply.text)
        if reply.caption:
            urls = extract_urls(reply.caption)

        file_info = None
        for attr in ("document", "video", "audio", "voice", "animation"):
            obj = getattr(reply, attr, None)
            if obj:
                file_info = (attr, obj)
                break

        if urls:
            for url in urls:
                stats = await check_url_safety(url)
                if stats:
                    await message.reply(format_url_result(url, stats))
                else:
                    await message.reply(f"⚠️ Не удалось проверить ссылку: {url}")
            return

        if file_info:
            attr, obj = file_info
            file_name = getattr(obj, "file_name", f"file.{attr}") or f"file.{attr}"
            file_id = obj.file_id

            file_size = getattr(obj, "file_size", 0)
            if file_size > MAX_FILE_SIZE:
                await message.reply(format_file_result(file_name, {"error": "too_large"}))
                return

            ext = os.path.splitext(file_name)[1].lower()
            if ext not in SCANNABLE_EXTENSIONS:
                await message.reply(f"ℹ️ Расширение <b>{ext}</b> не проверяется. Сканируются: {', '.join(sorted(SCANNABLE_EXTENSIONS))}")
                return

            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    await bot.download(file_id, destination=tmp.name)
                    tmp_path = tmp.name

                try:
                    stats = await check_file_safety(tmp_path, file_name)
                    if stats:
                        await message.reply(format_file_result(file_name, stats))
                    else:
                        await message.reply(f"⚠️ Не удалось проверить файл: {file_name}")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Scan file error: {e}")
                await message.reply("⚠️ Ошибка при проверке файла.")
            return

        await message.reply("ℹ️ Ответьте на сообщение со ссылкой или файлом, чтобы проверить.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        url = parts[1].strip()
        if url.startswith("http"):
            stats = await check_url_safety(url)
            if stats:
                await message.reply(format_url_result(url, stats))
            else:
                await message.reply(f"⚠️ Не удалось проверить ссылку: {url}")
            return

    await message.reply(
        "ℹ️ <b>Использование /scan:</b>\n\n"
        "• <code>/scan</code> — в ответ на сообщение со ссылкой или файлом\n"
        "• <code>/scan &lt;URL&gt;</code> — проверить указанную ссылку\n\n"
        "Доступно для премиум-пользователей."
    )
