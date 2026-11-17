"""
Zusätzliche Bot-Chart-Ansichten (Admin-Panel-Parität).

Der Bot konnte bisher nur den Einnahmen-Verlauf als Linien-/Flächendiagramm
senden. Dieses Modul liefert die übrigen Analytics-Charts des Admin-Panels als
gemeinsame Datenbasis für den PNG- und den HTML-Widget-Renderer:

- ``streamers``: Streamer-Umsatz-Ranking (bzw. Session-Performance)
- ``timeofday``: Tageszeit-Aktivitätsmuster
- ``gifts``:     Verteilung der Top-Geschenke
- ``gifters``:   Ranking der Top-Spender

Die Zeitreihe (``timeline``) bleibt im leichtgewichtigen Pfad von
:mod:`shared.widget_chart`. Für die übrigen Ansichten wird
``get_analytics_data`` genutzt, damit Bot und Admin-Panel exakt dieselben
Aggregate anzeigen.
"""

from __future__ import annotations

import html
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from shared.widget_chart import (
    ChartSeries,
    chart_caption,
    ensure_widget_limits,
    format_coins,
    format_eur,
    load_chart_series,
    normalize_metric,
    normalize_period,
)

if TYPE_CHECKING:  # pragma: no cover - nur für Typen
    from shared.widget_chart import ChartWidget

CHART_VIEWS = ("timeline", "streamers", "timeofday", "gifts", "gifters")
DEFAULT_CHART_VIEW = "timeline"

VIEW_LABELS = {
    "timeline": "VERLAUF",
    "streamers": "STREAMER",
    "timeofday": "TAGESZEIT",
    "gifts": "GESCHENKE",
    "gifters": "SPENDER",
}

VIEW_TITLES = {
    "timeline": "EINNAHMEN-VERLAUF",
    "streamers": "STREAMER-RANKING",
    "timeofday": "TAGESZEIT-MUSTER",
    "gifts": "GESCHENKE-VERTEILUNG",
    "gifters": "TOP-SPENDER",
}

_KIND_BY_VIEW = {
    "timeline": "line",
    "streamers": "hbar",
    "timeofday": "vbar",
    "gifts": "donut",
    "gifters": "hbar",
}

_VIEW_ALIASES = {
    "timeline": "timeline",
    "verlauf": "timeline",
    "line": "timeline",
    "linie": "timeline",
    "history": "timeline",
    "verlauf_chart": "timeline",
    "streamers": "streamers",
    "streamer": "streamers",
    "ranking": "streamers",
    "streamer_ranking": "streamers",
    "streamer-ranking": "streamers",
    "top": "streamers",
    "timeofday": "timeofday",
    "time_of_day": "timeofday",
    "tageszeit": "timeofday",
    "uhrzeit": "timeofday",
    "hours": "timeofday",
    "stunden": "timeofday",
    "gifts": "gifts",
    "gift": "gifts",
    "geschenke": "gifts",
    "top_gifts": "gifts",
    "gift_dist": "gifts",
    "verteilung": "gifts",
    "gifters": "gifters",
    "gifter": "gifters",
    "spender": "gifters",
    "donors": "gifters",
    "donor": "gifters",
    "top_gifters": "gifters",
    "supporter": "gifters",
}

_PALETTE = (
    "#58a6ff",
    "#3fb950",
    "#d29922",
    "#bc8cff",
    "#f778ba",
    "#39c5cf",
    "#ffa657",
    "#ff7b72",
    "#7ee787",
    "#79c0ff",
)

_MAX_ROWS = 8

# Die Zusatz-Ansichten teilen sich dieselbe Analytics-Abfrage. Ein kurzer
# Cache verhindert, dass wiederholte Button-Klicks mehrfach die teuren
# Aggregationen auslösen (der Zeitverlauf hat seinen eigenen Cache).
_ANALYTICS_TTL = {
    "today": 30.0,
    "24h": 30.0,
    "7d": 120.0,
    "30d": 300.0,
    "all": 600.0,
}
_ANALYTICS_CACHE_MAX = 128
_analytics_cache: "OrderedDict[str, Tuple[float, Dict[str, Any]]]" = OrderedDict()
_analytics_cache_lock = threading.Lock()


