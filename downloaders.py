import asyncio
import glob
import os
import re
import subprocess
import sys
import time
import urllib.request

import aiohttp
import yt_dlp

from config import MEDIA_DIR, logger
from utils import format_bytes

_COOKIES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'cookies.txt'))
_COOKIES_VALID = False
if os.path.exists(_COOKIES_PATH):
    with open(_COOKIES_PATH, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if '.youtube.com' in content and ('\tTRUE\t' in content or 'cookie' in content.lower()):
        _COOKIES_VALID = True
        logger.info(f"cookies.txt: {len(content)} байт, формат OK")
    else:
        logger.warning("cookies.txt существует, но похож на неверный формат (нужен Netscape)")
else:
    logger.info("cookies.txt не найден — скачивание YouTube может не работать без авторизации")
    logger.info("Создай cookies.txt из cookies.txt.example и заполни своими cookies YouTube")

def _update_ytdlp():
    try:
        old_ver = getattr(yt_dlp.version, '__version__', '???')
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet', 'yt-dlp'],
            capture_output=True, timeout=60
        )
        result = subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--version'],
            capture_output=True, text=True, timeout=30
        )
        new_ver = result.stdout.strip() or '???'
        if old_ver != new_ver:
            logger.info(f"yt-dlp обновлён: {old_ver} → {new_ver}")
        else:
            logger.info(f"yt-dlp {old_ver} (актуальная)")
    except Exception as ex:
        logger.warning(f"yt-dlp auto-update failed: {ex}")

_update_ytdlp()

try:
    logger.info(f"yt-dlp version: {yt_dlp.version.__version__}")
except Exception:
    logger.info("yt-dlp version: unknown")

_JS_RUNTIMES = {}
for _rt in ('node', 'deno'):
    try:
        r = subprocess.run([_rt, '--version'], capture_output=True, check=False, timeout=5)
        if r.returncode == 0:
            _JS_RUNTIMES[_rt] = {}
            logger.info(f"JS runtime: {_rt} найден")
    except (FileNotFoundError, OSError):
        pass
if not _JS_RUNTIMES:
    logger.warning("JS runtime не найден (node/deno) — установи для лучшей совместимости с YouTube")
    logger.warning("  apt install nodejs  или  curl -fsSL https://deno.land/install.sh | sh")

_YT_DL_OPTS = {
    'outtmpl': os.path.join(MEDIA_DIR, '%(id)s.%(ext)s'),
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'playlist_items': '1',
    'extractor_retries': 5,
    'fragment_retries': 5,
    'retry_sleep': lambda n: 5 + n * 3,
    'throttledratelimit': 100000,
    'sleep_interval_requests': 2,
    'js_runtimes': _JS_RUNTIMES,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
            'player_skip': ['js'],
        },
    },
    'cookiefile': _COOKIES_PATH if _COOKIES_VALID else None,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
    },
}

_HAS_FFMPEG = False
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    _HAS_FFMPEG = True
except Exception:
    pass

_max_file_size = 1500


def set_max_file_size(mb: int):
    global _max_file_size
    _max_file_size = mb


_INVIDIOUS_INSTANCES = [
    'inv.nadeko.net',
    'yewtu.be',
    'invidious.snopyta.org',
    'inv.vern.cc',
    'vid.puffyan.us',
]


def _yt_id(url):
    m = re.search(r'(?:v=|youtu\.be/|list=)([a-zA-Z0-9_-]{11})', url)
    return m.group(1) if m else None


