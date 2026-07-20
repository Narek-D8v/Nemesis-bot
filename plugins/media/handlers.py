import os
import random
import re
import tempfile

from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatType

from bot import bot, logger
from . import processor

_RESULT_CAPTIONS = [
    "Вот ваше изображение 🖼️",
    "Держите результат ✨",
    "Ваш шедевр готов 🎨",
    "Получайте, распишитесь 📸",
    "Готово, забирайте ✅",
    "Изображение обработано 🔥",
    "Вуаля! Ваша картинка 🌟",
    "Как вам такое? 👀",
    "Результат налицо 💫",
    "Красота получилась 😍",
    "Держите, это ваше 🎯",
    "Обработка завершена 🎉",
    "Ловите результат 🚀",
    "Готовенькое 🍪",
    "Вот что вышло 🤩",
    "Та-да! Ваше изображение 🎭",
    "Сделано с любовью 💖",
    "Ваш заказ готов 🛠️",
    "Шедевр готов к просмотру 👌",
    "Вот так получилось 🎪",
    "Нравится? Надеюсь, да 😊",
    "Преображение завершено 🦋",
    "Готово к употреблению 🍿",
    "Забегайте, результат ждёт 🚪",
    "Свежеобработанное 🔄",
    "Ваша картинка готова 🏁",
    "Вот, держите на здоровье 🫶",
    "Оп-па! Готово 🎩",
    "Сделано с душой 💝",
    "Красотища вышла 🌈",
]


_PROCESSING_MSGS_VIDEO = [
    "Начинаю обработку видео, ожидайте ✨",
    "Конвертирую видео, секундочку 🎬",
    "Кручу-верчу видео, почти готово 📹",
    "Немного терпения, видео обрабатывается 🎥",
    "Делаю кружок, подождите 🔄",
    "Обрабатываю видео, потерпите чуточку ⏳",
    "Режу и монтирую, сейчас будет 📽️",
    "Запускаю видеопроцессор, ожидайте ⚡",
    "Превращаю видео в кружок 🌀",
    "Немного магии видео, почти готово 🪄",
]

_PROCESSING_MSGS = [
    "Начинаю обработку, ожидайте, пожалуйста ✨",
    "Уже колдую, секундочку! 🎨",
    "Магия начинается, подождите немного 🔮",
    "Обрабатываю, потерпите чуточку 🐌",
    "Превращаю в шедевр, почти готово 🖼️",
    "Немного терпения, уже в процессе 💫",
    "Вжух — и будет красиво, ожидайте 🌟",
    "Кручу-верчу, сделать хочу, минуту! 🌀",
    "Заряжаю фотонную пушку... почти обработал 🚀",
    "Рисую пиксели, не переключайтесь 🎯",
    "Шлифую алгоритмы, секунду ⏳",
    "Немного волшебной пыли и готово ✨🪄",
    "Загружаю фильтры, ожидайте эффекта 🎛️",
    "Считаю до трёх... раз, два... 🕐",
    "Обработчик запущен, ждите результат 📡",
    "Нейросети в деле, скоро будет круто 🤖",
    "Включаю режим творца, подождите 🎨",
    "Уже почти, доделываю последние штрихи 🖌️",
    "Преобразую реальность, ожидайте... 🌈",
    "Так, так, так... сейчас сделаем красиво 💅",
    "Запускаю магический процессор ⚡",
    "Минутку внимания, изображение обрабатывается 🖥️",
    "Ща всё будет, босс, подождите 🔥",
    "Волшебство требует времени, ожидайте 🧙",
    "Достаю фильтры из рукава, секунду 🎩",
    "Настраиваю пиксели, потерпите 🎚️",
    "Скоро будет эпично, чуть-чуть подождите 🏆",
    "Превращаем обычное в необычное, ожидайте 🦋",
    "Калибрую красоту, почти финиш 💎",
    "Машина творчества запущена, ждите результат 🎰",
]


async def _say_processing(message: Message, is_video: bool = False) -> Message | None:
    user = message.from_user
    if user:
        link = f"<a href=\"tg://user?id={user.id}\">{user.first_name}</a>"
    else:
        link = "Пользователь"
    msg = random.choice(_PROCESSING_MSGS_VIDEO if is_video else _PROCESSING_MSGS)
    text = f"{link},\n{msg}"
    try:
        return await message.reply(text)
    except Exception:
        return None