_WIDGET_CSS = """body{margin:0;padding:8px 12px;font:14px/1.35 system-ui,sans-serif;color:var(--tg-theme-text-color);user-select:none}
.tt{font-size:11px;letter-spacing:.04em;color:var(--tg-theme-hint-color)}
.vv{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.ii{font-size:11px;color:var(--tg-theme-hint-color);min-height:14px}
.xl{display:flex;justify-content:space-between;gap:4px;font-size:10px;color:var(--tg-theme-hint-color)}
.cv{display:block;width:100%;height:110px;margin:6px 0 2px}
.gr{stroke:var(--tg-theme-section-separator-color);stroke-width:1}
.bar{fill:var(--tg-theme-button-color);fill-opacity:.55}
.barhi{fill:var(--tg-theme-button-color)}
.hr{display:flex;align-items:center;gap:6px;margin:3px 0;font-size:10px;color:var(--tg-theme-text-color)}
.hn{width:94px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--tg-theme-hint-color)}
.hw{flex:1;height:8px;overflow:hidden}
.hf{display:block;height:8px;background:var(--tg-theme-button-color);opacity:.7}
.ht{width:72px;text-align:right;font-variant-numeric:tabular-nums}
.dn{display:flex;align-items:center;gap:10px;margin:6px 0 2px}
.dch{width:104px;height:104px;flex:none}
.dl{flex:1;font-size:10px;color:var(--tg-theme-text-color)}
.li{display:flex;align-items:center;gap:5px;margin:2px 0}
.sq{width:8px;height:8px;flex:none}
.ln2{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--tg-theme-hint-color)}
.lv{font-variant-numeric:tabular-nums}"""


def normalize_view(value: Optional[str]) -> str:
    """Normalisiert Ansichtsnamen und Aliase auf die kanonischen Views."""
    return _VIEW_ALIASES.get((value or "").strip().lower(), DEFAULT_CHART_VIEW)


def is_view_alias(value: Optional[str]) -> bool:
    """True, wenn der Wert ein bekannter Ansichtsname/-Alias ist."""
    return (value or "").strip().lower() in _VIEW_ALIASES


@dataclass(frozen=True)
class ChartViewSeries:
    """Kategorielle Chart-Daten für Ranking-, Tageszeit- und Donut-Ansichten."""

    view: str
    period: str
    metric: str
    kind: str
    labels: Tuple[str, ...]
    values: Tuple[float, ...]
    secondary: Tuple[float, ...]
    title: str
    subtitle: str
    total: float
    peak: float
    streamer_id: Optional[int] = None
    streamer_name: str = ""
    group_id: Optional[int] = None
    group_name: str = ""
    highlight: int = -1
    caption_override: str = ""

    @property
    def period_label(self) -> str:
        from shared.widget_chart import PERIOD_LABELS

        return PERIOD_LABELS.get(self.period, self.period.upper())

    @property
    def metric_label(self) -> str:
        from shared.widget_chart import METRIC_LABELS

        return METRIC_LABELS.get(self.metric, self.metric.upper())

    @property
    def view_label(self) -> str:
        return VIEW_LABELS.get(self.view, self.view.upper())

    @property
    def total_text(self) -> str:
        return _format_value(self.total, self.metric)

    @property
    def peak_text(self) -> str:
        return _format_value(self.peak, self.metric)

    @property
    def scope_prefix(self) -> str:
        if self.group_name:
            return f"GRUPPE {self.group_name} · "
        if self.streamer_name:
            return f"@{self.streamer_name} · "
        return ""

    @property
    def title_text(self) -> str:
        return f"{self.scope_prefix}{self.title} · {self.period_label} · {self.metric_label}"

    @property
    def caption(self) -> str:
        if self.caption_override:
            return self.caption_override
        prefix = self.scope_prefix
        return (
            f"📊 TT-INTELLIGENCE · {prefix}{self.title}\n"
            f"{self.period_label} · {self.metric_label} · "
            f"{self.total_text} · Peak {self.peak_text}"
        )


def _format_value(value: float, metric: str) -> str:
    return (
        f"€ {format_eur(value)}"
        if metric == "eur"
        else f"{format_coins(value)} Coins"
    )


