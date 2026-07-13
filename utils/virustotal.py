import time
import re
import hashlib
import os
import asyncio

from config import VIRUSTOTAL_API_KEY
from bot import logger

url_cache: dict[str, tuple[dict, float]] = {}
file_cache: dict[str, tuple[dict, float]] = {}
URL_CACHE_TTL = 3600
FILE_CACHE_TTL = 86400

URL_EXTRACT = re.compile(r'https?://[^\s]+', re.IGNORECASE)

SCANNABLE_EXTENSIONS = {
    '.exe', '.scr', '.bat', '.com', '.dll', '.jar', '.apk',
    '.docm', '.xlsm', '.pptm', '.zip', '.rar', '.7z', '.gz',
    '.ps1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
    '.msi', '.msp', '.cab', '.iso', '.img',
}
MAX_FILE_SIZE = 32 * 1024 * 1024

_vt_rate_limit = asyncio.Lock()
_vt_last_call: float = 0
VT_MIN_INTERVAL = 16


def extract_urls(text: str) -> list[str]:
    return URL_EXTRACT.findall(text)


def get_file_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


async def check_url_safety(url: str):
    if not VIRUSTOTAL_API_KEY:
        return None

    now = time.time()
    cached = url_cache.get(url)
    if cached:
        stats, ts = cached
        if now - ts < URL_CACHE_TTL:
            return stats
        del url_cache[url]

    global _vt_last_call
    async with _vt_rate_limit:
        now_local = time.time()
        since_last = now_local - _vt_last_call
        if since_last < VT_MIN_INTERVAL:
            await asyncio.sleep(VT_MIN_INTERVAL - since_last)
        _vt_last_call = time.time()

    try:
        from vt import Client
        async with Client(VIRUSTOTAL_API_KEY) as client:
            analysis = await client.scan_url_async(url)
            obj = await client.get_object_async(f"/analyses/{analysis.id}")
            stats = dict(obj.stats)
            url_cache[url] = (stats, now)
            logger.info(f"VirusTotal URL check OK: {url} -> {stats}")
            return stats
    except Exception as e:
        logger.error(f"VirusTotal URL error for {url}: {e}")
        return None


async def check_file_safety(file_path: str, file_name: str = ""):
    if not VIRUSTOTAL_API_KEY:
        return None

    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        return None
    if file_size > MAX_FILE_SIZE:
        logger.warning(f"File too large for VT: {file_name or file_path} ({file_size} bytes)")
        return {"error": "too_large", "size": file_size}

    sha256 = get_file_sha256(file_path)
    now = time.time()
    cached = file_cache.get(sha256)
    if cached:
        stats, ts = cached
        if now - ts < FILE_CACHE_TTL:
            logger.info(f"VirusTotal file cache hit: {sha256}")
            return stats
        del file_cache[sha256]

    global _vt_last_call
    async with _vt_rate_limit:
        now_local = time.time()
        since_last = now_local - _vt_last_call
        if since_last < VT_MIN_INTERVAL:
            await asyncio.sleep(VT_MIN_INTERVAL - since_last)
        _vt_last_call = time.time()

    try:
        from vt import Client
        async with Client(VIRUSTOTAL_API_KEY) as client:
            with open(file_path, "rb") as fh:
                analysis = await client.scan_file_async(fh)
            obj = await client.get_object_async(f"/analyses/{analysis.id}")
            stats = dict(obj.stats)
            file_cache[sha256] = (stats, now)
            logger.info(f"VirusTotal file check OK: {file_name or file_path} -> {stats}")
            return stats
    except Exception as e:
        logger.error(f"VirusTotal file error for {file_name or file_path}: {e}")
        return None
