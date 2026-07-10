import csv
import io
from datetime import datetime

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from bot import logger
from db import db

router = Router()


@router.message(Command("export_stats"))
async def cmd_export_stats(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    is_premium_user = await db.is_premium_user(user_id)
    is_premium_group = await db.is_premium_group(chat_id)
    if not is_premium_user and not is_premium_group:
        await message.reply(
            "⚠️ Эта функция доступна только для премиум-пользователей.\n"
            "Купите личный премиум за 10 ⭐ или групповой за 5 ⭐."
        )
        return

    parts = message.text.split(maxsplit=1)
    period = 30
    if len(parts) > 1:
        arg = parts[1].strip().lower()
        if arg == "all":
            period = None
        else:
            try:
                period = int(arg)
                if period <= 0:
                    await message.reply("ℹ️ Период должен быть положительным числом (дней) или 'all'.")
                    return
            except ValueError:
                await message.reply("ℹ️ Неверный формат. Используйте: /export_stats [число дней | all]")
                return

    if period is None:
        logs = await db.get_moderator_logs_by_days(chat_id, days=36500, limit=10000)
        period_text = "за всё время"
    else:
        logs = await db.get_moderator_logs_by_days(chat_id, days=period)
        period_text = f"за последние {period} дней"

    if not logs:
        await message.reply(f"📭 За выбранный период ({period_text}) логов не найдено.")
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(["Дата", "Действие", "Пользователь (ID)", "Модератор (ID)", "Причина"])
    for row in logs:
        created_at, action, target_id, moderator_id, reason = row
        dt = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([dt, action, target_id, moderator_id, reason or ""])

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"logs_{datetime.now().strftime('%Y-%m-%d')}.csv"

    await message.answer_document(
        BufferedInputFile(csv_bytes, filename=filename),
        caption=f"📊 Экспорт статистики {period_text}\nВсего записей: {len(logs)}"
    )
    logger.info(f"Exported {len(logs)} logs for chat {chat_id} ({period_text})")
