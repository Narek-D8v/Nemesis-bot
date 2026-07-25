import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
PORT = int(os.environ.get('PORT', 8080))
STRING_SESSION = os.environ.get('STRING_SESSION')
OWNER_ID_RAW = os.environ.get('OWNER_ID')
MEDIA_DIR = os.environ.get('MEDIA_DIR', './media')

if not API_ID or not API_HASH:
    raise ValueError("API_ID и API_HASH обязательны. Укажите их в .env")
if not OWNER_ID_RAW:
    raise ValueError("OWNER_ID обязателен. Укажите Telegram ID владельца в .env")
OWNER_ID = int(OWNER_ID_RAW)

MAX_COOLDOWN_ENTRIES = 500
MAX_FILE_SIZE_MB = 1500
