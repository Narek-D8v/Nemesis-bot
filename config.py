import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
raw = os.getenv("ADMIN_ID", "0")
ADMIN_ID = int(raw) if raw else 0
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in .env file")