async def _try_invidious(url, mode):
    video_id = _yt_id(url)
    if not video_id:
        return None
    os.makedirs(MEDIA_DIR, exist_ok=True)
    for instance in _INVIDIOUS_INSTANCES:
        try:
            api_url = f"https://{instance}/api/v1/videos/{video_id}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(api_url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            title = data.get('title', video_id) or video_id
            combined = data.get('formatStreams') or []
            adaptive = data.get('adaptiveFormats') or []
            if mode == 'audio':
                picks = adaptive + combined
                best = max((f for f in picks if f.get('url') and (f.get('bitrate') or 0)), key=lambda f: f['bitrate'], default=None)
            else:
                best = max((f for f in combined if f.get('url') and (f.get('height') or 0)), key=lambda f: f['height'], default=None)
                if not best and adaptive:
                    best = max((f for f in adaptive if f.get('url') and (f.get('height') or 0)), key=lambda f: f['height'], default=None)
            if not best:
                continue
            ext = best.get('container', 'mp4')
            path = os.path.join(MEDIA_DIR, f"{video_id}_invidious.{ext}")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
                async with s.get(best['url']) as resp:
                    if resp.status != 200:
                        continue
                    with open(path, 'wb') as f:
                        while True:
                            chunk = await resp.content.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                logger.info(f"Invidious download OK: {title} ({instance})")
                return path
        except Exception as ex:
            logger.warning(f"Invidious {instance} failed: {ex}")
            continue
    return None


def _resolve_yt_path(ydl, info):
    filepath = None
    if info.get('requested_downloads'):
        filepath = info['requested_downloads'][0].get('filepath')
    if not filepath or not os.path.exists(filepath or ''):
        filepath = ydl.prepare_filename(info)
    if filepath and os.path.exists(filepath):
        return filepath
    video_id = info.get('id')
    if video_id:
        pattern = os.path.join(MEDIA_DIR, f'{video_id}.*')
        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if matches:
            return matches[0]
    raise ValueError("Файл не найден после загрузки (возможно, проблема с ffmpeg пост-обработкой)")


def _probe_formats(url, opts):
    attempts = [
        ('android', {'extract_flat': True,
                     'extractor_args': {'youtube': {'player_client': ['android'],
                                                    'player_skip': ['js']}}}),
        ('web', {'extract_flat': True,
                 'extractor_args': {'youtube': {'player_client': ['web'],
                                                'player_skip': ['js']}}}),
    ]
    for label, extra in attempts:
        probe_opts = dict(opts)
        probe_opts.pop('format', None)
        probe_opts.pop('extractor_args', None)
        probe_opts['skip_download'] = True
        probe_opts.update(extra)
        try:
            with yt_dlp.YoutubeDL(probe_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                logger.info(f"YouTube probe [{label}]: id={info.get('id', '?')}, "
                            f"title=\"{info.get('title', '?')[:80]}\", "
                            f"channel={info.get('channel', '?')}")
                if info.get('title') or info.get('entries'):
                    return info
        except yt_dlp.utils.DownloadError as ex:
            logger.warning(f"Probe [{label}] failed: {ex}")
            continue
        except Exception as ex:
            logger.warning(f"Probe [{label}] unexpected: {ex}")
            continue
    _dl_diag(url)
    return None


def _dl_diag(url):
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--verbose', '--flat-playlist', '-J', '--no-check-certificates', url],
            capture_output=True, text=True, timeout=60
        )
        logger.info(f"yt-dlp CLI stdout: {result.stdout[:500]}")
        logger.info(f"yt-dlp CLI stderr: {result.stderr[:500]}")
    except Exception as ex:
        logger.error(f"yt-dlp CLI diag failed: {ex}")


