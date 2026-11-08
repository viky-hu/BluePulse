"""PNG share layouts adapted from AIHOT media/{poster,og}.ts (MIT).

Copyright (c) 2026 数字生命卡兹克.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_M


INK = "#0e191b"
ACCENT = "#176b75"
MUTED = "#52666a"
PAPER = "#f5f6f5"
CHINA = timezone(timedelta(hours=8))


@lru_cache(maxsize=32)
def _font(size, bold=False):
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    configured = os.environ.get("BLUEPULSE_SHARE_FONT")
    candidates = (
        configured,
        windows / ("msyhbd.ttc" if bold else "msyh.ttc"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(str(candidate), size)
    raise ValueError("share_font_unavailable")


def _clamp(text, size):
    text = " ".join((text or "").split())
    return text if len(text) <= size else text[:size - 1] + "…"


def _wrap(text, font, width):
    """Match the original poster's character wrapping for CJK and word wrapping for Latin."""
    import re

    lines, line = [], ""
    for word in re.findall(r"[\u2e80-\u9fff]|[^\s\u2e80-\u9fff]+|\s+", text):
        if line and font.getlength(line + word) > width:
            lines.append(line.rstrip())
            line = ""
        if not line and word.isspace():
            continue
        if font.getlength(word) > width:
            for character in word:
                if line and font.getlength(line + character) > width:
                    lines.append(line)
                    line = ""
                line += character
        else:
            line += word
    return "\n".join([*lines, line.rstrip()])


def _beijing_date(article):
    if article.published_date:
        return article.published_date.isoformat()
    source_time = article.published_at or article.first_seen_at
    if source_time.tzinfo is None:
        source_time = source_time.replace(tzinfo=timezone.utc)
    return source_time.astimezone(CHINA).date().isoformat()


def render_share(article, mode, origin, selected):
    return _render(
        mode, origin, article.id, article.zh_title or article.source_title, article.zh_summary,
        article.source.name, _beijing_date(article), article.importance_score if selected else None,
    )


@lru_cache(maxsize=64)
def _render(mode, origin, article_id, title, summary, source, date, score):
    poster = mode == "poster"
    width, height = (1080, 1440) if poster else (1200, 630)
    canvas = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(canvas)
    margin = 88 if poster else 68
    draw.rectangle((0, 0, width, 9), fill=ACCENT)
    draw.text((margin, 76 if poster else 45), "BLUE PULSE", font=_font(48 if poster else 39, True), fill=INK)
    draw.text((width - margin, 96 if poster else 60), date, anchor="ra", font=_font(25), fill=MUTED)
    label_y = 220 if poster else 125
    draw.ellipse((margin, label_y + 11, margin + 12, label_y + 23), fill=ACCENT)
    label = "警务科技情报" if score is None else f"警务科技情报  ·  精选 {score} 分"
    draw.text((margin + 26, label_y), label, font=_font(29, True), fill=ACCENT)
    title = _clamp(title, 72 if poster else 46)
    title_size = (58 if len(title) > 48 else 66 if len(title) > 30 else 76) if poster else 52
    title_font = _font(title_size, True)
    title_y = label_y + 60
    title_lines = _wrap(title, title_font, width - 2 * margin)
    draw.multiline_text((margin, title_y), title_lines, font=title_font, fill=INK, spacing=12)
    _, _, _, title_end = draw.multiline_textbbox((margin, title_y), title_lines, font=title_font, spacing=12)
    if summary:
        text_font = _font(34 if poster else 27)
        summary = _clamp(summary, (120 if len(title) > 48 else 150) if poster else 80)
        draw.multiline_text((margin, title_end + 27), _wrap(summary, text_font, width - 2 * margin),
                            font=text_font, fill=MUTED, spacing=12)
    source_y = 976 if poster else 544
    draw.line((margin, source_y - 22, width - margin, source_y - 22), fill="#c5d6d5", width=2)
    draw.text((margin, source_y), "来源  " + _clamp(source, 35), font=_font(26), fill=MUTED)
    if poster:
        _qr_panel(canvas, draw, origin, article_id, margin)
    data = BytesIO()
    canvas.save(data, "PNG", optimize=True)
    return data.getvalue()


def _qr_panel(canvas, draw, origin, article_id, margin):
    if not origin:
        raise ValueError("share_origin_unconfigured")
    qr = QRCode(error_correction=ERROR_CORRECT_M, box_size=5, border=4)
    qr.add_data(f"{origin}/articles/{article_id}")
    qr.make(fit=True)
    code = qr.make_image(fill_color=INK, back_color="#ffffff").convert("RGB")
    code.thumbnail((215, 215), Image.Resampling.NEAREST)
    draw.rounded_rectangle((margin, 1050, 1080 - margin, 1330), radius=28, fill="#ffffff")
    canvas.paste(code, (margin + 36, 1080))
    draw.text((margin + 286, 1120), "长按识别二维码", font=_font(36, True), fill=INK)
    draw.text((margin + 286, 1195), "阅读公开报道及原文入口", font=_font(28), fill=MUTED)