def _row_value(row: Dict[str, Any], metric: str) -> float:
    if metric == "coins":
        value = row.get("coins")
        if value is None:
            value = row.get("total_coins")
        if value is None:
            value = row.get("session_coins")
        return float(value or 0.0)
    return float(row.get("eur_net", 0.0) or 0.0)


def _row_secondary(row: Dict[str, Any], metric: str) -> float:
    if metric == "coins":
        return float(row.get("eur_net", 0.0) or 0.0)
    return float(row.get("total_coins", 0.0) or 0.0)


def _shorten(value: str, limit: int = 20) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _empty_view(
    view: str,
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
    title: str,
) -> ChartViewSeries:
    return ChartViewSeries(
        view=view,
        period=period,
        metric=metric,
        kind=_KIND_BY_VIEW.get(view, "hbar"),
        labels=(),
        values=(),
        secondary=(),
        title=title,
        subtitle="KEINE DATEN IM ZEITRAUM",
        total=0.0,
        peak=0.0,
        streamer_id=streamer_id,
        streamer_name=streamer_name,
    )


def clear_chart_view_cache() -> None:
    """Leert den Analytics-Cache der Zusatz-Ansichten (z. B. nach Gruppenänderungen)."""
    with _analytics_cache_lock:
        _analytics_cache.clear()


def _load_analytics(
    streamer_id: Optional[int],
    period: str,
    force_refresh: bool = False,
    group_id: Optional[int] = None,
) -> Dict[str, Any]:
    sid = int(streamer_id) if streamer_id else 0
    gid = int(group_id) if group_id else 0
    cache_key = f"{period}:{sid}:g{gid}"
    ttl = _ANALYTICS_TTL.get(period, 60.0)
    now = time.monotonic()

    if not force_refresh:
        with _analytics_cache_lock:
            cached = _analytics_cache.get(cache_key)
            if cached and (now - cached[0]) < ttl:
                _analytics_cache.move_to_end(cache_key)
                return cached[1]

    from shared.db import get_analytics_data

    data = get_analytics_data(streamer_id=streamer_id, period=period, group_id=group_id)
    with _analytics_cache_lock:
        _analytics_cache[cache_key] = (time.monotonic(), data)
        _analytics_cache.move_to_end(cache_key)
        while len(_analytics_cache) > _ANALYTICS_CACHE_MAX:
            _analytics_cache.popitem(last=False)
    return data


def _load_streamers(
    data: Dict[str, Any],
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
) -> ChartViewSeries:
    if streamer_id:
        sessions = list(data.get("sessions") or [])
        rows = list(reversed(sessions[:_MAX_ROWS]))
        items: List[Tuple[str, float, float]] = []
        for session in rows:
            started = str(session.get("started_at") or "")
            label = f"#{session.get('id')} {started[5:10]}".strip()
            items.append(
                (
                    label,
                    _row_value(session, metric),
                    float(session.get("peak_viewers") or 0.0),
                )
            )
        if not items:
            return _empty_view(
                "streamers", period, metric, streamer_id, streamer_name,
                "SESSION-PERFORMANCE",
            )
        return ChartViewSeries(
            view="streamers",
            period=period,
            metric=metric,
            kind="hbar",
            labels=tuple(item[0] for item in items),
            values=tuple(item[1] for item in items),
            secondary=tuple(item[2] for item in items),
            title="SESSION-PERFORMANCE",
            subtitle=f"LETZTE {len(items)} SESSIONS · PEAK-VIEWER",
            total=float(data.get("totals", {}).get("total_coins" if metric == "coins" else "eur_net", 0.0) or 0.0),
            peak=max((item[1] for item in items), default=0.0),
            streamer_id=streamer_id,
            streamer_name=streamer_name,
        )

    ranking = list(data.get("streamers_ranking") or [])
    items = [
        (f"@{row.get('username') or ''}", _row_value(row, metric), _row_secondary(row, metric))
        for row in ranking
        if _row_value(row, metric) > 0
    ]
    items.sort(key=lambda item: item[1], reverse=True)
    items = items[:_MAX_ROWS]
    if not items:
        return _empty_view(
            "streamers", period, metric, streamer_id, streamer_name,
            VIEW_TITLES["streamers"],
        )
    return ChartViewSeries(
        view="streamers",
        period=period,
        metric=metric,
        kind="hbar",
        labels=tuple(item[0] for item in items),
        values=tuple(item[1] for item in items),
        secondary=tuple(item[2] for item in items),
        title=VIEW_TITLES["streamers"],
        subtitle=f"TOP {len(items)} NACH {('COINS' if metric == 'coins' else 'NETTO')}",
        total=float(data.get("totals", {}).get("total_coins" if metric == "coins" else "eur_net", 0.0) or 0.0),
        peak=max((item[1] for item in items), default=0.0),
        streamer_id=streamer_id,
        streamer_name=streamer_name,
    )


