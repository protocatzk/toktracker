"""
Telegram HTML-Widgets für Einnahmen-Charts (Bot API 10.4).

Das Chart wird serverseitig als SVG gerendert. Damit ist die Grafik auch dann
sichtbar, wenn die Widget-Sandbox bestimmte DOM-/JS-Features nicht anbietet
oder ein Client Widgets nur eingeschränkt darstellt. JavaScript ist nur noch
eine optionale Progressive Enhancement für den Tap-Readout.

Telegram-Grenzen:
- 32.768 Bytes HTML
- 4.096 Bytes nach zlib-Level-9
"""

from __future__ import annotations

import html
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

WIDGET_MAX_HTML_BYTES = 32768
WIDGET_MAX_COMPRESSED_BYTES = 4096
WIDGET_HEIGHT = 232

CHART_PERIODS = ("today", "24h", "7d", "30d")
CHART_METRICS = ("eur", "coins")

PERIOD_LABELS = {
    "today": "HEUTE",
    "24h": "24 STUNDEN",
    "7d": "7 TAGE",
    "30d": "30 TAGE",
}

METRIC_LABELS = {
    "eur": "NETTO (EUR)",
    "coins": "COINS",
}

_PERIOD_ALIASES = {
    "today": "today",
    "heute": "today",
    "day": "today",
    "24h": "24h",
    "24": "24h",
    "7d": "7d",
    "woche": "7d",
    "week": "7d",
    "30d": "30d",
    "monat": "30d",
    "month": "30d",
}

_METRIC_ALIASES = {
    "eur": "eur",
    "euro": "eur",
    "€": "eur",
    "netto": "eur",
    "coins": "coins",
    "coin": "coins",
    "diamonds": "coins",
}

_CSS = """body{margin:0;padding:8px 12px;font:14px/1.35 system-ui,sans-serif;color:var(--tg-theme-text-color);user-select:none}
.tt{font-size:11px;letter-spacing:.04em;color:var(--tg-theme-hint-color)}
.vv{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.ii{font-size:11px;color:var(--tg-theme-hint-color);min-height:14px}
.ch{display:block;width:100%;height:110px;margin:6px 0 2px;touch-action:pan-y}
.xl{display:flex;justify-content:space-between;gap:4px;font-size:10px;color:var(--tg-theme-hint-color)}
.gr{stroke:var(--tg-theme-section-separator-color);stroke-width:1}
.ar{fill:var(--tg-theme-button-color);fill-opacity:.14}
.ln{fill:none;stroke:var(--tg-theme-button-color);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.pt{fill:var(--tg-theme-button-color)}"""

_JS = """<script>(function(){var s=document.getElementById('chart'),i=document.getElementById('info');
if(!s||!i)return;var v=(s.getAttribute('data-vals')||'').split(',').filter(Boolean).map(Number);
var l=(s.getAttribute('data-labels')||'').split('|'),eur=s.getAttribute('data-metric')==='eur';
function f(x){return eur?'€ '+x.toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2}):Math.round(x).toLocaleString('de-DE')}
s.addEventListener('pointerdown',function(e){if(!v.length)return;var r=s.getBoundingClientRect();
var k=Math.max(0,Math.min(v.length-1,Math.round((e.clientX-r.left)/r.width*(v.length-1))));
i.textContent=(l[k]||'')+' · '+f(v[k]);});})();</script>"""


@dataclass(frozen=True)
class ChartWidget:
    """Fertiges Chart-Widget inklusive Caption."""

    html: str
    caption: str
    period: str
    metric: str
    total: float
    peak: float
    points: int
    height: int = WIDGET_HEIGHT

    @property
    def period_label(self) -> str:
        return PERIOD_LABELS.get(self.period, self.period.upper())

    @property
    def metric_label(self) -> str:
        return METRIC_LABELS.get(self.metric, self.metric.upper())


class WidgetLimitError(ValueError):
    """HTML überschreitet eine Telegram-Widget-Grenze."""


def normalize_period(value: Optional[str]) -> str:
    return _PERIOD_ALIASES.get((value or "").strip().lower(), "24h")


def normalize_metric(value: Optional[str]) -> str:
    return _METRIC_ALIASES.get((value or "").strip().lower(), "eur")


def widget_sizes(html_source: str) -> Tuple[int, int]:
    """(Rohbytes, zlib-9-Bytes) – identisch zur Zählweise von Telegram."""
    raw = html_source.encode("utf-8")
    return len(raw), len(zlib.compress(raw, 9))


def ensure_widget_limits(html_source: str) -> None:
    raw, compressed = widget_sizes(html_source)
    if raw > WIDGET_MAX_HTML_BYTES:
        raise WidgetLimitError(f"Widget-HTML zu groß: {raw} > {WIDGET_MAX_HTML_BYTES} Bytes")
    if compressed > WIDGET_MAX_COMPRESSED_BYTES:
        raise WidgetLimitError(
            f"Widget-HTML komprimiert zu groß: {compressed} > {WIDGET_MAX_COMPRESSED_BYTES} Bytes"
        )


