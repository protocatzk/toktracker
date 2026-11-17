"""
Bilderkollagen aus mehreren Chart-Ansichten für den Telegram-Bot.

Der normale ``/chart``-Befehl rendert genau eine Ansicht. Für Reportings
braucht es dagegen oft mehrere Perspektiven in einem Bild. Dieses Modul
kombiniert die bestehenden PNG-Renderer zu einem Raster:

- jede Kachel kann eine eigene Ansicht, Zeitraum, Metrik und Scope haben
- das Raster ist auf 3x3 (max. 9 Kacheln) begrenzt
- das fertige Bild wird zusätzlich zum Einzelbild-Cache gecacht

Die Kacheln werden weiterhin von :func:`shared.chart_image.build_chart_image`
gerendert; dadurch gelten exakt dieselben Daten- und Bild-Caches wie bei
``/chart``. Das Modul bleibt frei von Telegram- und DB-Abhängigkeiten, damit
Parser und Komposition isoliert testbar sind.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Sequence, Tuple

from shared.chart_image import (
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    ChartImageError,
    _font,
    build_chart_image,
)
from shared.chart_views import VIEW_LABELS, is_view_alias, normalize_view
from shared.widget_chart import (
    METRIC_LABELS,
    PERIOD_LABELS,
    is_metric_alias,
    is_period_alias,
    normalize_metric,
    normalize_period,
)

MAX_COLLAGE_TILES = 9
MAX_COLLAGE_GRID = 3
DEFAULT_COLLAGE_VIEWS: Tuple[str, ...] = (
    "timeline",
    "streamers",
    "timeofday",
    "gifts",
)

# Sonderansicht: eine kompakte Karte pro Streamer statt einer Chart-Kachel.
STREAMER_CARDS_VIEW = "cards"
CARD_VIEW_ALIASES = frozenset(
    {
        "cards",
        "card",
        "streamer_cards",
        "streamercards",
        "streamer-grid",
        "streamergrid",
        "streamer_grid",
    }
)


def is_card_view(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in CARD_VIEW_ALIASES

_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_ENTRIES = 32

_MARGIN = 18
_GAP = 12
_HEADER_HEIGHT = 70

_COLLAGE_BG = (8, 11, 16)
_COLLAGE_BORDER = (48, 54, 61)
_COLLAGE_TEXT = (244, 248, 252)
_COLLAGE_ACCENT = (63, 185, 80)
_COLLAGE_TAG_BG = (13, 17, 23)

_ALL_SCOPES = frozenset({"all", "alle", "global", "*", ""})
_GROUP_PREFIXES = ("gruppe:", "group:", "g:")


class CollageError(ValueError):
    """Ungültige Kollagen-Parameter oder nicht renderbare Kollage."""


@dataclass(frozen=True)
class CollageTile:
    """Aufgelöste Kachel: Scope-IDs und -Namen sind bereits bekannt."""

    view: str = "timeline"
    period: str = "24h"
    metric: str = "eur"
    streamer_id: Optional[int] = None
    streamer_name: str = ""
    group_id: Optional[int] = None
    group_name: str = ""
    label: str = ""


@dataclass(frozen=True)
class CollageTileRequest:
    """Noch nicht aufgelöste Kachel aus dem Parameter-Parser."""

    view: str = "timeline"
    period: str = "24h"
    metric: str = "eur"
    scope_ref: str = ""
    label: str = ""


@dataclass(frozen=True)
class CollageRequest:
    """Vollständig geparster ``/collage``-Auftrag."""

    tiles: Tuple[CollageTileRequest, ...]
    period: str = "24h"
    metric: str = "eur"
    scope_ref: str = ""
    rows: int = 1
    cols: int = 1
    title: str = ""
    force_refresh: bool = False


@dataclass(frozen=True)
class ChartCollage:
    """Fertige PNG-Kollage inklusive Caption und Raster-Metadaten."""

    png: bytes
    digest: str
    width: int
    height: int
    caption: str
    rows: int
    cols: int
    tiles: Tuple[CollageTile, ...]
    title: str = ""


_collage_cache: "OrderedDict[str, Tuple[float, ChartCollage]]" = OrderedDict()
_collage_cache_lock = threading.Lock()


def clear_chart_collage_cache() -> None:
    with _collage_cache_lock:
        _collage_cache.clear()


def infer_grid(count: int) -> Tuple[int, int]:
    """Liefert ``(cols, rows)`` für eine automatische Rasterwahl."""
    count = max(1, int(count or 1))
    cols = min(MAX_COLLAGE_GRID, max(1, math.ceil(math.sqrt(count))))
    rows = max(1, math.ceil(count / cols))
    return cols, rows


def validate_grid(rows: int, cols: int, count: int) -> None:
    """Validiert Rastergrenzen und die Anzahl der Kacheln."""
    if not (1 <= rows <= MAX_COLLAGE_GRID and 1 <= cols <= MAX_COLLAGE_GRID):
        raise CollageError(
            f"Layout muss zwischen 1x1 und {MAX_COLLAGE_GRID}x{MAX_COLLAGE_GRID} liegen."
        )
    if count < 1:
        raise CollageError("Eine Kollage benötigt mindestens eine Kachel.")
    if count > MAX_COLLAGE_TILES:
        raise CollageError(f"Maximal {MAX_COLLAGE_TILES} Kacheln pro Kollage.")
    if count > rows * cols:
        raise CollageError(
            f"{count} Kacheln passen nicht in ein {cols}x{rows}-Raster."
        )


def _parse_layout(value: str) -> Tuple[int, int]:
    """Liest ``SPALTENxZEILEN`` (z. B. ``2x3``)."""
    match = re.fullmatch(r"\s*(\d+)\s*[x×*]\s*(\d+)\s*", str(value or ""))
    if not match:
        raise CollageError("Layout erwartet im Format SPALTENxZEILEN, z. B. 2x2.")
    cols, rows = int(match.group(1)), int(match.group(2))
    if not (1 <= rows <= MAX_COLLAGE_GRID and 1 <= cols <= MAX_COLLAGE_GRID):
        raise CollageError(
            f"Layout muss zwischen 1x1 und {MAX_COLLAGE_GRID}x{MAX_COLLAGE_GRID} liegen."
        )
    return cols, rows


def normalize_scope_ref(value: object, default: str = "") -> str:
    """
    Normalisiert Scope-Angaben.

    ``gruppe:Team+Alpha`` wird zu ``gruppe:Team Alpha``. Ein ``+`` ist damit
    der Telegram-taugliche Ersatz für Leerzeichen in Gruppennamen. Leere
    Angaben und ``all``/``alle`` bedeuten global.
    """
    text = str(value or "").strip()
    if not text:
        return default
    lowered = text.lower()
    if lowered in _ALL_SCOPES:
        return ""
    for prefix in _GROUP_PREFIXES:
        if lowered.startswith(prefix):
            name = text[len(prefix):].strip().replace("+", " ")
            if not name:
                raise CollageError("Gruppen-Scope ohne Namen.")
            return f"gruppe:{name}"
    return "@" + text.lstrip("@").replace("+", " ")


def _looks_like_scope(value: str) -> bool:
    lowered = value.lower()
    return (
        value.startswith("@")
        or lowered in _ALL_SCOPES
        or any(lowered.startswith(prefix) for prefix in _GROUP_PREFIXES)
    )


def _split_tile_specs(value: str) -> List[str]:
    return [part.strip() for part in re.split(r"[,;]", str(value or "")) if part.strip()]


def _parse_tile_spec(spec: str, request: CollageRequest) -> CollageTileRequest:
    fields = [field.strip() for field in str(spec).split("|")]
    view = ""
    period: Optional[str] = None
    metric: Optional[str] = None
    scope: Optional[str] = None
    label = ""

    for field in fields:
        if not field:
            continue
        key, separator, value = field.partition("=")
        key_lower = key.strip().lower()
        value = value.strip()

        if separator:
            if key_lower in ("view", "ansicht"):
                if is_card_view(value):
                    view = STREAMER_CARDS_VIEW
                elif is_view_alias(value):
                    view = normalize_view(value)
                else:
                    raise CollageError(f"Unbekannte Ansicht '{value}'.")
            elif key_lower in ("period", "zeitraum", "zeit"):
                if not is_period_alias(value):
                    raise CollageError(f"Unbekannter Zeitraum '{value}'.")
                period = normalize_period(value)
            elif key_lower in ("metric", "metrik"):
                if not is_metric_alias(value):
                    raise CollageError(f"Unbekannte Metrik '{value}'.")
                metric = normalize_metric(value)
            elif key_lower in ("scope", "bereich"):
                scope = normalize_scope_ref(value)
            elif key_lower in ("streamer", "kanal"):
                scope = normalize_scope_ref("@" + value.lstrip("@"))
            elif key_lower in ("gruppe", "group"):
                scope = normalize_scope_ref("gruppe:" + value)
            elif key_lower in ("label", "titel", "title"):
                label = value[:40]
            else:
                raise CollageError(f"Unbekannte Kachel-Option '{key}'.")
            continue

        lowered = field.lower()
        if not view:
            if is_card_view(field):
                view = STREAMER_CARDS_VIEW
            elif not is_view_alias(field):
                raise CollageError(
                    f"Kachel muss mit einer Ansicht beginnen (z. B. verlauf), nicht '{field}'."
                )
            else:
                view = normalize_view(field)
        elif _looks_like_scope(field):
            scope = normalize_scope_ref(field)
        elif is_period_alias(field):
            period = normalize_period(field)
        elif is_metric_alias(field):
            metric = normalize_metric(field)
        elif lowered.startswith("label:"):
            label = field[len("label:"):].strip()[:40]
        else:
            # Freitext nach der Ansicht ist ein Streamer-Name.
            scope = normalize_scope_ref(field)

    if not view:
        raise CollageError(f"Kachel '{spec}' ohne Ansicht.")

    return CollageTileRequest(
        view=view,
        period=period or request.period,
        metric=metric or request.metric,
        scope_ref=scope if scope is not None else request.scope_ref,
        label=label,
    )


def parse_collage_args(
    args: Optional[Sequence[str]],
    max_tiles: int = MAX_COLLAGE_TILES,
) -> CollageRequest:
    """
    Parst die komplexe ``/collage``-Syntax.

    Globale Optionen::

        scope=@name|gruppe:Name|all
        period=today|24h|7d|30d
        metric=eur|coins
        layout=SPALTENxZEILEN
        views=verlauf,streamer,tageszeit,geschenke,spender
        title=...
        refresh=1

    Kachel-Spezifikationen innerhalb von ``views=`` werden mit Komma getrennt
    und nutzen ``|`` für Felder::

        verlauf|@alice|7d|eur
        streamer|gruppe:Team+Alpha|30d|coins
        geschenke|all|24h|eur|label=Q4
    """
    limit = min(MAX_COLLAGE_TILES, max(1, int(max_tiles or MAX_COLLAGE_TILES)))
    period = "24h"
    metric = "eur"
    scope_ref = ""
    title = ""
    rows = 0
    cols = 0
    force_refresh = False
    tile_specs: List[str] = []

    for raw in args or ():
        token = str(raw).strip()
        if not token:
            continue
        key, separator, value = token.partition("=")
        key_lower = key.strip().lower()
        value = value.strip()

        if separator and "|" not in key:
            if key_lower in ("period", "zeitraum", "zeit"):
                if not is_period_alias(value):
                    raise CollageError(f"Unbekannter Zeitraum '{value}'.")
                period = normalize_period(value)
            elif key_lower in ("metric", "metrik", "waehrung", "währung"):
                if not is_metric_alias(value):
                    raise CollageError(f"Unbekannte Metrik '{value}'.")
                metric = normalize_metric(value)
            elif key_lower in ("scope", "bereich"):
                scope_ref = normalize_scope_ref(value)
            elif key_lower in ("streamer", "kanal"):
                scope_ref = normalize_scope_ref("@" + value.lstrip("@"))
            elif key_lower in ("gruppe", "group"):
                scope_ref = normalize_scope_ref("gruppe:" + value)
            elif key_lower in ("layout", "raster", "grid"):
                cols, rows = _parse_layout(value)
            elif key_lower in ("views", "tiles", "ansichten", "kacheln", "bilder"):
                specs = _split_tile_specs(value)
                if not specs:
                    raise CollageError("views= enthält keine Kacheln.")
                tile_specs.extend(specs)
            elif key_lower in ("tile", "view", "ansicht", "kachel"):
                if not value:
                    raise CollageError("Leere Kachel-Angabe.")
                tile_specs.append(value)
            elif key_lower in ("title", "titel"):
                title = value[:80]
            elif key_lower in ("refresh", "aktualisieren", "neu", "force"):
                force_refresh = value.lower() in ("1", "true", "yes", "on", "ja")
            else:
                raise CollageError(f"Unbekannte Option '{key}'.")
            continue

        lowered = token.lower()
        if lowered in ("help", "hilfe", "?", "h"):
            raise CollageError("Hilfe angefordert.")
        if re.fullmatch(r"\d+\s*[x×*]\s*\d+", token):
            cols, rows = _parse_layout(token)
        elif lowered in ("refresh", "force", "neu", "aktualisieren"):
            force_refresh = True
        elif _looks_like_scope(token):
            scope_ref = normalize_scope_ref(token)
        elif is_period_alias(token):
            period = normalize_period(token)
        elif is_metric_alias(token):
            metric = normalize_metric(token)
        elif is_view_alias(token) or is_card_view(token) or "|" in token:
            specs = _split_tile_specs(token)
            if not specs:
                raise CollageError("Leere Kachel-Angabe.")
            tile_specs.extend(specs)
        else:
            # Kurzform für einen Streamer ohne @.
            scope_ref = normalize_scope_ref(token)

    if not tile_specs:
        tile_specs = list(DEFAULT_COLLAGE_VIEWS[:limit])

    if len(tile_specs) > limit:
        raise CollageError(f"Maximal {limit} Kacheln pro Kollage.")

    base = CollageRequest(
        tiles=(),
        period=period,
        metric=metric,
        scope_ref=scope_ref,
        title=title,
        force_refresh=force_refresh,
    )
    tiles = tuple(_parse_tile_spec(spec, base) for spec in tile_specs)

    if not rows or not cols:
        cols, rows = infer_grid(len(tiles))
    validate_grid(rows, cols, len(tiles))

    return CollageRequest(
        tiles=tiles,
        period=period,
        metric=metric,
        scope_ref=scope_ref,
        rows=rows,
        cols=cols,
        title=title,
        force_refresh=force_refresh,
    )


def _scope_label(tile: CollageTile) -> str:
    if tile.group_name:
        return f"GRUPPE {tile.group_name}"
    if tile.streamer_name:
        return f"@{tile.streamer_name}"
    return "ALLE"


def _combined_label(values: set[str], mapping: dict[str, str]) -> str:
    if len(values) == 1:
        value = next(iter(values))
        return mapping.get(value, value.upper())
    return "MIX (" + ", ".join(sorted(mapping.get(value, value.upper()) for value in values)) + ")"


def _collage_caption(
    tiles: Sequence[CollageTile],
    rows: int,
    cols: int,
    title: str,
) -> str:
    periods = {tile.period for tile in tiles}
    metrics = {tile.metric for tile in tiles}
    period_text = _combined_label(periods, PERIOD_LABELS)
    metric_text = _combined_label(metrics, METRIC_LABELS)

    seen: List[str] = []
    for tile in tiles:
        label = _scope_label(tile)
        if label not in seen:
            seen.append(label)
    scope_text = ", ".join(seen[:4])
    if len(seen) > 4:
        scope_text += f" +{len(seen) - 4}"

    views: List[str] = []
    for tile in tiles:
        label = VIEW_LABELS.get(tile.view, tile.view.upper())
        if label not in views:
            views.append(label)

    lines = [
        "🖼️ TT-INTELLIGENCE · BILDERKOLLAGE",
        f"{cols}×{rows} · {len(tiles)} KACHELN · {period_text} · {metric_text}",
    ]
    if title:
        lines.append(title)
    lines.append(f"SCOPE {scope_text}")
    lines.append(f"ANSICHTEN {', '.join(views)}")
    return "\n".join(lines)[:900]


def _render_collage(
    images: Sequence[object],
    tiles: Sequence[CollageTile],
    rows: int,
    cols: int,
    title: str,
) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - Pillow ist Pflicht
        raise ChartImageError("Pillow ist nicht installiert.") from exc

    margin = _MARGIN
    gap = _GAP
    header_height = _HEADER_HEIGHT if title else 0
    width = margin * 2 + cols * IMAGE_WIDTH + (cols - 1) * gap
    height = (
        margin * 2
        + header_height
        + (gap if title else 0)
        + rows * IMAGE_HEIGHT
        + (rows - 1) * gap
    )

    canvas = Image.new("RGB", (width, height), _COLLAGE_BG)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 5, height), fill=_COLLAGE_ACCENT)

    if title:
        brand_font = _font(True, 20, 700)
        title_font = _font(False, 24, 500)
        draw.text(
            (margin + 6, margin + 2),
            "// TT-INTELLIGENCE · BILDKOLLAGE",
            font=brand_font,
            fill=_COLLAGE_ACCENT,
        )
        draw.text(
            (margin + 6, margin + 28),
            title,
            font=title_font,
            fill=_COLLAGE_TEXT,
        )

    y_start = margin + (header_height + gap if title else 0)
    label_font = _font(True, 16, 700)

    for index, (image, tile) in enumerate(zip(images, tiles, strict=True)):
        row, col = divmod(index, cols)
        x = margin + col * (IMAGE_WIDTH + gap)
        y = y_start + row * (IMAGE_HEIGHT + gap)

        with Image.open(BytesIO(image.png)) as source:
            tile_image = source.convert("RGB")
            canvas.paste(tile_image, (x, y))
            tile_image.close()

        draw.rectangle(
            (x - 1, y - 1, x + IMAGE_WIDTH, y + IMAGE_HEIGHT),
            outline=_COLLAGE_BORDER,
            width=2,
        )

        if tile.label:
            text = tile.label if len(tile.label) <= 28 else tile.label[:27] + "…"
            text_width = draw.textlength(text, font=label_font)
            right = x + IMAGE_WIDTH - 12
            left = right - text_width - 18
            draw.rectangle((left, y + 10, right, y + 34), fill=_COLLAGE_TAG_BG)
            draw.rectangle((left, y + 10, left + 3, y + 34), fill=_COLLAGE_ACCENT)
            draw.text(
                (left + 10, y + 22),
                text,
                font=label_font,
                fill=_COLLAGE_TEXT,
                anchor="lm",
            )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    canvas.close()
    return buffer.getvalue()


def _fingerprint(
    tiles: Sequence[CollageTile],
    rows: int,
    cols: int,
    title: str,
) -> str:
    payload = json.dumps(
        [
            rows,
            cols,
            title,
            [
                [
                    tile.view,
                    tile.period,
                    tile.metric,
                    tile.streamer_id or 0,
                    tile.streamer_name,
                    tile.group_id or 0,
                    tile.group_name,
                    tile.label,
                ]
                for tile in tiles
            ],
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_chart_collage(
    tiles: Sequence[CollageTile],
    rows: Optional[int] = None,
    cols: Optional[int] = None,
    title: str = "",
    force_refresh: bool = False,
) -> ChartCollage:
    """
    Rendert mehrere Chart-Kacheln als eine PNG-Kollage.

    Die Einzelbilder laufen über :func:`build_chart_image` und profitieren
    damit automatisch von dessen Daten-/PNG-Cache. Zusätzlich wird die
    fertige Kollage per Inhalts-Fingerprint für kurze Zeit gecacht.
    """
    tile_list = tuple(tiles or ())
    if not tile_list:
        raise CollageError("Eine Kollage benötigt mindestens eine Kachel.")
    if len(tile_list) > MAX_COLLAGE_TILES:
        raise CollageError(f"Maximal {MAX_COLLAGE_TILES} Kacheln pro Kollage.")

    if not rows or not cols:
        inferred_cols, inferred_rows = infer_grid(len(tile_list))
        cols = int(cols or inferred_cols)
        rows = int(rows or inferred_rows)
    validate_grid(int(rows), int(cols), len(tile_list))

    clean_title = str(title or "").strip()[:80]
    key = _fingerprint(tile_list, int(rows), int(cols), clean_title)
    now = time.monotonic()

    if not force_refresh:
        with _collage_cache_lock:
            cached = _collage_cache.get(key)
            if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
                _collage_cache.move_to_end(key)
                return cached[1]

    images = [
        build_chart_image(
            tile.period,
            tile.metric,
            tile.streamer_id,
            tile.streamer_name,
            force_refresh,
            tile.view,
            tile.group_id,
            tile.group_name,
        )
        for tile in tile_list
    ]
    png = _render_collage(images, tile_list, int(rows), int(cols), clean_title)
    collage = ChartCollage(
        png=png,
        digest=hashlib.sha256(png).hexdigest(),
        width=cols * IMAGE_WIDTH + (cols - 1) * _GAP + 2 * _MARGIN,
        height=(
            rows * IMAGE_HEIGHT
            + (rows - 1) * _GAP
            + 2 * _MARGIN
            + (_HEADER_HEIGHT + _GAP if clean_title else 0)
        ),
        caption=_collage_caption(tile_list, int(rows), int(cols), clean_title),
        rows=int(rows),
        cols=int(cols),
        tiles=tile_list,
        title=clean_title,
    )

    with _collage_cache_lock:
        _collage_cache[key] = (time.monotonic(), collage)
        _collage_cache.move_to_end(key)
        while len(_collage_cache) > _CACHE_MAX_ENTRIES:
            _collage_cache.popitem(last=False)
    return collage