def _load_time_of_day(
    data: Dict[str, Any],
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
) -> ChartViewSeries:
    rows = list(data.get("time_of_day") or [])
    labels = tuple(str(row.get("label") or f"{int(row.get('hour', 0)):02d}:00") for row in rows)
    values = tuple(_row_value(row, metric) for row in rows)
    secondary = tuple(float(row.get("events_count") or 0.0) for row in rows)
    if not any(values):
        return _empty_view(
            "timeofday", period, metric, streamer_id, streamer_name,
            VIEW_TITLES["timeofday"],
        )
    highlight = max(range(len(values)), key=lambda idx: values[idx])
    return ChartViewSeries(
        view="timeofday",
        period=period,
        metric=metric,
        kind="vbar",
        labels=labels,
        values=values,
        secondary=secondary,
        title=VIEW_TITLES["timeofday"],
        subtitle="STUNDENWEISE VERTEILUNG",
        total=float(data.get("totals", {}).get("total_coins" if metric == "coins" else "eur_net", 0.0) or 0.0),
        peak=max(values, default=0.0),
        streamer_id=streamer_id,
        streamer_name=streamer_name,
        highlight=highlight,
    )


def _load_gifts(
    data: Dict[str, Any],
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
) -> ChartViewSeries:
    rows = list(data.get("top_gifts") or [])
    top = rows[:6]
    items: List[Tuple[str, float, float]] = [
        (
            _shorten(str(row.get("gift_name") or "Geschenk"), 18),
            _row_value(row, metric),
            float(row.get("total_quantity") or 0.0),
        )
        for row in top
    ]
    other = sum(_row_value(row, metric) for row in rows[6:])
    if other > 0:
        items.append(("Andere", other, 0.0))
    items = [item for item in items if item[1] > 0]
    if not items:
        return _empty_view(
            "gifts", period, metric, streamer_id, streamer_name,
            VIEW_TITLES["gifts"],
        )
    top_peak = max((item[1] for item in items if item[0] != "Andere"), default=0.0)
    return ChartViewSeries(
        view="gifts",
        period=period,
        metric=metric,
        kind="donut",
        labels=tuple(item[0] for item in items),
        values=tuple(item[1] for item in items),
        secondary=tuple(item[2] for item in items),
        title=VIEW_TITLES["gifts"],
        subtitle=f"TOP {min(len(top), len(items))} GESCHENKE",
        total=float(data.get("totals", {}).get("total_coins" if metric == "coins" else "eur_net", 0.0) or 0.0),
        peak=top_peak,
        streamer_id=streamer_id,
        streamer_name=streamer_name,
    )


def _load_gifters(
    data: Dict[str, Any],
    period: str,
    metric: str,
    streamer_id: Optional[int],
    streamer_name: str,
) -> ChartViewSeries:
    rows = list(data.get("top_gifters") or [])
    items = [
        (f"@{row.get('sender_username') or ''}", _row_value(row, metric), _row_secondary(row, metric))
        for row in rows
        if _row_value(row, metric) > 0
    ]
    items.sort(key=lambda item: item[1], reverse=True)
    items = items[:_MAX_ROWS]
    if not items:
        return _empty_view(
            "gifters", period, metric, streamer_id, streamer_name,
            VIEW_TITLES["gifters"],
        )
    return ChartViewSeries(
        view="gifters",
        period=period,
        metric=metric,
        kind="hbar",
        labels=tuple(item[0] for item in items),
        values=tuple(item[1] for item in items),
        secondary=tuple(item[2] for item in items),
        title=VIEW_TITLES["gifters"],
        subtitle=f"TOP {len(items)} NACH {('COINS' if metric == 'coins' else 'NETTO')}",
        total=float(data.get("totals", {}).get("total_coins" if metric == "coins" else "eur_net", 0.0) or 0.0),
        peak=max((item[1] for item in items), default=0.0),
        streamer_id=streamer_id,
        streamer_name=streamer_name,
    )