CMD_CIRCLE = re.compile(r'^\.кружок', re.IGNORECASE)
CMD_BW = re.compile(r'^\.чб', re.IGNORECASE)
CMD_ASCII = re.compile(r'^\.ацифруй\s*(.*)', re.IGNORECASE)
CMD_EDGES = re.compile(r'^\.линии', re.IGNORECASE)
CMD_MIRROR = re.compile(r'^\.зерк', re.IGNORECASE)
CMD_PIXEL = re.compile(r'^\.пиксель', re.IGNORECASE)
CMD_NEGATIVE = re.compile(r'^\.негатив', re.IGNORECASE)
CMD_SCANLINES = re.compile(r'^\.полоски', re.IGNORECASE)
CMD_TRIGGERED = re.compile(r'^\.тр', re.IGNORECASE)
CMD_DEMOTIVATOR = re.compile(r'^\.дм\s*(.*)', re.IGNORECASE)


async def _download_file(file_id: str) -> str | None:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    tmp_path = tmp.name
    tmp.close()
    try:
        file_obj = await bot.get_file(file_id)
        if not file_obj.file_path:
            os.unlink(tmp_path)
            return None
        await bot.download_file(file_obj.file_path, destination=tmp_path)
        return tmp_path
    except Exception as e:
        logger.error(f"Download failed: {e}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return None


async def _reply_photo(message: Message, output_path: str):
    try:
        caption = random.choice(_RESULT_CAPTIONS)
        await message.reply_photo(FSInputFile(output_path), caption=caption)
    except Exception as e:
        logger.error(f"Send photo failed: {e}")
        await message.reply("❌ Не удалось отправить результат.")


async def _reply_video_note(message: Message, output_path: str):
    try:
        await bot.send_video_note(
            chat_id=message.chat.id,
            video_note=FSInputFile(output_path),
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"Send video note failed: {e}")
        await message.reply("❌ Не удалось отправить кружок.")


async def _cleanup(*paths: str):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except Exception:
            pass


async def handle_circle(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_CIRCLE.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("❌ Ответьте на видео командой .кружок")
        return True

    video = message.reply_to_message.video
    if video.duration and video.duration > 60:
        await message.reply("❌ Видео должно быть не длиннее 60 секунд.")
        return True

    proc_msg = await _say_processing(message, is_video=True)

    input_path = await _download_file(video.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить видео.")
        return True

    output_path = input_path + "_circle.mp4"
    try:
        await processor.make_video_circle(input_path, output_path, max_duration=60)
        if os.path.getsize(output_path) > 50 * 1024 * 1024:
            await message.reply("❌ Результат слишком большой для отправки.")
            return True
        await _reply_video_note(message, output_path)
    except Exception as e:
        logger.error(f"Circle error: {e}")
        await message.reply("❌ Ошибка обработки видео.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_bw(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_BW.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .чб")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_bw.jpg"
    try:
        processor.black_white(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"BW error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_ascii(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    m = CMD_ASCII.match(text.strip())
    if not m:
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .ацифруй")
        return True

    chars = m.group(1).strip() or "01"

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_ascii.jpg"
    try:
        processor.ascii_art(input_path, output_path, chars)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"ASCII error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_edges(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_EDGES.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .линии")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_edges.jpg"
    try:
        processor.edge_lines(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Edges error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_mirror(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_MIRROR.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .зерк")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_mirror.jpg"
    try:
        processor.mirror(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Mirror error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_pixelate(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_PIXEL.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .пиксель")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_pixel.jpg"
    try:
        processor.pixelate(input_path, output_path, block_size=16)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Pixelate error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_negative(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_NEGATIVE.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .негатив")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_neg.jpg"
    try:
        processor.negative(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Negative error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_scanlines(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_SCANLINES.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .полоски")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_scan.jpg"
    try:
        processor.scanlines(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Scanlines error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_triggered(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not CMD_TRIGGERED.match(text.strip()):
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .тр")
        return True

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_tr.jpg"
    try:
        processor.triggered(input_path, output_path)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Triggered error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True


async def handle_demotivator(message: Message, chat_id: int, user_id: int, text: str, settings: dict) -> bool:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    m = CMD_DEMOTIVATOR.match(text.strip())
    if not m:
        return False
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Ответьте на фото командой .дм [текст]")
        return True

    text_arg = m.group(1).strip() if m.group(1) else ""

    proc_msg = await _say_processing(message)

    photo = message.reply_to_message.photo[-1]
    input_path = await _download_file(photo.file_id)
    if not input_path:
        await message.reply("❌ Не удалось загрузить фото.")
        return True

    output_path = input_path + "_dm.jpg"
    try:
        processor.demotivator(input_path, output_path, text=text_arg)
        await _reply_photo(message, output_path)
    except Exception as e:
        logger.error(f"Demotivator error: {e}")
        await message.reply("❌ Ошибка обработки.")
    finally:
        await _cleanup(input_path, output_path)
    return True
