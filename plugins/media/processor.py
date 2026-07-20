import asyncio
import math
import os
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).parent / "fonts"
_FONT_LOCAL = _FONT_DIR / "NotoSans-Regular.ttf"
_FONT_URL = (
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosans/NotoSans-Regular.ttf"
)

_FONT_CANDIDATES = [
    str(_FONT_LOCAL),
    str(Path(__file__).parent.parent.parent / "utils" / "fonts" / "impact.ttf"),
    "arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


def _ensure_font(size: int = 40):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


async def download_font():
    if _FONT_LOCAL.exists():
        return
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(_FONT_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    _FONT_LOCAL.write_bytes(await resp.read())
    except Exception:
        pass


def black_white(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGB")
    img = ImageOps.grayscale(img)
    img.save(output_path)


def ascii_art(input_path: str, output_path: str, chars: str = "01"):
    img = Image.open(input_path).convert("L")
    width, height = img.size
    aspect = height / width
    new_w = 120
    new_h = int(aspect * new_w * 0.55)
    img = img.resize((new_w, new_h))

    pixels = list(img.getdata())
    scale = 255 // (len(chars) - 1) if len(chars) > 1 else 1
    ascii_str = ""
    for i, p in enumerate(pixels):
        idx = min(p // scale, len(chars) - 1)
        ascii_str += chars[idx]
        if (i + 1) % new_w == 0:
            ascii_str += "\n"

    font = _ensure_font(10)
    lines = ascii_str.split("\n")
    line_h = font.getbbox("A")[3] + 2 if hasattr(font, "getbbox") else 12
    out_h = len(lines) * line_h
    out_w = font.getbbox(ascii_str.split("\n")[0])[2] + 20 if hasattr(font, "getbbox") else new_w * 7
    out_img = Image.new("RGB", (out_w, out_h), "black")
    draw = ImageDraw.Draw(out_img)
    draw.text((10, 5), ascii_str, fill="white", font=font)
    out_img.save(output_path)


def edge_lines(input_path: str, output_path: str):
    img = Image.open(input_path).convert("L")
    img = img.filter(ImageFilter.FIND_EDGES)
    img = ImageOps.invert(img)
    img = img.point(lambda p: 255 if p > 30 else 0)
    img.save(output_path)


def mirror(input_path: str, output_path: str):
    img = Image.open(input_path)
    img = ImageOps.mirror(img)
    img.save(output_path)


def pixelate(input_path: str, output_path: str, block_size: int = 16):
    img = Image.open(input_path)
    w, h = img.size
    bw = max(1, w // block_size)
    bh = max(1, h // block_size)
    small = img.resize((bw, bh), Image.NEAREST)
    result = small.resize((w, h), Image.NEAREST)
    result.save(output_path)


def negative(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGB")
    img = ImageOps.invert(img)
    img.save(output_path)


def scanlines(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(0, h, 3):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, 80), width=1)
        draw.line([(0, y + 1), (w, y + 1)], fill=(0, 0, 0, 60), width=1)
    img = Image.alpha_composite(img, overlay)
    img.save(output_path)


def triggered(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (255, 0, 0, 80))
    img = Image.alpha_composite(img, overlay)

    shake = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    shake.paste(img, (10, 10), img)
    shake.paste(img, (5, 15), img)
    shake.paste(img, (15, 5), img)
    result = shake.crop((5, 5, w + 15, h + 15))
    result.save(output_path)


def demotivator(input_path: str, output_path: str, text: str = ""):
    img = Image.open(input_path).convert("RGB")
    photo_w, photo_h = img.size
    max_photo_w = 500
    if photo_w > max_photo_w:
        ratio = max_photo_w / photo_w
        photo_w, photo_h = max_photo_w, int(photo_h * ratio)
    img = img.resize((photo_w, photo_h))

    border = 6
    framed = ImageOps.expand(img, border=border, fill="white")

    margin_top = 30
    margin_bottom = 50
    canvas_w = framed.width + 80
    canvas_h = margin_top + framed.height + margin_bottom + 80

    canvas = Image.new("RGB", (canvas_w, canvas_h), "black")
    canvas.paste(framed, ((canvas_w - framed.width) // 2, margin_top))

    draw = ImageDraw.Draw(canvas)
    font_size = 36
    font = _ensure_font(font_size)

    if text:
        lines = []
        for line in text.split("\\n"):
            wrapped = _wrap_text(draw, line, font, canvas_w - 60)
            lines.extend(wrapped)
        y_text = margin_top + framed.height + 20
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((canvas_w - tw) // 2, y_text), line, fill="white", font=font)
            y_text += bbox[3] - bbox[1] + 4

    canvas.save(output_path)


def _wrap_text(draw, text: str, font, max_width: int):
    if not text:
        return [""]
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


async def _run_ffmpeg(args: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def make_video_circle(input_path: str, output_path: str, max_duration: int = 60):
    code, out, err = await _run_ffmpeg([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", input_path,
    ])
    try:
        dur = float(out.strip())
    except (ValueError, TypeError):
        dur = 0
    duration = min(dur, max_duration)

    await _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "crop=min(iw\\,ih):min(iw\\,ih),format=yuv420p",
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",
        output_path,
    ])
