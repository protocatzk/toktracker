"""
Serverseitiges Rendering von Chart-Bildern für Telegram.

Die Karte ist eine komplett eckige, schwarze Fläche mit weißen Kennzahlen und
grüner Chart-Linie. Kein Alpha, keine runden Ecken: Das Bild bleibt bei
Telegram unabhängig von der Kompression identisch.

Das Rendering ist CPU-only (Pillow) und wird über einen LRU-Cache sowie einen
Telegram-file_id-Cache im Bot extrem günstig gehalten.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Optional, Tuple

from shared.chart_views import ChartViewSeries, load_chart_view, normalize_view
from shared.config import BASE_DIR
from shared.widget_chart import (
    ChartSeries,
    chart_caption,
    format_coins,
    format_eur,
    load_chart_series,
)

IMAGE_WIDTH = 800
IMAGE_HEIGHT = 400
_SUPERSAMPLE = 2
_CACHE_TTL_SECONDS = 600.0
_CACHE_MAX_ENTRIES = 96

# Brand-Palette (eckige schwarze Karte)
_BG = (0, 0, 0)
_TEXT = (244, 248, 252)
_MUTED = (157, 169, 183)
_ACCENT = (63, 185, 80)
_GRID = (36, 42, 50)
_AREA = (20, 42, 25)

# Admin-Panel-Palette (Dashboard/Chart.js) für die zusätzlichen Ansichten.
_PALETTE = (
    (88, 166, 255),
    (63, 185, 80),
    (210, 153, 34),
    (188, 140, 255),
    (247, 120, 186),
    (57, 197, 207),
    (255, 166, 87),
    (255, 123, 114),
    (126, 231, 135),
    (121, 192, 255),
)
_PRIMARY = (88, 166, 255)
_SECONDARY = (63, 185, 80)
_GOLD = (210, 153, 34)
_PURPLE = (188, 140, 255)

_FONT_INTER = os.path.join(BASE_DIR, "static", "fonts", "inter-variable.ttf")
_FONT_MONO = os.path.join(BASE_DIR, "static", "fonts", "jetbrains-mono-variable.ttf")


class ChartImageError(RuntimeError):
    """Rendering nicht möglich (z. B. Pillow/Font fehlt)."""


@dataclass(frozen=True)
class ChartImage:
    png: bytes
    digest: str
    width: int
    height: int
    caption: str
    period: str
    metric: str
    total: float
    peak: float
    points: int
    streamer_id: Optional[int] = None
    streamer_name: str = ""
    group_id: Optional[int] = None
    group_name: str = ""
    view: str = "timeline"
    view_label: str = "VERLAUF"


_image_cache: "OrderedDict[str, Tuple[float, ChartImage]]" = OrderedDict()
_image_cache_lock = threading.Lock()


def clear_chart_image_cache() -> None:
    with _image_cache_lock:
        _image_cache.clear()


@lru_cache(maxsize=24)
def _font(mono: bool, size: int, weight: int):
    try:
        from PIL import ImageFont
    except ImportError as exc:  # pragma: no cover - Pillow ist Pflicht
        raise ChartImageError("Pillow ist nicht installiert.") from exc

    path = _FONT_MONO if mono else _FONT_INTER
    try:
        font = ImageFont.truetype(path, size)
        if weight:
            try:
                # Inter hat die Achsen (opsz, wght), JetBrains Mono nur (wght).
                font.set_variation_by_axes([weight] if mono else [14, weight])
            except Exception:
                pass
        return font
    except Exception as exc:
        raise ChartImageError(f"Font konnte nicht geladen werden: {path}") from exc


def _render_png(series: ChartSeries) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover
        raise ChartImageError("Pillow ist nicht installiert.") from exc

    scale = _SUPERSAMPLE
    width, height = IMAGE_WIDTH * scale, IMAGE_HEIGHT * scale
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    title = series.title_text
    total_text = series.total_text
    peak_text = series.peak_text
    count = len(series.values)

    font_title = _font(False, 34, 500)
    font_big = _font(False, 88, 700)
    font_muted = _font(False, 26, 500)
    font_axis = _font(False, 28, 500)
    font_brand = _font(True, 30, 700)

    pad_x = 32 * scale
    # Grüner Brand-Stripe am linken Rand + Wortmarke.
    draw.rectangle((0, 0, 4 * scale, height), fill=_ACCENT)
    draw.text(
        (pad_x, 14 * scale),
        "// TT-INTELLIGENCE",
        font=font_brand,
        fill=_ACCENT,
    )
    draw.text((pad_x, 46 * scale), title, font=font_title, fill=_MUTED)
    draw.text((pad_x, 68 * scale), total_text, font=font_big, fill=_TEXT)
    if count:
        info = f"PEAK {peak_text} · {count} PUNKTE"
    else:
        info = "Keine Daten im Zeitraum."
    draw.text((pad_x, 126 * scale), info, font=font_muted, fill=_MUTED)

    x0, x1 = 64 * scale, width - 32 * scale
    y0, y1 = 166 * scale, 350 * scale

    for step in range(3):
        y = y0 + (y1 - y0) * step / 2
        draw.line([(x0, y), (x1, y)], fill=_GRID, width=scale)

    if count:
        peak = series.peak or 1.0
        points = []
        for index, value in enumerate(series.values):
            px = x0 if count == 1 else x0 + (x1 - x0) * index / (count - 1)
            py = y1 - (float(value) / peak) * (y1 - y0)
            points.append((px, py))

        if count > 1:
            draw.polygon(points + [(x1, y1), (x0, y1)], fill=_AREA)
        if count > 1:
            draw.line(points, fill=_ACCENT, width=3 * scale, joint="curve")
        dot_r = 4 * scale
        cx, cy = points[-1]
        draw.ellipse(
            [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
            fill=_ACCENT,
        )

        # Vier Zeitlabels; bei sehr kurzen Serien entsprechend weniger.
        tick_indexes = sorted(
            {
                0,
                round((count - 1) / 3),
                round((count - 1) * 2 / 3),
                count - 1,
            }
        )
        last_right = -10**9
        for index in tick_indexes:
            label = series.labels[index] if index < len(series.labels) else ""
            if not label:
                continue
            # Bei 24h/Today reicht die Uhrzeit; Datum steht im Titel.
            if ":" in label:
                label = label[-5:]
            text_width = draw.textlength(label, font=font_axis)
            px = x0 if count == 1 else x0 + (x1 - x0) * index / (count - 1)
            if index == 0:
                tx = px
            elif index == count - 1:
                tx = px - text_width
            else:
                tx = px - text_width / 2
            if tx < last_right + 8 * scale:
                continue
            draw.text((tx, 368 * scale), label, font=font_axis, fill=_MUTED)
            last_right = tx + text_width

    resample = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _shorten_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _draw_view_header(
    draw: Any,
    series: ChartViewSeries,
    fonts: Tuple[Any, Any, Any, Any, Any],
) -> None:
    """Zeichnet Brand-Stripe, Titel, Summe und Infozeile der Zusatz-Charts."""
    brand_font, title_font, big_font, muted_font, _ = fonts
    scale = _SUPERSAMPLE
    height = IMAGE_HEIGHT * scale
    pad_x = 32 * scale
    draw.rectangle((0, 0, 4 * scale, height), fill=_ACCENT)
    draw.text((pad_x, 14 * scale), "// TT-INTELLIGENCE", font=brand_font, fill=_ACCENT)
    draw.text((pad_x, 46 * scale), series.title_text, font=title_font, fill=_MUTED)
    draw.text((pad_x, 68 * scale), series.total_text, font=big_font, fill=_TEXT)
    info = (
        f"{series.subtitle} · PEAK {series.peak_text}"
        if series.values and series.subtitle
        else (f"PEAK {series.peak_text}" if series.values else "Keine Daten im Zeitraum.")
    )
    draw.text((pad_x, 126 * scale), info, font=muted_font, fill=_MUTED)


def _render_hbar_png(series: ChartViewSeries) -> bytes:
    from PIL import Image, ImageDraw

    scale = _SUPERSAMPLE
    width, height = IMAGE_WIDTH * scale, IMAGE_HEIGHT * scale
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    font_brand = _font(True, 30, 700)
    font_title = _font(False, 34, 500)
    font_big = _font(False, 88, 700)
    font_muted = _font(False, 26, 500)
    font_axis = _font(False, 28, 500)
    font_value = _font(True, 24, 500)

    _draw_view_header(
        draw, series, (font_brand, font_title, font_big, font_muted, font_axis)
    )

    if not series.values:
        resample = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    x0 = 212 * scale
    x1 = width - 32 * scale
    y0, y1 = 170 * scale, 352 * scale
    row_h = (y1 - y0) / len(series.values)
    bar_h = min(row_h * 0.5, 18 * scale)
    value_reserve = 190 * scale
    bar_max = max(x1 - x0 - value_reserve, 20 * scale)
    peak = series.peak or 1.0
    color = _PRIMARY if series.view == "streamers" else _SECONDARY

    for index, label in enumerate(series.labels):
        cy = y0 + row_h * (index + 0.5)
        draw.text(
            (x0 - 12 * scale, cy),
            _shorten_text(label, 22),
            font=font_axis,
            fill=_MUTED,
            anchor="rm",
        )
        value = float(series.values[index])
        bar_w = max(2 * scale, (value / peak) * bar_max)
        draw.rectangle(
            (x0, cy - bar_h / 2, x0 + bar_w, cy + bar_h / 2),
            fill=color,
        )
        value_text = (
            f"€ {format_eur(value)}" if series.metric == "eur" else format_coins(value)
        )
        draw.text(
            (x1, cy),
            value_text,
            font=font_value,
            fill=_TEXT,
            anchor="rm",
        )

    resample = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_vbar_png(series: ChartViewSeries) -> bytes:
    from PIL import Image, ImageDraw

    scale = _SUPERSAMPLE
    width, height = IMAGE_WIDTH * scale, IMAGE_HEIGHT * scale
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    font_brand = _font(True, 30, 700)
    font_title = _font(False, 34, 500)
    font_big = _font(False, 88, 700)
    font_muted = _font(False, 26, 500)
    font_axis = _font(False, 24, 500)

    _draw_view_header(
        draw, series, (font_brand, font_title, font_big, font_muted, font_axis)
    )

    x0, x1 = 64 * scale, width - 32 * scale
    y0, y1 = 170 * scale, 348 * scale
    for step in range(3):
        y = y0 + (y1 - y0) * step / 2
        draw.line([(x0, y), (x1, y)], fill=_GRID, width=scale)

    count = len(series.values)
    if count:
        peak = series.peak or 1.0
        slot = (x1 - x0) / count
        bar_w = slot * 0.62
        for index, value in enumerate(series.values):
            bar_h = (float(value) / peak) * (y1 - y0)
            bx = x0 + slot * index + (slot - bar_w) / 2
            color = _GOLD if index == series.highlight else _PURPLE
            draw.rectangle(
                (bx, y1 - bar_h, bx + bar_w, y1),
                fill=color,
            )

        last_right = -10**9
        step = max(1, count // 8)
        for index in list(range(0, count, step)) + [count - 1]:
            label = series.labels[index] if index < len(series.labels) else ""
            if not label:
                continue
            text_width = draw.textlength(label, font=font_axis)
            px = x0 + slot * (index + 0.5)
            tx = px - text_width / 2
            if tx < last_right + 8 * scale:
                continue
            draw.text((tx, 366 * scale), label, font=font_axis, fill=_MUTED)
            last_right = tx + text_width

    resample = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_donut_png(series: ChartViewSeries) -> bytes:
    from PIL import Image, ImageDraw

    scale = _SUPERSAMPLE
    width, height = IMAGE_WIDTH * scale, IMAGE_HEIGHT * scale
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    font_brand = _font(True, 30, 700)
    font_title = _font(False, 34, 500)
    font_big = _font(False, 88, 700)
    font_muted = _font(False, 26, 500)
    font_legend = _font(False, 24, 500)
    font_pct = _font(True, 22, 500)

    _draw_view_header(
        draw, series, (font_brand, font_title, font_big, font_muted, font_legend)
    )

    total = sum(series.values)
    cx, cy = 238 * scale, 262 * scale
    radius = 82 * scale
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)

    if total > 0:
        start = -90.0
        for index, value in enumerate(series.values):
            extent = 360.0 * float(value) / total
            color = _PALETTE[index % len(_PALETTE)]
            draw.pieslice(bbox, start, start + extent, fill=color)
            start += extent
        inner = int(radius * 0.58)
        draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=_BG)

    lx = 404 * scale
    ly0, ly1 = 176 * scale, 348 * scale
    count = len(series.values)
    if count:
        row_h = (ly1 - ly0) / count
        for index, label in enumerate(series.labels):
            value = float(series.values[index])
            pct = (value / total * 100.0) if total > 0 else 0.0
            color = _PALETTE[index % len(_PALETTE)]
            cy_row = ly0 + row_h * (index + 0.5)
            box = 13 * scale
            draw.rectangle(
                (lx, cy_row - box / 2, lx + box, cy_row + box / 2),
                fill=color,
            )
            draw.text(
                (lx + 22 * scale, cy_row),
                _shorten_text(label, 18),
                font=font_legend,
                fill=_MUTED,
                anchor="lm",
            )
            draw.text(
                (width - 32 * scale, cy_row),
                f"{pct:.0f}%",
                font=font_pct,
                fill=_TEXT,
                anchor="rm",
            )

    resample = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_view_png(series: ChartViewSeries) -> bytes:
    if series.kind == "vbar":
        return _render_vbar_png(series)
    if series.kind == "donut":
        return _render_donut_png(series)
    return _render_hbar_png(series)


def _view_fingerprint(series: ChartViewSeries) -> str:
    payload = json.dumps(
        [
            series.view,
            series.period,
            series.metric,
            series.streamer_id or 0,
            series.group_id or 0,
            series.group_name,
            series.labels,
            series.values,
            round(series.total, 4),
            round(series.peak, 4),
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fingerprint(series: ChartSeries) -> str:
    payload = json.dumps(
        [
            series.period,
            series.metric,
            series.streamer_id or 0,
            series.group_id or 0,
            series.group_name,
            series.values,
            round(series.total, 4),
            round(series.peak, 4),
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_chart_image(
    period: str = "24h",
    metric: str = "eur",
    streamer_id: Optional[int] = None,
    streamer_name: str = "",
    force_refresh: bool = False,
    view: str = "timeline",
    group_id: Optional[int] = None,
    group_name: str = "",
) -> ChartImage:
    """
    Liefert ein gecachtes PNG für die Chart-Daten.

    Der Daten-Cache liegt in ``get_chart_timeline`` (Zeitverlauf) bzw.
    ``get_analytics_data`` (Zusatz-Ansichten); hier wird zusätzlich das fertige
    PNG per Inhalts-Fingerprint gecacht. Bei unveränderten Daten kostet ein
    weiterer Aufruf praktisch nichts.
    """
    norm_view = normalize_view(view)
    if norm_view != "timeline":
        return _build_chart_view_image(
            norm_view,
            period,
            metric,
            streamer_id,
            streamer_name,
            force_refresh,
            group_id,
            group_name,
        )

    series = load_chart_series(
        period,
        metric,
        streamer_id,
        streamer_name,
        force_refresh,
        group_id,
        group_name,
    )
    key = _fingerprint(series)
    now = time.monotonic()

    with _image_cache_lock:
        cached = _image_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            _image_cache.move_to_end(key)
            return cached[1]

        png = _render_png(series)
        image = ChartImage(
            png=png,
            digest=hashlib.sha256(png).hexdigest(),
            width=IMAGE_WIDTH,
            height=IMAGE_HEIGHT,
            caption=chart_caption(series),
            period=series.period,
            metric=series.metric,
            total=series.total,
            peak=series.peak,
            points=len(series.values),
            streamer_id=series.streamer_id,
            streamer_name=series.streamer_name,
            group_id=series.group_id,
            group_name=series.group_name,
        )
        _image_cache[key] = (now, image)
        while len(_image_cache) > _CACHE_MAX_ENTRIES:
            _image_cache.popitem(last=False)
        return image


def _build_chart_view_image(
    view: str,
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
    force_refresh: bool,
    group_id: Optional[int] = None,
    group_name: str = "",
) -> ChartImage:
    """Rendert und cached die zusätzlichen Admin-Panel-Ansichten als PNG."""
    series = load_chart_view(
        view,
        period,
        metric,
        streamer_id,
        streamer_name,
        force_refresh,
        group_id,
        group_name,
    )
    key = _view_fingerprint(series)
    now = time.monotonic()

    with _image_cache_lock:
        cached = _image_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            _image_cache.move_to_end(key)
            return cached[1]

        png = _render_view_png(series)
        image = ChartImage(
            png=png,
            digest=hashlib.sha256(png).hexdigest(),
            width=IMAGE_WIDTH,
            height=IMAGE_HEIGHT,
            caption=series.caption,
            period=series.period,
            metric=series.metric,
            total=series.total,
            peak=series.peak,
            points=len(series.values),
            streamer_id=series.streamer_id,
            streamer_name=series.streamer_name,
            group_id=series.group_id,
            group_name=series.group_name,
            view=series.view,
            view_label=series.view_label,
        )
        _image_cache[key] = (now, image)
        while len(_image_cache) > _CACHE_MAX_ENTRIES:
            _image_cache.popitem(last=False)
        return image
