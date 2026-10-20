"""Generate a B50 poster locally as PNG; score records are never uploaded."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any
import os

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .network import make_session, SYSTEM_PROXY
from .rating import rating_tier, dx_star_count

WIDTH = 1600
MARGIN = 36
CARD_W = 294
CARD_H = 132
GAP_X = 14
GAP_Y = 13
COLS = 5

TIER_COLORS = {
    "rainbow": (215, 91, 178), "platinum": (132, 146, 171), "gold": (181, 138, 19),
    "silver": (125, 137, 154), "bronze": (169, 106, 64), "purple": (137, 97, 197),
    "red": (206, 82, 104), "yellow": (169, 139, 22), "green": (55, 141, 87),
    "blue": (71, 127, 191), "white": (112, 109, 124),
}
DIFF_COLORS = {
    "BASIC": (100, 191, 99), "ADVANCED": (235, 184, 61), "EXPERT": (230, 91, 112),
    "MASTER": (153, 92, 221), "RE:MASTER": (149, 105, 235), "UTAGE": (228, 112, 163),
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if os.name == "nt":
        candidates += [
            r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\YuGothB.ttc" if bold else r"C:\Windows\Fonts\YuGothM.ttc",
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        ]
    candidates += [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _cover_url(record: dict[str, Any]) -> str | None:
    raw = str(record.get("cover_id") or record.get("song_id") or "").strip()
    if not raw.isdigit():
        return None
    return "https://meta.salt.realtvop.top/covers/{}.png".format(raw.zfill(6)[-6:])


def _cover_key(record: dict[str, Any]) -> str:
    return str(record.get("song_id") or record.get("cover_id") or "").strip()


def _fetch_cover(record: dict[str, Any], network_mode: str, proxy_url: str | None) -> tuple[str, bytes] | None:
    url = _cover_url(record)
    key = _cover_key(record)
    if not url or not key:
        return None
    cache_dir = Path(__file__).resolve().parents[1] / "data" / "cover_cache"
    cache_path = cache_dir / (key + ".png")
    try:
        if cache_path.exists():
            raw = cache_path.read_bytes()
            with Image.open(BytesIO(raw)) as im:
                im.verify()
            return key, raw
    except (OSError, ValueError):
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        with make_session(network_mode, proxy_url) as session:
            response = session.get(url, timeout=(1.4, 2.6))
            response.raise_for_status()
            if "image" not in response.headers.get("content-type", "").lower():
                return None
            raw = response.content
            with Image.open(BytesIO(raw)) as im:
                im.verify()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
            return key, raw
    except (requests.RequestException, OSError, ValueError):
        return None


def _load_covers(records: list[dict[str, Any]], network_mode: str, proxy_url: str | None) -> dict[str, Image.Image]:
    found: dict[str, Image.Image] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(_fetch_cover, rec, network_mode, proxy_url) for rec in records[:50]]
        for future in as_completed(futures):
            try:
                result = future.result()
                if not result:
                    continue
                key, raw = result
                with Image.open(BytesIO(raw)) as im:
                    found[key] = im.convert("RGB").copy()
            except Exception:
                continue
    return found


def _wrap_song_title(title: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> tuple[str, str]:
    """Wrap titles to two lines without orphaning the final character."""
    words = title.split()
    line1 = ""
    line2 = ""
    omitted = False
    if len(words) > 1:
        for word in words:
            candidate = (line1 + " " + word).strip()
            if not line2 and draw.textlength(candidate, font=font) <= max_width:
                line1 = candidate
                continue
            candidate2 = (line2 + " " + word).strip()
            if draw.textlength(candidate2, font=font) <= max_width:
                line2 = candidate2
            else:
                omitted = True
                break
    else:
        for char in title:
            if not line2 and draw.textlength(line1 + char, font=font) <= max_width:
                line1 += char
            elif draw.textlength(line2 + char, font=font) <= max_width:
                line2 += char
            else:
                omitted = True
                break
    if not line1:
        line1, line2 = title[:1], title[1:]
        omitted = True
    if omitted:
        if not line2:
            line2 = "…"
        else:
            while line2 and draw.textlength(line2 + "…", font=font) > max_width:
                line2 = line2[:-1]
            line2 += "…"
    return line1, line2


def _fit_cover(draw: ImageDraw.ImageDraw, canvas: Image.Image, img: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    crop = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=9, fill=255)
    canvas.paste(crop, (x, y), mask)


def _draw_tier_value(draw: ImageDraw.ImageDraw, canvas: Image.Image, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, tier: str) -> None:
    x, y = xy
    if tier != "rainbow":
        draw.text((x, y), text, font=font, fill=TIER_COLORS.get(tier, TIER_COLORS["white"]), stroke_width=1, stroke_fill=(255, 255, 255))
        return
    # Rainbow text mask; no third-party image or font resource is required.
    bbox = draw.textbbox((x, y), text, font=font, stroke_width=1)
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=font, fill=255, stroke_width=1, stroke_fill=255)
    grad = Image.new("RGB", canvas.size, (255, 255, 255))
    gd = ImageDraw.Draw(grad)
    colors = [(236, 73, 101), (222, 137, 51), (38, 163, 119), (60, 131, 228), (160, 76, 210), (239, 96, 179)]
    left, top, right, bottom = bbox
    span = max(1, right - left)
    for px in range(max(0, left), min(canvas.width, right)):
        t = (px - left) / span * (len(colors) - 1)
        j = min(len(colors) - 2, int(t))
        frac = t - j
        c0, c1 = colors[j], colors[j + 1]
        color = tuple(int(c0[k] * (1 - frac) + c1[k] * frac) for k in range(3))
        gd.line((px, max(0, top), px, min(canvas.height, bottom)), fill=color)
    canvas.paste(grad, (0, 0), mask)


def generate_b50_png(
    records: list[dict[str, Any]],
    total_rating: int,
    mode_label: str,
    source_label: str,
    *,
    network_mode: str = SYSTEM_PROXY,
    proxy_url: str | None = None,
    fetch_covers: bool = True,
) -> bytes:
    """Return a 5-column B50 PNG. Only chart-cover IDs may be requested, never scores."""
    records = list(records[:50])
    rows = max(1, (len(records) + COLS - 1) // COLS)
    header_h = 218
    height = header_h + rows * (CARD_H + GAP_Y) + 48
    canvas = Image.new("RGB", (WIDTH, height), (245, 239, 255))
    px = canvas.load()
    gd = ImageDraw.Draw(canvas)
    for y in range(height):
        t = y / max(1, height - 1)
        top = (227, 249, 255)
        bottom = (255, 235, 244)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        gd.line((0, y, WIDTH - 1, y), fill=color)
    draw = ImageDraw.Draw(canvas)
    draw = ImageDraw.Draw(canvas)
    f_title = _font(39, True)
    f_sub = _font(18, False)
    f_rating_label = _font(20, True)
    f_rating = _font(52, True)
    f_label = _font(15, True)
    f_song = _font(17, True)
    f_meta = _font(14, False)
    f_value = _font(16, True)

    draw.rounded_rectangle((MARGIN, 24, WIDTH - MARGIN, 110), radius=22, fill=(255, 255, 255), outline=(255, 255, 255), width=2)
    draw.text((MARGIN + 24, 36), "ASTRODX B50", font=f_title, fill=(61, 49, 92))
    draw.text((MARGIN + 27, 82), "RHYTHM GAME SCORE ANALYZER  ·  {}".format(source_label), font=f_sub, fill=(131, 117, 163))

    tier, tier_label = rating_tier(total_rating)
    draw.rounded_rectangle((MARGIN, 124, WIDTH - MARGIN, 202), radius=19, fill=(128, 100, 222))
    draw.text((MARGIN + 22, 145), "DX RATING", font=f_rating_label, fill=(255, 255, 255))
    draw.text((MARGIN + 22, 171), "{}  ·  {} CHARTS".format(mode_label, len(records)), font=f_meta, fill=(244, 238, 255))
    _draw_tier_value(draw, canvas, (WIDTH - MARGIN - 315, 129), "{:,}".format(int(total_rating)), f_rating, tier)
    draw.text((WIDTH - MARGIN - 24, 177), tier_label, font=f_meta, fill=(255, 255, 255), anchor="ra")

    covers: dict[str, Image.Image] = {}
    if fetch_covers and records:
        covers = _load_covers(records, network_mode, proxy_url)

    for i, rec in enumerate(records):
        col, row = i % COLS, i // COLS
        x = MARGIN + col * (CARD_W + GAP_X)
        y = header_h + row * (CARD_H + GAP_Y)
        diff = str(rec.get("difficulty") or "").upper().replace("REMASTER", "RE:MASTER")
        accent = DIFF_COLORS.get(diff, (145, 121, 190))
        draw.rounded_rectangle((x, y, x + CARD_W, y + CARD_H), radius=15, fill=(255, 255, 255), outline=(255, 255, 255), width=2)
        draw.rounded_rectangle((x, y, x + 7, y + CARD_H), radius=3, fill=accent)
        cover_key = str(rec.get("song_id") or rec.get("cover_id") or "")
        cover = covers.get(cover_key)
        img_x, img_y = x + 11, y + 11
        if cover:
            _fit_cover(draw, canvas, cover, (img_x, img_y, 82, 82))
        else:
            draw.rounded_rectangle((img_x, img_y, img_x + 82, img_y + 82), radius=10, fill=(238, 231, 250))
            draw.text((img_x + 41, img_y + 40), "♪", font=_font(37, True), fill=accent, anchor="mm")
        text_x = x + 104
        title = str(rec.get("title") or "Unknown song")
        # At most two lines; wrap at spaces where possible and avoid one-letter orphans.
        line1, line2 = _wrap_song_title(title, draw, f_song, CARD_W - 118)
        draw.text((text_x, y + 11), line1, font=f_song, fill=(65, 51, 96))
        if line2:
            draw.text((text_x, y + 31), line2, font=f_meta, fill=(78, 67, 104))
        draw.text((text_x, y + 54), "{}  ·  {}".format(diff, rec.get("song_type") or "DX"), font=f_label, fill=accent)
        try:
            achievement = float(rec.get("achievement") or 0)
        except (TypeError, ValueError):
            achievement = 0
        draw.text((text_x, y + 75), "{:.4f}%".format(achievement), font=f_value, fill=(137, 78, 200))
        detail = "DS {}   DX {}".format(rec.get("constant", "—"), int(rec.get("dx_score") or 0))
        draw.text((x + 12, y + 103), detail, font=f_meta, fill=(126, 116, 148))
        stars = dx_star_count(rec.get("dx_score", 0), rec.get("notes") or rec.get("total_notes"))
        if stars:
            draw.text((x + CARD_W - 82, y + 78), "✦" * stars, font=_font(15, True), fill=(232, 169, 40), anchor="ra")
        draw.text((x + CARD_W - 12, y + 103), "R {}".format(int(rec.get("rating") or 0)), font=f_label, fill=(146, 83, 198), anchor="ra")

    return_io = BytesIO()
    canvas.save(return_io, format="PNG", optimize=True)
    return return_io.getvalue()
