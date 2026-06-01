"""
services/image_gen.py — Profile card image generator using Pillow
Produces a premium glassmorphism-style PNG card for alert notifications.
"""

from __future__ import annotations
import io
import os
import math
import textwrap
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from utils.helpers import sanitize_username, chat_type_label, format_utc


# ─────────────────────────────────────────────
# Color Palette (Telegram-inspired dark theme)
# ─────────────────────────────────────────────

BG_TOP    = (18, 22, 42)       # Deep navy
BG_BOT    = (28, 12, 48)       # Deep purple
GLASS_BG  = (255, 255, 255, 25)  # Translucent white glass
GLASS_BDR = (255, 255, 255, 60)  # Border glow
ACCENT    = (84, 172, 255)     # Telegram blue
ACCENT2   = (172, 84, 255)     # Purple accent
TEXT_PRI  = (240, 245, 255)    # Primary text
TEXT_SEC  = (140, 160, 200)    # Secondary text
TEXT_DIM  = (90, 110, 150)     # Dimmed text
RED_ALERT = (255, 80, 80)      # For disappeared alerts
GREEN_OK  = (80, 220, 120)     # For new alerts
AVATAR_RING = (84, 172, 255)


CARD_W, CARD_H = 640, 360

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a font, fall back to default."""
    try:
        font_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        font_path = os.path.join(FONTS_DIR, font_name)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    # System fonts fallback
    for path in [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'Bold' if bold else ''}.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    radius: int,
    fill=None,
    outline=None,
    width: int = 1,
) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _gradient_bg(size: tuple[int, int]) -> Image.Image:
    """Create a smooth gradient background."""
    w, h = size
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _create_blurred_circles(size: tuple[int, int]) -> Image.Image:
    """Add soft glowing circles for depth."""
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Left circle — blue glow
    draw.ellipse((-80, -80, 200, 200), fill=(84, 172, 255, 30))
    # Right circle — purple glow
    draw.ellipse((size[0]-180, size[1]-180, size[0]+80, size[1]+80), fill=(172, 84, 255, 30))
    return overlay.filter(ImageFilter.GaussianBlur(radius=40))


def _paste_avatar(card: Image.Image, photo_bytes: Optional[bytes], cx: int, cy: int, r: int) -> None:
    """Paste a circular avatar onto the card at (cx, cy) with radius r."""
    if photo_bytes:
        try:
            av = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
            av = av.resize((r * 2, r * 2), Image.LANCZOS)
            # Circular mask
            mask = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            av.putalpha(mask)
            card.paste(av, (cx - r, cy - r), av)
        except Exception:
            _draw_placeholder_avatar(card, cx, cy, r)
    else:
        _draw_placeholder_avatar(card, cx, cy, r)


def _draw_placeholder_avatar(card: Image.Image, cx: int, cy: int, r: int) -> None:
    draw = ImageDraw.Draw(card)
    # Circle background
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 50, 80))
    # Person silhouette
    head_r = r // 3
    draw.ellipse((cx - head_r, cy - r + 10, cx + head_r, cy - r + 10 + head_r * 2), fill=(100, 130, 190))
    body_y = cy - r + 10 + head_r * 2 + 4
    draw.ellipse((cx - r + 14, body_y, cx + r - 14, cy + r), fill=(100, 130, 190))


def generate_profile_card(
    name: str,
    username: Optional[str],
    chat_id: int,
    keyword: str,
    chat_type: str,
    detected_at: datetime,
    photo_bytes: Optional[bytes] = None,
    alert_type: str = "new",  # "new" or "disappeared"
) -> bytes:
    """
    Generate a premium glassmorphism profile card PNG.
    Returns raw PNG bytes.
    """
    # ── Background ──
    bg = _gradient_bg((CARD_W, CARD_H))
    card = bg.convert("RGBA")

    # ── Glow circles ──
    circles = _create_blurred_circles((CARD_W, CARD_H))
    card.alpha_composite(circles)

    draw = ImageDraw.Draw(card)

    # ── Glass panel ──
    glass_x0, glass_y0 = 20, 20
    glass_x1, glass_y1 = CARD_W - 20, CARD_H - 20
    glass_layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    glass_draw = ImageDraw.Draw(glass_layer)
    glass_draw.rounded_rectangle(
        (glass_x0, glass_y0, glass_x1, glass_y1),
        radius=24,
        fill=GLASS_BG,
        outline=GLASS_BDR,
        width=1,
    )
    card.alpha_composite(glass_layer)

    draw = ImageDraw.Draw(card)

    # ── Top accent bar ──
    accent_color = GREEN_OK if alert_type == "new" else RED_ALERT
    draw.rounded_rectangle((glass_x0 + 1, glass_y0 + 1, glass_x1 - 1, glass_y0 + 6), radius=3, fill=accent_color)

    # ── Avatar ──
    av_cx, av_cy, av_r = 100, 130, 52
    # Avatar ring
    draw.ellipse(
        (av_cx - av_r - 3, av_cy - av_r - 3, av_cx + av_r + 3, av_cy + av_r + 3),
        outline=AVATAR_RING,
        width=3,
    )
    _paste_avatar(card, photo_bytes, av_cx, av_cy, av_r)

    draw = ImageDraw.Draw(card)

    # ── Fonts ──
    fn_title  = _get_font(22, bold=True)
    fn_large  = _get_font(20, bold=True)
    fn_body   = _get_font(15)
    fn_small  = _get_font(13)
    fn_badge  = _get_font(12, bold=True)
    fn_header = _get_font(17, bold=True)

    # ── Header label ──
    if alert_type == "new":
        header_text = "✔ NEW DISCOVERY"
        header_col = GREEN_OK
    else:
        header_text = "💔 DISAPPEARED"
        header_col = RED_ALERT

    draw.text((glass_x0 + 20, glass_y0 + 18), header_text, font=fn_header, fill=header_col)

    # ── Separator line ──
    draw.line((glass_x0 + 20, glass_y0 + 50, glass_x1 - 20, glass_y0 + 50), fill=(255, 255, 255, 30), width=1)

    # ── Name ──
    name_display = name[:32] + ("..." if len(name) > 32 else "")
    draw.text((175, 85), name_display, font=fn_large, fill=TEXT_PRI)

    # ── Username ──
    uname = sanitize_username(username)
    draw.text((175, 115), uname, font=fn_body, fill=ACCENT)

    # ── Chat type badge ──
    type_label = chat_type_label(chat_type)
    badge_x, badge_y = 175, 148
    badge_w = 90
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_w, badge_y + 22),
        radius=8,
        fill=(*ACCENT, 60),
    )
    draw.text((badge_x + 10, badge_y + 4), type_label, font=fn_badge, fill=TEXT_PRI)

    # ── Info rows ──
    row_x = 40
    info_y_start = 205
    row_gap = 30
    label_w = 120

    info_rows = [
        ("Keyword", keyword[:40]),
        ("Chat ID", str(chat_id)),
        ("Detected", format_utc(detected_at)),
    ]

    for i, (label, value) in enumerate(info_rows):
        y = info_y_start + i * row_gap
        # Label
        draw.text((row_x, y), label + ":", font=fn_small, fill=TEXT_DIM)
        # Value
        draw.text((row_x + label_w, y), value, font=fn_small, fill=TEXT_SEC)
        # Divider
        if i < len(info_rows) - 1:
            draw.line(
                (row_x, y + 22, CARD_W - 40, y + 22),
                fill=(255, 255, 255, 15),
                width=1,
            )

    # ── Bottom brand ──
    brand = "TG Monitor • Powered by Telethon"
    draw.text((CARD_W // 2, CARD_H - 30), brand, font=fn_small, fill=TEXT_DIM, anchor="mm")

    # ── Finalize ──
    final = card.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


def generate_placeholder_card(
    name: str,
    alert_type: str = "new",
) -> bytes:
    """
    Quick card with no photo.
    """
    return generate_profile_card(
        name=name,
        username=None,
        chat_id=0,
        keyword="",
        chat_type="channel",
        detected_at=datetime.utcnow(),
        photo_bytes=None,
        alert_type=alert_type,
    )