_LOADERS = {
    "streamers": _load_streamers,
    "timeofday": _load_time_of_day,
    "gifts": _load_gifts,
    "gifters": _load_gifters,
}


def load_chart_view(
    view: str = DEFAULT_CHART_VIEW,
    period: str = "24h",
    metric: str = "eur",
    streamer_id: Optional[int] = None,
    streamer_name: str = "",
    force_refresh: bool = False,
    group_id: Optional[int] = None,
    group_name: str = "",
) -> ChartViewSeries:
    """Lädt die Daten einer Chart-Ansicht und normalisiert sie fürs Rendering."""
    norm_view = normalize_view(view)
    norm_period = normalize_period(period)
    norm_metric = normalize_metric(metric)
    clean_name = str(streamer_name or "").strip().lstrip("@")[:32]
    clean_group = str(group_name or "").strip()[:48]

    if norm_view == "timeline":
        timeline_series: ChartSeries = load_chart_series(
            norm_period,
            norm_metric,
            streamer_id,
            clean_name,
            force_refresh,
            group_id,
            clean_group,
        )
        return ChartViewSeries(
            view="timeline",
            period=timeline_series.period,
            metric=timeline_series.metric,
            kind="line",
            labels=timeline_series.labels,
            values=timeline_series.values,
            secondary=(),
            title=VIEW_TITLES["timeline"],
            subtitle="",
            total=timeline_series.total,
            peak=timeline_series.peak,
            streamer_id=timeline_series.streamer_id,
            streamer_name=timeline_series.streamer_name,
            group_id=timeline_series.group_id,
            group_name=timeline_series.group_name,
            caption_override=chart_caption(timeline_series),
        )

    data = _load_analytics(streamer_id, norm_period, force_refresh, group_id)
    loader = _LOADERS[norm_view]
    series = loader(data, norm_period, norm_metric, streamer_id, clean_name)
    if group_id or clean_group:
        from dataclasses import replace

        series = replace(
            series,
            group_id=group_id,
            group_name=clean_group,
        )
    return series


def _widget_ticks(labels: Sequence[str]) -> List[Tuple[int, str]]:
    count = len(labels)
    if not count:
        return []
    if count == 1:
        return [(0, labels[0])]
    indexes = sorted({0, round((count - 1) / 3), round((count - 1) * 2 / 3), count - 1})
    return [(idx, labels[idx]) for idx in indexes]


def _render_hbar_html(series: ChartViewSeries) -> str:
    peak = series.peak or 1.0
    rows: List[str] = []
    for index, label in enumerate(series.labels):
        value = series.values[index]
        width = max(1.5, (value / peak) * 100.0)
        rows.append(
            f'<div class="hr"><span class="hn">{html.escape(label)}</span>'
            f'<span class="hw"><span class="hf" style="width:{width:.1f}%"></span></span>'
            f'<span class="ht">{html.escape(_format_value(value, series.metric))}</span></div>'
        )
    return "".join(rows)


