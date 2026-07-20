import asyncio
import math
import os
import shutil
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).parent / "fonts"
_FONT_URL = (
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosans/NotoSans-Regular.ttf"
)


def _ensure_font(size: int = 40):
    if _FONT_DIR.exists():
        for f in sorted(_FONT_DIR.glob("*.[tT][tT][fF]")):
            try:
                return ImageFont.truetype(str(f), size)
            except (OSError, IOError):
                continue
    for path in (
        str(Path(__file__).parent.parent.parent / "utils" / "fonts" / "impact.ttf"),
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


async def download_font():
    if _FONT_DIR.exists() and any(_FONT_DIR.glob("*.[tT][tT][fF]")):
        return
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(_FONT_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    path = _FONT_DIR / "NotoSans-Regular.ttf"
                    path.write_bytes(await resp.read())
    except Exception:
        pass


def black_white(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGB")
    img = ImageOps.grayscale(img)
    img.save(output_path)


_ASCII_CHARS = "@%#8&$WM*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^'. "


def _luminance(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def ascii_art(input_path: str, output_path: str, chars: str = ""):
    gradient = chars or _ASCII_CHARS
    if not gradient:
        gradient = _ASCII_CHARS
    img = Image.open(input_path).convert("RGB")
    orig_w, orig_h = img.size

    font = _ensure_font(10)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    cw = max(1, int(tmp.textlength("A", font=font)))
    ch = max(1, tmp.textbbox((0, 0), "Ay", font=font)[3])

    cols = 300
    rows = int(cols * orig_h / orig_w * cw / ch)
    rows = max(1, rows)
    small = img.resize((cols, rows), Image.LANCZOS)
    pixels = list(small.getdata())
    scale = len(gradient) - 1

    out_w = cols * cw + 4
    out_h = rows * ch
    out_img = Image.new("RGB", (out_w, out_h), "black")
    draw = ImageDraw.Draw(out_img)

    for y in range(rows):
        line = ""
        for x in range(cols):
            r, g, b = pixels[y * cols + x]
            lum = int(0.299 * r + 0.587 * g + 0.114 * b)
            line += gradient[min(lum * scale // 255, scale)]
        draw.text((2, y * ch), line, fill="white", font=font)

    pix = out_img.load()
    for py in range(out_h):
        cy = min(py // ch, rows - 1)
        row = [pixels[cy * cols + x] for x in range(cols)]
        for px in range(out_w):
            if pix[px, py] != (0, 0, 0):
                cx = min((px - 2) // cw, cols - 1)
                pix[px, py] = row[cx]

    bbox = out_img.getbbox()
    if bbox:
        out_img = out_img.crop(bbox)

    out_img.save(output_path, quality=85)


def edge_lines(input_path: str, output_path: str):
    import numpy as np
    from math import sin as _sin

    img = Image.open(input_path).convert("L")
    w, h = img.size

    blur_r = max(2, min(w, h) // 100)
    img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))
    arr = np.array(img, dtype=np.float64)

    out = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(out)

    num_lines = max(25, min(70, h // 14))
    step_y = h / num_lines
    max_amp = (step_y / 2.0) * 0.90

    for i in range(num_lines):
        base_y = (i + 0.5) * step_y
        row_idx = int(base_y)
        if row_idx < 0 or row_idx >= h:
            continue
        row_data = arr[row_idx, :]

        intensity = (255.0 - row_data) / 255.0
        intensity = np.clip(intensity, 0.0, 1.0)

        freq = 50.0 / w
        xs = np.arange(0, w, 2, dtype=np.int32)
        wave = np.sin(xs * freq)
        offset = wave * (intensity[xs] * max_amp)
        current_y = np.clip(base_y + offset, 0, h - 1)

        pts = [(int(xs[k]), int(current_y[k])) for k in range(len(xs))]
        draw.line(pts, fill=(0, 0, 0), width=2)

    out.save(output_path)


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
    img = Image.alpha_composite(img, overlay).convert("RGB")
    img.save(output_path)


def triggered(input_path: str, output_path: str):
    img = Image.open(input_path).convert("RGB")
    w, h = img.size

    shake = Image.new("RGB", (w + 50, h + 50), (0, 0, 0))
    shake.paste(img, (20, 20))
    shake.paste(img, (25, 30))
    shake.paste(img, (30, 20))
    shake.paste(img, (15, 35))
    shake.paste(img, (35, 15))
    shake = shake.crop((15, 15, w + 35, h + 35))
    rw, rh = shake.size

    overlay = Image.new("RGB", (rw, rh), (255, 0, 0))
    shake = Image.blend(shake, overlay, 0.35)

    bar_h = max(55, rh // 6)
    draw = ImageDraw.Draw(shake)
    draw.rectangle([(0, rh - bar_h), (rw, rh)], fill=(255, 165, 0))

    fnt = _ensure_font(bar_h - 12)
    txt = "TRIGGERED"
    tw = draw.textbbox((0, 0), txt, font=fnt)[2]
    tx = (rw - tw) // 2
    ty = rh - bar_h + (bar_h - draw.textbbox((0, 0), txt, font=fnt)[3]) // 2

    txt_img = Image.new("RGB", (rw, bar_h), (255, 165, 0))
    tdraw = ImageDraw.Draw(txt_img)
    tdraw.text((tx, ty - (rh - bar_h)), txt, fill=(0, 0, 0), font=fnt)
    txt_img = txt_img.filter(ImageFilter.BoxBlur(3))
    shake.paste(txt_img, (0, rh - bar_h))

    shake.save(output_path)


def _best_font_size(draw: ImageDraw.Draw, text: str, max_w: int, max_h: int, min_size: int = 24, max_size: int = 60):
    for size in range(max_size, min_size - 1, -2):
        font = _ensure_font(size)
        lines = []
        for paragraph in text.split("\\n"):
            lines.extend(_wrap_text(draw, paragraph, font, max_w))
        if not lines:
            return font, lines
        line_h = draw.textbbox((0, 0), "Аy", font=font)[3] + 4
        total_h = len(lines) * line_h
        max_line_w = max(draw.textbbox((0, 0), l, font=font)[2] for l in lines)
        if max_line_w <= max_w and total_h <= max_h:
            return font, lines
    return _ensure_font(min_size), _wrap_text(draw, text, _ensure_font(min_size), max_w)


def demotivator(input_path: str, output_path: str, text: str = ""):
    text = text.upper()
    img = Image.open(input_path).convert("RGB")
    photo_w, photo_h = img.size
    max_photo_w = 700
    if photo_w > max_photo_w:
        ratio = max_photo_w / photo_w
        photo_w, photo_h = max_photo_w, int(photo_h * ratio)
    img = img.resize((photo_w, photo_h))

    border = 8
    framed = ImageOps.expand(img, border=border, fill="white")

    margin_top = 40
    pad_x = 50
    text_margin_bottom = 40
    canvas_w = framed.width + pad_x * 2
    text_area_w = canvas_w - pad_x * 2
    text_area_h = 300
    canvas_h = margin_top + framed.height + text_margin_bottom + text_area_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), "black")
    canvas.paste(framed, ((canvas_w - framed.width) // 2, margin_top))

    draw = ImageDraw.Draw(canvas)
    font, lines = _best_font_size(draw, text, text_area_w, text_area_h)
    if not lines:
        canvas.save(output_path)
        return

    line_h = draw.textbbox((0, 0), "Аy", font=font)[3] + 4
    total_text_h = len(lines) * line_h
    y_text = margin_top + framed.height + text_margin_bottom + (text_area_h - total_text_h) // 2
    for line in lines:
        tw = draw.textbbox((0, 0), line, font=font)[2]
        draw.text(((canvas_w - tw) // 2, y_text), line, fill="white", font=font)
        y_text += line_h

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


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    return p or "ffmpeg"


async def make_video_circle(input_path: str, output_path: str, max_duration: int = 60):
    ffmpeg = _ffmpeg_path()
    code, out, err = await _run_ffmpeg([
        ffmpeg, "-y",
        "-i", input_path,
        "-vf", "scale=384:384:force_original_aspect_ratio=increase,crop=384:384,setsar=1",
        "-pix_fmt", "yuv420p",
        "-t", str(max_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-f", "mp4",
        output_path,
    ])
    if code != 0:
        raise RuntimeError(f"ffmpeg failed (code {code}): {err[:500]}")