def _cli_download(url, output_path):
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-o', output_path,
        '--no-playlist',
        '--no-check-certificates',
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            matches = sorted(glob.glob(output_path.replace('%(ext)s', '*')), key=os.path.getmtime, reverse=True)
            if matches:
                return matches[0]
            stderr_lower = result.stderr.lower()
            m = re.search(r'\[download\]\s+(.+?)\s+has already been downloaded', result.stderr, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        logger.error(f"CLI download failed (rc={result.returncode}): {result.stderr[:3000]}")
        return None
    except subprocess.TimeoutExpired:
        logger.error("CLI download timed out")
        return None
    except Exception as ex:
        logger.error(f"CLI download error: {ex}")
        return None


def _pick_format_and_download(url, opts, quality, is_audio):
    os.makedirs(MEDIA_DIR, exist_ok=True)

    if not _HAS_FFMPEG:
        probe = _probe_formats(url, opts)
        if probe is None:
            logger.warning("Python API probe failed, trying CLI fallback...")
            ext = 'mp3' if is_audio else 'mp4'
            cli_path = os.path.join(MEDIA_DIR, f'%(id)s.{ext}')
            cli_result = _cli_download(url, cli_path)
            if cli_result:
                return cli_result
            if not _JS_RUNTIMES:
                hint = (
                    "\n\n📦 Установи JS-рантайм для yt-dlp и перезапусти:\n"
                    "  apt install nodejs\n"
                    "  # или: curl -fsSL https://deno.land/install.sh | sh"
                )
            else:
                hint = (
                    "\n\n🔑 YouTube всё ещё блокирует IP. Тогда нужны cookies:\n"
                    "  cookies.txt.example → cookies.txt, экспорт из браузера"
                )
            raise ValueError("YouTube блокирует сервер." + hint)

    if _HAS_FFMPEG and is_audio:
        opts['format'] = 'ba/b'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif _HAS_FFMPEG and not is_audio:
        opts['format'] = 'bv*+ba/b'
        if quality:
            opts['format'] = f'bv*[height<={quality}]+ba/b[height<={quality}]'
        opts['merge_output_format'] = 'mp4'
    else:
        formats_to_try = ['ba', 'b'] if is_audio else ['b', 'bv']
        last_ex = None
        for fmt in formats_to_try:
            opts['format'] = fmt
            try:
                logger.info(f'yt-dlp opts: format={opts.get("format")}, ffmpeg={_HAS_FFMPEG}')
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return _resolve_yt_path(ydl, info)
            except yt_dlp.utils.DownloadError as ex:
                last_ex = ex
                continue
        raise ValueError(f"YouTube: {last_ex}")

    logger.info(f'yt-dlp opts: format={opts.get("format")}, ffmpeg={_HAS_FFMPEG}')
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return _resolve_yt_path(ydl, info)


async def _download_yt_video(url, quality=None):
    def _dl():
        try:
            return _pick_format_and_download(url, dict(_YT_DL_OPTS), quality, is_audio=False)
        except yt_dlp.utils.DownloadError as ex:
            raise ValueError(f"YouTube: {ex}")
        except ValueError:
            raise
        except Exception as ex:
            logger.error(f"yt-dlp unexpected error: {ex}", exc_info=True)
            raise ValueError(f"YouTube: {ex}")

    return await asyncio.to_thread(_dl)


async def _download_yt_audio(url):
    def _dl():
        try:
            return _pick_format_and_download(url, dict(_YT_DL_OPTS), quality=None, is_audio=True)
        except yt_dlp.utils.DownloadError as ex:
            raise ValueError(f"YouTube: {ex}")
        except ValueError:
            raise
        except Exception as ex:
            logger.error(f"yt-dlp unexpected error: {ex}", exc_info=True)
            raise ValueError(f"YouTube: {ex}")

    return await asyncio.to_thread(_dl)


async def _download_instagram_video(url):
    def _dl():
        try:
            opts = dict(_YT_DL_OPTS)
            opts['format'] = 'b'
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return _resolve_yt_path(ydl, info)
        except yt_dlp.utils.DownloadError as ex:
            raise ValueError(f"Instagram: {ex}")
    return await asyncio.to_thread(_dl)


async def _download_tiktok_video(url):
    def _dl():
        try:
            opts = dict(_YT_DL_OPTS)
            opts['format'] = 'b'
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return _resolve_yt_path(ydl, info)
        except yt_dlp.utils.DownloadError as ex:
            raise ValueError(f"TikTok: {ex}")
    return await asyncio.to_thread(_dl)


_GEN_OPTS = {
    'outtmpl': os.path.join(MEDIA_DIR, '%(id)s.%(ext)s'),
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'playlist_items': '1',
    'extractor_retries': 3,
    'fragment_retries': 3,
    'retry_sleep': lambda n: 5 + n * 2,
    'sleep_interval_requests': 1,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    },
}


def _is_direct_media(url):
    return bool(re.search(r'\.(mp4|webm|mkv|avi|mov|flv|wmv|mp3|aac|ogg|wav|m4a)($|\?)', url.lower()))