def _render_vbar_html(series: ChartViewSeries) -> str:
    count = len(series.values)
    if not count:
        return ""
    peak = series.peak or 1.0
    width, height = 320.0, 110.0
    top, bottom = 4.0, height - 6.0
    slot = width / count
    bar_w = slot * 0.62
    bars: List[str] = []
    for index, value in enumerate(series.values):
        bar_h = (float(value) / peak) * (bottom - top)
        x = slot * index + (slot - bar_w) / 2
        cls = "barhi" if index == series.highlight else "bar"
        bars.append(
            f'<rect class="{cls}" x="{x:.1f}" y="{bottom - bar_h:.1f}" '
            f'width="{bar_w:.1f}" height="{max(bar_h, 0.0):.1f}"/>'
        )
    grid = "".join(
        f'<line class="gr" x1="0" y1="{gy:.1f}" x2="{width:.0f}" y2="{gy:.1f}"/>'
        for gy in (top, (top + bottom) / 2, bottom)
    )
    ticks = _widget_ticks(series.labels)
    tick_html = '<div class="xl">' + "".join(
        f"<span>{html.escape(label)}</span>" for _, label in ticks
    ) + "</div>"
    return (
        f'<svg class="cv" viewBox="0 0 320 110" preserveAspectRatio="none">'
        f"{grid}{''.join(bars)}</svg>{tick_html}"
    )


def _render_donut_html(series: ChartViewSeries) -> str:
    total = sum(series.values) or 1.0
    offset = 25.0
    circles: List[str] = []
    legend: List[str] = []
    for index, label in enumerate(series.labels):
        value = series.values[index]
        pct = value / total * 100.0
        color = _PALETTE[index % len(_PALETTE)]
        circles.append(
            f'<circle cx="21" cy="21" r="15.9155" fill="none" stroke="{color}" '
            f'stroke-width="8" stroke-dasharray="{max(pct - 0.6, 0.0):.2f} '
            f'{100 - max(pct - 0.6, 0.0):.2f}" stroke-dashoffset="{offset:.2f}"/>'
        )
        offset -= pct
        legend.append(
            f'<div class="li"><span class="sq" style="background:{color}"></span>'
            f'<span class="ln2">{html.escape(label)}</span>'
            f'<span class="lv">{pct:.0f}%</span></div>'
        )
    return (
        f'<div class="dn"><svg class="dch" viewBox="0 0 42 42">{"".join(circles)}</svg>'
        f'<div class="dl">{"".join(legend)}</div></div>'
    )


def _render_widget_body(series: ChartViewSeries) -> Tuple[str, int]:
    if series.kind == "hbar":
        chart = _render_hbar_html(series)
        height = max(250, 118 + 19 * len(series.values))
    elif series.kind == "vbar":
        chart = _render_vbar_html(series)
        height = 250
    elif series.kind == "donut":
        chart = _render_donut_html(series)
        height = 250
    else:  # pragma: no cover - timeline läuft über shared.widget_chart
        chart = ""
        height = 232

    info = (
        f"PEAK {series.peak_text} · {len(series.values)} EINTRÄGE"
        if series.values
        else "Keine Daten im Zeitraum."
    )
    html_source = (
        "<!doctype html><html><head><style>"
        + _WIDGET_CSS
        + "</style></head><body>"
        + f'<div class="tt">{html.escape(series.title_text)}</div>'
        + f'<div class="vv">{html.escape(series.total_text)}</div>'
        + f'<div class="ii">{html.escape(info)}</div>'
        + chart
        + "</body></html>"
    )
    return html_source, height


def build_chart_view_widget(
    view: str = DEFAULT_CHART_VIEW,
    period: str = "24h",
    metric: str = "eur",
    streamer_id: Optional[int] = None,
    streamer_name: str = "",
    force_refresh: bool = False,
    group_id: Optional[int] = None,
    group_name: str = "",
) -> "ChartWidget":
    """Rendert eine zusätzliche Chart-Ansicht als Telegram-HTML-Widget."""
    norm_view = normalize_view(view)
    if norm_view == "timeline":  # Kompatibilität: Zeitreihe bleibt im Altpfad.
        from shared.widget_chart import build_chart_widget

        return build_chart_widget(
            period,
            metric,
            streamer_id,
            streamer_name,
            force_refresh,
            "timeline",
            group_id,
            group_name,
        )

    from shared.widget_chart import ChartWidget

    series = load_chart_view(
        norm_view,
        period,
        metric,
        streamer_id,
        streamer_name,
        force_refresh,
        group_id,
        group_name,
    )
    html_source, height = _render_widget_body(series)
    ensure_widget_limits(html_source)
    return ChartWidget(
        html=html_source,
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
        height=height,
        view=series.view,
        view_label=series.view_label,
    )
