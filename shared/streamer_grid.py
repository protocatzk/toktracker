"""
Kompakte Streamer-Grid-Kollage für Telegram.

Im Gegensatz zu den Chart-Kacheln zeigt dieses Modul **alle Streamer** als
kleine Karten in einem einzigen PNG. Jede Karte enthält Rang, Username,
Live-Status, Netto-Umsatz, Coins und Gift-Events.

Die Daten kommen aus ``shared.db.get_analytics_data`` und damit aus denselben
Aggregaten wie Dashboard und Charts.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Sequence, Tuple

from shared.chart_image import ChartImageError, _font
from shared.widget_chart import (
    METRIC_LABELS,
    PERIOD_LABELS,
    format_coins,
    format_eur,
    normalize_metric,
    normalize_period,
)

CARD_WIDTH = 340
CARD_HEIGHT = 200
GRID_GAP = 12
GRID_MARGIN = 20
GRID_HEADER_HEIGHT = 84
MAX_STREAMER_CARDS = 72

_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_ENTRIES = 16

_BG = (8, 11, 16)
_CARD_BG = (13, 17, 23)
_BORDER = (48, 54, 61)
_TEXT = (244, 248, 252)
_MUTED = (157, 169, 183)
_ACCENT = (63, 185, 80)
_GOLD = (210, 153, 34)
_PRIMARY = (88, 166, 255)

_grid_cache: "OrderedDict[str, Tuple[float, StreamerGridImage]]" = OrderedDict()
_grid_cache_lock = threading.Lock()


@dataclass(frozen=True)
class StreamerGridImage:
    png: bytes
    digest: str
    width: int
    height: int
    caption: str
    count: int
    total_count: int
    period: str
    metric: str
    title: str = ""


def clear_streamer_grid_cache() -> None:
    with _grid_cache_lock:
        _grid_cache.clear()


def _metric_value(row: Dict[str, Any], metric: str) -> float:
    if metric == "coins":
        return float(row.get("total_coins") or 0.0)
    return float(row.get("eur_net") or 0.0)


def load_streamer_grid_rows(period: str = "all") -> List[Dict[str, Any]]:
    """Lädt alle Streamer inklusive Aggregaten für den gewählten Zeitraum."""
    from shared.db import get_streamer_grid_stats

    return get_streamer_grid_stats(period=normalize_period(period))


def _shorten(value: str, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _prepare_rows(
    rows: Sequence[Dict[str, Any]],
    metric: str,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            -_metric_value(row, metric),
            str(row.get("username") or "").lower(),
        ),
    )
    return ordered[:MAX_STREAMER_CARDS]


def _fingerprint(
    rows: Sequence[Dict[str, Any]],
    period: str,
    metric: str,
    title: str,
) -> str:
    payload = json.dumps(
        [
            period,
            metric,
            title,
            [
                [
                    row.get("username"),
                    bool(row.get("is_live")),
                    int(row.get("current_viewers") or 0),
                    int(row.get("total_coins") or 0),
                    round(float(row.get("eur_net") or 0.0), 4),
                    int(row.get("gift_events_count") or 0),
                ]
                for row in rows
            ],
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _caption(
    rows: Sequence[Dict[str, Any]],
    total_count: int,
    period: str,
    metric: str,
    title: str,
) -> str:
    total_eur = sum(float(row.get("eur_net") or 0.0) for row in rows)
    total_coins = sum(int(row.get("total_coins") or 0) for row in rows)
    lines = ["🖼️ TT-INTELLIGENCE · STREAMER GRID"]
    if title:
        lines.append(title)
    lines.append(
        f"{len(rows)} STREAMER · {PERIOD_LABELS.get(period, period.upper())} · "
        f"{METRIC_LABELS.get(metric, metric.upper())}"
    )
    lines.append(f"SUMME € {format_eur(total_eur)} · {format_coins(total_coins)} Coins")
    if len(rows) < total_count:
        lines.append(f"TOP {len(rows)} VON {total_count} STREAMERN")
    return "\n".join(lines)[:900]


def _render_grid(
    rows: Sequence[Dict[str, Any]],
    total_count: int,
    period: str,
    metric: str,
    title: str,
) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - Pillow ist Pflicht
        raise ChartImageError("Pillow ist nicht installiert.") from exc

    count = len(rows)
    if not count:
        raise ChartImageError("Keine Streamer für die Grid-Kollage gefunden.")

    columns = 6 if count > 12 else 4 if count > 4 else 2
    grid_rows = max(1, math.ceil(count / columns))
    header = GRID_HEADER_HEIGHT if title else 0
    width = (
        GRID_MARGIN * 2
        + columns * CARD_WIDTH
        + (columns - 1) * GRID_GAP
    )
    height = (
        GRID_MARGIN * 2
        + header
        + (GRID_GAP if title else 0)
        + grid_rows * CARD_HEIGHT
        + (grid_rows - 1) * GRID_GAP
    )

    canvas = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 5, height), fill=_ACCENT)

    font_brand = _font(True, 20, 700)
    font_title = _font(False, 26, 500)
    font_rank = _font(True, 16, 700)
    font_user = _font(False, 22, 700)
    font_status = _font(True, 14, 500)
    font_value = _font(False, 34, 700)
    font_secondary = _font(True, 17, 500)
    font_detail = _font(False, 14, 500)

    if title:
        draw.text(
            (GRID_MARGIN + 6, GRID_MARGIN + 2),
            "// TT-INTELLIGENCE · STREAMER GRID",
            font=font_brand,
            fill=_ACCENT,
        )
        draw.text(
            (GRID_MARGIN + 6, GRID_MARGIN + 30),
            title,
            font=font_title,
            fill=_TEXT,
        )

    y_start = GRID_MARGIN + (header + GRID_GAP if title else 0)
    for index, row in enumerate(rows):
        grid_row, grid_col = divmod(index, columns)
        x = GRID_MARGIN + grid_col * (CARD_WIDTH + GRID_GAP)
        y = y_start + grid_row * (CARD_HEIGHT + GRID_GAP)

        draw.rectangle(
            (x, y, x + CARD_WIDTH, y + CARD_HEIGHT),
            fill=_CARD_BG,
            outline=_BORDER,
            width=2,
        )
        draw.rectangle((x, y, x + 4, y + CARD_HEIGHT), fill=_PRIMARY)

        draw.text(
            (x + 16, y + 12),
            f"#{index + 1:02d}",
            font=font_rank,
            fill=_GOLD,
        )

        username = _shorten(f"@{row.get('username') or ''}", 24)
        draw.text((x + 16, y + 32), username, font=font_user, fill=_TEXT)

        is_live = bool(row.get("is_live"))
        status = (
            f"LIVE · {int(row.get('current_viewers') or 0):,}"
            if is_live
            else "OFFLINE"
        )
        draw.text(
            (x + CARD_WIDTH - 16, y + 14),
            status.replace(",", "."),
            font=font_status,
            fill=_ACCENT if is_live else _MUTED,
            anchor="ra",
        )

        eur_value = float(row.get("eur_net") or 0.0)
        coins_value = int(row.get("total_coins") or 0)
        if metric == "coins":
            primary = f"{format_coins(coins_value)} Coins"
            secondary = f"€ {format_eur(eur_value)}"
        else:
            primary = f"€ {format_eur(eur_value)}"
            secondary = f"{format_coins(coins_value)} Coins"

        value_font = font_value
        if draw.textlength(primary, font=font_value) > CARD_WIDTH - 32:
            value_font = _font(False, 26, 700)
        draw.text((x + 16, y + 76), primary, font=value_font, fill=_TEXT)
        draw.text(
            (x + 16, y + 122),
            secondary,
            font=font_secondary,
            fill=_MUTED,
        )

        gifts = int(row.get("gift_events_count") or 0)
        pct = float(row.get("pct_of_total") or 0.0)
        draw.text(
            (x + 16, y + 156),
            f"{gifts:,} Gifts · {pct:.1f}%".replace(",", "."),
            font=font_detail,
            fill=_MUTED,
        )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    canvas.close()
    return buffer.getvalue()


def build_streamer_grid(
    period: str = "all",
    metric: str = "eur",
    title: str = "",
    force_refresh: bool = False,
) -> StreamerGridImage:
    """Rendert alle Streamer als kompakte Karten in einem PNG."""
    norm_period = normalize_period(period)
    norm_metric = normalize_metric(metric)
    clean_title = str(title or "").strip()[:80]

    all_rows = load_streamer_grid_rows(norm_period)
    rows = _prepare_rows(all_rows, norm_metric)
    if not rows:
        raise ChartImageError("Keine Streamer für die Grid-Kollage gefunden.")

    key = _fingerprint(rows, norm_period, norm_metric, clean_title)
    now = time.monotonic()
    if not force_refresh:
        with _grid_cache_lock:
            cached = _grid_cache.get(key)
            if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
                _grid_cache.move_to_end(key)
                return cached[1]

    png = _render_grid(rows, len(all_rows), norm_period, norm_metric, clean_title)
    columns = 6 if len(rows) > 12 else 4 if len(rows) > 4 else 2
    grid_rows = max(1, math.ceil(len(rows) / columns))
    width = (
        GRID_MARGIN * 2
        + columns * CARD_WIDTH
        + (columns - 1) * GRID_GAP
    )
    height = (
        GRID_MARGIN * 2
        + (GRID_HEADER_HEIGHT if clean_title else 0)
        + (GRID_GAP if clean_title else 0)
        + grid_rows * CARD_HEIGHT
        + (grid_rows - 1) * GRID_GAP
    )

    image = StreamerGridImage(
        png=png,
        digest=hashlib.sha256(png).hexdigest(),
        width=width,
        height=height,
        caption=_caption(rows, len(all_rows), norm_period, norm_metric, clean_title),
        count=len(rows),
        total_count=len(all_rows),
        period=norm_period,
        metric=norm_metric,
        title=clean_title,
    )

    with _grid_cache_lock:
        _grid_cache[key] = (time.monotonic(), image)
        _grid_cache.move_to_end(key)
        while len(_grid_cache) > _CACHE_MAX_ENTRIES:
            _grid_cache.popitem(last=False)
    return image