def _find_m3u8_in_html(html):
    urls = re.findall(r'(https?://[^"\'\s<>]+?\.m3u8[^"\'\s<>]*)', html)
    if not urls:
        urls = re.findall(r'["\']([^"\']+\.m3u8[^"\']*)["\']', html)
    return urls


def _resolve_url(base, uri):
    if uri.startswith('http://') or uri.startswith('https://'):
        return uri
    from urllib.parse import urljoin
    return urljoin(base, uri)


async def _download_m3u8_video(m3u8_url, output_path):
    import m3u8
    from urllib.parse import urljoin
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(m3u8_url) as resp:
                if resp.status != 200:
                    return None
                content = await resp.text()
        playlist = m3u8.loads(content)
        seg_urls = []
        if playlist.is_variant:
            top = max(playlist.playlists, key=lambda p: p.stream_info.resolution[1] if p.stream_info.resolution else 0)
            variant_url = _resolve_url(m3u8_url, top.uri)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.get(variant_url) as resp:
                    if resp.status != 200:
                        return None
                    content = await resp.text()
            playlist = m3u8.loads(content)
        for seg in playlist.segments:
            uri = _resolve_url(m3u8_url, seg.uri)
            seg_urls.append(uri)
        if not seg_urls:
            return None
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
            with open(output_path, 'wb') as f:
                for seg_url in seg_urls:
                    try:
                        async with s.get(seg_url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                f.write(data)
                    except Exception:
                        continue
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as ex:
        logger.warning(f"m3u8 download failed: {ex}")
    return None


async def _download_generic(url, mode, event_edit_func):
    await event_edit_func("🌐 Пробую yt-dlp...")
    try:
        opts = dict(_GEN_OPTS)
        if mode == 'audio':
            if _HAS_FFMPEG:
                opts['format'] = 'ba/b'
                opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
            else:
                opts['format'] = 'ba'
        filename = await asyncio.to_thread(lambda: _dl_generic_sync(url, opts))
        if filename:
            return filename
    except Exception as ex:
        logger.warning(f"yt-dlp generic failed: {ex}")

    if _is_direct_media(url):
        await event_edit_func("📥 Скачиваю напрямую...")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
                async with s.get(url) as resp:
                    if resp.status == 200:
                        ext = os.path.splitext(url.split('?')[0])[1] or '.mp4'
                        path = os.path.join(MEDIA_DIR, f'direct_{int(time.time())}{ext}')
                        with open(path, 'wb') as f:
                            while True:
                                chunk = await resp.content.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                        if os.path.getsize(path) > 0:
                            return path
        except Exception as ex:
            logger.warning(f"Direct download failed: {ex}")

    await event_edit_func("🖼 Пробую скачать как картинку...")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    og_img = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
                    if og_img:
                        img_url = og_img.group(1).replace('&amp;', '&')
                        ext = os.path.splitext(img_url.split('?')[0])[1] or '.jpg'
                        path = os.path.join(MEDIA_DIR, f'img_{int(time.time())}{ext}')
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s2:
                            async with s2.get(img_url) as img_resp:
                                if img_resp.status == 200:
                                    with open(path, 'wb') as f:
                                        async for chunk in img_resp.content.iter_chunked(65536):
                                            f.write(chunk)
                                    if os.path.getsize(path) > 0:
                                        return path
    except Exception as ex:
        logger.warning(f"Image fallback failed: {ex}")

    await event_edit_func("🔍 Ищу m3u8...")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    m3u8_urls = _find_m3u8_in_html(html)
                    for m3u8_url in m3u8_urls:
                        path = os.path.join(MEDIA_DIR, f'm3u8_{int(time.time())}.mp4')
                        result = await _download_m3u8_video(m3u8_url, path)
                        if result:
                            return result
    except Exception as ex:
        logger.warning(f"m3u8 search failed: {ex}")

    return None


def _dl_generic_sync(url, opts):
    last_ex = None
    for fmt_override in [None, 'b', 'best']:
        try:
            if fmt_override:
                opts['format'] = fmt_override
            elif 'format' in opts:
                del opts['format']
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = None
                if info.get('requested_downloads'):
                    filepath = info['requested_downloads'][0].get('filepath')
                if not filepath or not os.path.exists(filepath or ''):
                    filepath = ydl.prepare_filename(info)
                if filepath and os.path.exists(filepath):
                    return filepath
                video_id = info.get('id')
                if video_id:
                    matches = sorted(glob.glob(os.path.join(MEDIA_DIR, f'{video_id}.*')), key=os.path.getmtime, reverse=True)
                    if matches:
                        return matches[0]
        except yt_dlp.utils.DownloadError as ex:
            last_ex = ex
            if 'No video formats' in str(ex):
                continue
            raise
    last_ex_str = str(last_ex) if last_ex else ''

    if 'No video formats' in last_ex_str:
        try:
            with yt_dlp.YoutubeDL({**opts, 'skip_download': True, 'quiet': True, 'no_warnings': True, 'format': None}) as ydl:
                info = ydl.extract_info(url, download=False)
            thumb_url = info.get('thumbnail') or (info.get('entries') or [{}])[0].get('thumbnail')
            if thumb_url:
                ext = os.path.splitext(thumb_url.split('?')[0])[1] or '.jpg'
                path = os.path.join(MEDIA_DIR, f'img_{info.get("id", int(time.time()))}{ext}')
                urllib.request.urlretrieve(thumb_url, path)
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return path
        except Exception as ex:
            logger.warning(f"Thumbnail download failed: {ex}")

    return None


async def _download_pinterest_pin(url):
    yt_path = await _try_ytdlp_pinterest(url)
    if yt_path:
        return yt_path

    logger.info("No video from yt-dlp, scraping image...")
    originals_url, fallback_url = await _scrape_pinterest_image(url)
    if originals_url:
        try:
            return await _generic_direct_download(originals_url, fallback_736x=fallback_url)
        except ValueError as ex:
            if fallback_url:
                logger.info(f"originals failed ({ex}), trying 736x fallback")
                return await _generic_direct_download(fallback_url)
            raise
    raise ValueError("Pinterest: не удалось найти медиа на странице")


async def _try_ytdlp_pinterest(url):
    def _dl():
        opts = dict(_YT_DL_OPTS)
        opts['format'] = 'bv*+ba/b'
        opts['merge_output_format'] = 'mp4'
        opts['extractor_args'] = {'pinterest': {'video': ['true']}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fp = _resolve_yt_path(ydl, info)
                if fp:
                    return fp
        except yt_dlp.utils.DownloadError as ex:
            if 'No video formats' in str(ex):
                return None
            logger.warning(f"yt-dlp Pinterest error: {ex}")
            return None
        except Exception as ex:
            logger.warning(f"yt-dlp Pinterest error: {ex}")
        return None
    return await asyncio.to_thread(_dl)


async def _scrape_pinterest_image(url):
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, allow_redirects=True) as resp:
            if resp.status != 200:
                return None, None
            html = await resp.text()

    og = re.search(r'<meta[^>]+(?:property|name)="og:image"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if not og:
        og = re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="og:image"', html, re.IGNORECASE)
    if og:
        img = og.group(1).replace('&amp;', '&')
        fallback = None
        if '/736x/' in img:
            fallback = img
            img = img.replace('/736x/', '/originals/')
        return img, fallback

    img_urls = re.findall(r'(https://i\.pinimg\.com/(?:originals|736x|1200x|474x|236x|170x)/[a-zA-Z0-9/_-]+\.(?:jpg|jpeg|png|gif|webp))', html)
    if not img_urls:
        return None, None

    seen = set()
    unique = []
    for u in img_urls:
        n = u.rstrip(')')
        if n not in seen:
            seen.add(n)
            unique.append(n)

    for prefix in ('/originals/', '/1200x/', '/736x/', '/474x/', '/236x/', '/170x/'):
        for u in unique:
            if prefix in u:
                if prefix != '/originals/':
                    fallback = u
                    u = u.replace(prefix, '/originals/', 1)
                    return u, fallback
                return u, None
    return unique[0], None


async def _generic_direct_download(url, *, referer='https://www.pinterest.com/', fallback_736x=None):
    ext = os.path.splitext(url.split('?')[0].split('/')[-1])[1]
    if not ext or ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.mov'):
        ext = '.jpg'
    path = os.path.join(MEDIA_DIR, f'pin_{int(time.time())}{ext}')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Referer': referer,
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
        async with s.get(url, headers=headers) as resp:
            if resp.status == 403 and fallback_736x:
                logger.info("originals blocked (403), fallback to 736x")
                return await _generic_direct_download(fallback_736x, referer=referer)
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status} при скачивании {url}")
            with open(path, 'wb') as f:
                while True:
                    chunk = await resp.content.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    raise ValueError("Файл пуст после скачивания")


async def run_download(event_edit_func, url, mode='video', quality=None, timeout=600):
    logger.info(f"[download] Starting: {url} (mode={mode})")
    try:
        is_instagram = 'instagram.com' in url.lower()
        is_youtube = 'youtube.com' in url.lower() or 'youtu.be' in url.lower()
        is_tiktok = 'tiktok.com' in url.lower()
        is_pinterest = 'pinterest.com' in url.lower() or 'pin.it' in url.lower()
        if is_youtube:
            m = re.match(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11})', url)
            if m:
                url = m.group(1)

        if is_pinterest:
            await event_edit_func("📥 Скачиваю из Pinterest...")
            filename = await asyncio.wait_for(
                _download_pinterest_pin(url), timeout=timeout
            )
        elif is_tiktok:
            await event_edit_func("📥 Скачиваю из TikTok...")
            filename = await asyncio.wait_for(
                _download_tiktok_video(url), timeout=timeout
            )
        elif is_instagram:
            await event_edit_func("📥 Скачиваю из Instagram...")
            filename = await asyncio.wait_for(
                _download_instagram_video(url), timeout=timeout
            )
        elif is_youtube:
            if mode == 'audio':
                await event_edit_func("🎵 Скачиваю аудио...")
                filename = await asyncio.wait_for(
                    _download_yt_audio(url), timeout=timeout
                )
            else:
                qual = f"{quality}p" if quality else None
                await event_edit_func(f"📥 Скачиваю видео ({qual or 'авто'})...")
                filename = await asyncio.wait_for(
                    _download_yt_video(url, quality), timeout=timeout
                )
        else:
            return await _download_generic(url, mode, event_edit_func)

        if filename and os.path.exists(filename):
            size = format_bytes(os.path.getsize(filename))
            logger.info(f"[download] OK: {filename} ({size})")
            return filename
        logger.warning(f"[download] file not found after download: {url}")
        return None
    except asyncio.TimeoutError:
        await event_edit_func("❌ Превышено время ожидания (10 мин).")
        logger.warning(f"Download timeout: {url}")
        return None
    except ValueError as ex:
        logger.warning(f"Download error: {ex}")
        if is_youtube:
            await event_edit_func("🔄 Пробую через Invidious...")
            invidious_path = await _try_invidious(url, mode)
            if invidious_path:
                return invidious_path
        await event_edit_func(f"❌ {ex}")
        return None
    except Exception as ex:
        logger.error(f"Download error: {ex}", exc_info=True)
        await event_edit_func(f"❌ **Ошибка:** {ex}")
        return None


async def send_and_clean(event_edit_func, client, chat_id, filepath, caption=''):
    if not filepath or not os.path.exists(filepath):
        return
    try:
        size_mb = os.path.getsize(filepath) / 1024 / 1024
    except OSError:
        return
    if size_mb > _max_file_size:
        await event_edit_func(f"❌ Слишком большой файл (> {_max_file_size} МБ).")
    else:
        await event_edit_func("📤 **Отправляю файл...**")
        try:
            await client.send_file(chat_id, filepath, caption=caption)
        except Exception as ex:
            await event_edit_func(f"❌ Ошибка отправки: {ex}")
    await asyncio.sleep(5)
    for _ in range(3):
        try:
            os.remove(filepath)
            break
        except OSError:
            await asyncio.sleep(1)