def format_eur(value: float) -> str:
    """Deutsche Zahlformatierung (1.234,56)."""
    formatted = f"{float(value):,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_coins(value: float) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def _tick_indices(count: int) -> List[int]:
    if count <= 0:
        return []
    if count == 1:
        return [0]
    return sorted({0, round((count - 1) / 3), round((count - 1) * 2 / 3), count - 1})


def _render_svg(values: Sequence[float]) -> str:
    count = len(values)
    if not count:
        return ""

    peak = max((float(v) for v in values), default=0.0) or 1.0
    width, height = 320.0, 110.0
    top, bottom = 4.0, height - 6.0

    def x_at(index: int) -> float:
        return 0.0 if count == 1 else index / (count - 1) * width

    def y_at(value: float) -> float:
        return bottom - (float(value) / peak) * (bottom - top)

    points = [(x_at(i), y_at(v)) for i, v in enumerate(values)]
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    area = line + f" L{width:.1f} {bottom:.1f} L0 {bottom:.1f} Z" if count > 1 else ""
    grid = "".join(
        f'<line class="gr" x1="0" y1="{gy:.1f}" x2="{width:.0f}" y2="{gy:.1f}"/>'
        for gy in (top, (top + bottom) / 2, bottom)
    )
    area_path = f'<path class="ar" d="{area}"/>' if area else ""
    marker = f'<circle class="pt" cx="{points[-1][0]:.1f}" cy="{points[-1][1]:.1f}" r="2.5"/>'
    return (
        f'<svg class="ch" id="chart" viewBox="0 0 320 110" preserveAspectRatio="none" '
        f'data-vals="{html.escape(",".join(f"{float(v):.2f}" for v in values), quote=True)}" '
        f'data-labels="__LABELS__" data-metric="__METRIC__">'
        f"{grid}{area_path}<path class=\"ln\" d=\"{line}\"/>{marker}</svg>"
    )


def _render_ticks(labels: Sequence[str]) -> str:
    indices = _tick_indices(len(labels))
    if not indices:
        return ""
    slots = [""] * len(indices)
    for pos, idx in enumerate(indices):
        slots[pos] = html.escape(labels[idx]) if idx < len(labels) else ""
    return '<div class="xl">' + "".join(f"<span>{label}</span>" for label in slots) + "</div>"


def _load_timeline(
    period: str, force_refresh: bool = False
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # Lazy import: haelt das Modul unabhaengig von der DB-Fassade und
    # vermeidet Zyklen beim App-Import.
    from database import get_chart_timeline

    data = get_chart_timeline(period=period, force_refresh=force_refresh)
    timeline = data.get("timeline") or []
    totals = data.get("totals") or {}
    return list(timeline), dict(totals)


def build_chart_widget(
    period: str = "24h", metric: str = "eur", force_refresh: bool = False
) -> ChartWidget:
    """Lädt die leichte Chart-Zeitreihe und rendert das Widget serverseitig."""
    norm_period = normalize_period(period)
    norm_metric = normalize_metric(metric)

    timeline, totals = _load_timeline(norm_period, force_refresh)
    metric_key = "coins" if norm_metric == "coins" else "eur_net"
    total_key = "total_coins" if norm_metric == "coins" else "eur_net"

    values: List[float] = []
    labels: List[str] = []
    for row in timeline:
        try:
            values.append(max(0.0, float(row.get(metric_key) or 0.0)))
        except (TypeError, ValueError):
            values.append(0.0)
        labels.append(str(row.get("label") or "")[:12])

    peak = max(values, default=0.0)
    total = float(totals.get(total_key) or 0.0)

    period_label = PERIOD_LABELS.get(norm_period, norm_period.upper())
    metric_label = METRIC_LABELS.get(norm_metric, norm_metric.upper())
    value_text = (
        f"€ {format_eur(total)}" if norm_metric == "eur" else f"{format_coins(total)} Coins"
    )
    peak_text = f"€ {format_eur(peak)}" if norm_metric == "eur" else f"{format_coins(peak)} Coins"

    svg = _render_svg(values)
    ticks = _render_ticks(labels)
    labels_attr = html.escape("|".join(labels), quote=True)
    svg = (
        svg.replace("__LABELS__", labels_attr).replace("__METRIC__", norm_metric)
        if svg
        else ""
    )
    info_text = f"PEAK {peak_text} · {len(values)} PUNKTE" if values else "Keine Daten im Zeitraum."

    html_source = (
        "<!doctype html><html><head><style>"
        + _CSS
        + "</style></head><body>"
        + f'<div class="tt">{html.escape(period_label)} · {html.escape(metric_label)}</div>'
        + f'<div class="vv">{html.escape(value_text)}</div>'
        + f'<div class="ii" id="info">{html.escape(info_text)}</div>'
        + svg
        + ticks
        + _JS
        + "</body></html>"
    )
    ensure_widget_limits(html_source)

    caption = (
        f"📈 TT-INTELLIGENCE · {period_label} · {metric_label}\n"
        f"{value_text} · Peak {peak_text}"
    )
    return ChartWidget(
        html=html_source,
        caption=caption,
        period=norm_period,
        metric=norm_metric,
        total=total,
        peak=peak,
        points=len(values),
    )
