"""
Serverseitiges Rendering von Chart-Bildern für Telegram.

Die Karte ist bewusst als halbtransparentes „Scrim“ angelegt: Sie verschmilzt
mit dem Chat-Hintergrund, wenn der Client Alpha unterstützt, und fällt bei
Telegram-Flattening auf eine normale dunkle Karte zurück. Schrift bleibt weiß
und damit in Light- wie Dark-Theme lesbar.

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

from shared.config import BASE_DIR
from shared.widget_chart import ChartSeries, chart_caption, load_chart_series

IMAGE_WIDTH = 800
IMAGE_HEIGHT = 400
_SUPERSAMPLE = 2
_CACHE_TTL_SECONDS = 600.0
_CACHE_MAX_ENTRIES = 96

# Brand-Palette (dark industrial)
_SCRIM = (16, 21, 28, 188)
_TEXT = (244, 248, 252)
_MUTED = (157, 169, 183)
_ACCENT = (63, 185, 80)
_GRID = (255, 255, 255, 30)
_AREA = (63, 185, 80, 38)

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
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    # Halbtransparente Karte; bei Alpha-Verlust bleibt eine dunkle Karte.
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=20 * scale,
        fill=_SCRIM,
    )

    title = series.title_text
    total_text = series.total_text
    peak_text = series.peak_text
    count = len(series.values)

    font_title = _font(False, 34, 500)
    font_big = _font(False, 88, 700)
    font_muted = _font(False, 26, 500)
    font_axis = _font(False, 28, 500)

    pad_x = 32 * scale
    draw.text((pad_x, 18 * scale), title, font=font_title, fill=_MUTED)
    draw.text((pad_x, 36 * scale), total_text, font=font_big, fill=_TEXT)
    if count:
        info = f"PEAK {peak_text} · {count} PUNKTE"
    else:
        info = "Keine Daten im Zeitraum."
    draw.text((pad_x, 96 * scale), info, font=font_muted, fill=_MUTED)

    x0, x1 = 64 * scale, width - 32 * scale
    y0, y1 = 138 * scale, 338 * scale

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
            draw.text((tx, 356 * scale), label, font=font_axis, fill=_MUTED)
            last_right = tx + text_width

    resample = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT), resample)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _fingerprint(series: ChartSeries) -> str:
    payload = json.dumps(
        [
            series.period,
            series.metric,
            series.streamer_id or 0,
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
) -> ChartImage:
    """
    Liefert ein gecachtes PNG für die Chart-Daten.

    Der Daten-Cache liegt in ``get_chart_timeline``; hier wird zusätzlich das
    fertige PNG per Inhalts-Fingerprint gecacht. Bei unveränderten Daten
    kostet ein weiterer Aufruf praktisch nichts.
    """
    series = load_chart_series(period, metric, streamer_id, streamer_name, force_refresh)
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
        )
        _image_cache[key] = (now, image)
        while len(_image_cache) > _CACHE_MAX_ENTRIES:
            _image_cache.popitem(last=False)
        return image
