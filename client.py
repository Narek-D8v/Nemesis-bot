from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, STRING_SESSION

if STRING_SESSION:
    client = TelegramClient(StringSession(STRING_SESSION), int(API_ID), API_HASH)
else:
    client = TelegramClient('my_userbot', int(API_ID), API_HASH)
