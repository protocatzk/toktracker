"""
Telegram HTML-Widgets für Einnahmen-Charts (Bot API 10.4).

Widgets laufen in einer QuickJS-Sandbox ohne Netzwerkzugriff. Der HTML-Code
ist nach dem Senden unveränderlich; nur der ``chat_data``-State (max. 1024
Bytes) darf per ``editMessageWidgetData`` aktualisiert werden. Deshalb ist
das HTML hier ein generischer Renderer und alle Unterschiede (Zeitraum,
Metrik, Werte) stecken im State.

Die Telegram-Grenzen werden vor dem Senden geprüft:
- 32.768 Bytes HTML
- 4.096 Bytes nach zlib-Level-9
- 1.024 Bytes State
"""

from __future__ import annotations

import base64
import json
import struct
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

WIDGET_MAX_HTML_BYTES = 32768
WIDGET_MAX_COMPRESSED_BYTES = 4096
WIDGET_MAX_STATE_BYTES = 1024
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

# Statisches HTML: liest ausschließlich TelegramWidget.chatData und zeichnet
# daraus eine Fläche mit Achsenraster, Zeitlabels und Tap-Readout.
WIDGET_HTML = """<!doctype html><html><head><style>
body{margin:0;padding:8px 12px;font:14px/1.35 system-ui,sans-serif;color:var(--tg-theme-text-color);user-select:none}
.hd{display:flex;flex-direction:column;gap:1px}
.tt{font-size:11px;letter-spacing:.04em;color:var(--tg-theme-hint-color)}
.vv{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.ii{font-size:11px;color:var(--tg-theme-hint-color);min-height:14px}
svg{display:block;width:100%;height:110px;margin:6px 0 2px;touch-action:pan-y}
.xl{display:flex;justify-content:space-between;gap:4px;font-size:10px;color:var(--tg-theme-hint-color)}
.gr{stroke:var(--tg-theme-section-separator-color);stroke-width:1}
.ar{fill:var(--tg-theme-button-color);fill-opacity:.14}
.ln{fill:none;stroke:var(--tg-theme-button-color);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.pt{fill:var(--tg-theme-button-color)}
</style></head><body>
<div class="hd"><div class="tt" id="title"></div><div class="vv" id="value"></div><div class="ii" id="info"></div></div>
<svg id="chart" viewBox="0 0 300 110"></svg>
<div class="xl" id="labels"></div>
<script>
const W=window.TelegramWidget||{chatData:null,onEvent:function(){},ready:function(){}};
const svg=document.getElementById('chart'),title=document.getElementById('title'),value=document.getElementById('value'),info=document.getElementById('info'),labels=document.getElementById('labels');
let data={},vals=[],peak=1;
function decode(b64){const s=atob(b64||'');const a=new Uint8Array(s.length);for(let i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return new Uint16Array(a.buffer)}
function fmt(v){return data.f==='eur'?'€ '+v.toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2}):Math.round(v).toLocaleString('de-DE')}
function add(tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);svg.appendChild(e);return e}
function draw(){
  const w=Math.max(220,svg.clientWidth||300),h=110,n=vals.length;
  svg.setAttribute('viewBox','0 0 '+w+' '+h);svg.textContent='';
  if(!n){svg.style.display='none';labels.textContent='';return}
  svg.style.display='block';
  const x=i=>n<2?0:i/(n-1)*w,y=v=>h-6-(v/60000)*(h-12);
  for(let i=0;i<3;i++){const gy=h-6-i*(h-12)/2;add('line',{class:'gr',x1:0,y1:gy,x2:w,y2:gy})}
  let line='',area='';
  for(let i=0;i<n;i++){const px=x(i),py=y(vals[i]);line+=(i?'L':'M')+px.toFixed(1)+' '+py.toFixed(1);area+=(i?'L':'M')+px.toFixed(1)+' '+(i?py:h-6)+' '}
  area+='L'+w.toFixed(1)+' '+(h-6)+'L0 '+(h-6)+'Z';
  if(n>1)add('path',{class:'ar',d:area});
  add('path',{class:'ln',d:line});
  add('circle',{class:'pt',cx:x(n-1),cy:y(vals[n-1]),r:2.5});
  const idx=n<2?[0]:[0,Math.round((n-1)/3),Math.round((n-1)*2/3),n-1];
  labels.textContent='';idx.forEach((p,i)=>{const s=document.createElement('span');s.textContent=(data.lb||[])[p]||'';if(i===1||i===2)s.style.textAlign='center';labels.appendChild(s)});
}
function boot(){
  try{data=JSON.parse(W.chatData||'{}')}catch(e){data={}}
  vals=decode(data.v);peak=+data.mx||1;
  title.textContent=(data.t||'')+(data.m?' · '+data.m:'');
  value.textContent=fmt(+data.tot||0);
  info.textContent=vals.length?'PEAK '+fmt(peak):'Keine Daten im Zeitraum.';
  draw();
  if(W.ready)W.ready();
}
svg.addEventListener('pointerdown',e=>{
  if(!vals.length)return;
  const r=svg.getBoundingClientRect(),n=vals.length;
  const i=Math.max(0,Math.min(n-1,Math.round((e.clientX-r.left)/r.width*(n-1))));
  info.textContent=((data.lb||[])[i]||'')+' · '+fmt(vals[i]*peak/60000);
});
if(window.ResizeObserver){let last=0;new ResizeObserver(()=>{const w=svg.clientWidth;if(Math.abs(w-last)>2){last=w;draw()}}).observe(svg)}
if(W.onEvent)W.onEvent('chatDataChanged',boot);
boot();
</script></body></html>"""


@dataclass(frozen=True)
class ChartWidget:
    """Fertiges Chart-Widget inklusive State und Caption."""

    html: str
    state: str
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
    """HTML oder State überschreitet eine Telegram-Widget-Grenze."""


def normalize_period(value: Optional[str]) -> str:
    return _PERIOD_ALIASES.get((value or "").strip().lower(), "24h")


def normalize_metric(value: Optional[str]) -> str:
    return _METRIC_ALIASES.get((value or "").strip().lower(), "eur")


def encode_series(values: Sequence[float]) -> Tuple[str, float]:
    """
    Packt Werte als uint16-Base64 und liefert den echten Peak zurück.

    Der Skalierungsfaktor steckt implizit in ``peak / 60000``; der Client
    rechnet jeden Punkt damit zurück. Das reicht für 24-31 Buckets deutlich
    unter dem 1024-Byte-State-Limit.
    """
    peak = max((float(v) for v in values), default=0.0)
    if peak <= 0 or not values:
        return "", 0.0
    scale = peak / 60000.0
    quantized = [
        max(0, min(65535, int(round(float(v) / scale))))
        for v in values
    ]
    raw = struct.pack("<" + "H" * len(quantized), *quantized)
    return base64.b64encode(raw).decode("ascii"), peak


def decode_series(encoded: str) -> List[int]:
    """Nur für Tests/Diagnose: Base64-State zurück in uint16-Werte."""
    if not encoded:
        return []
    raw = base64.b64decode(encoded.encode("ascii"))
    return list(struct.unpack("<" + "H" * (len(raw) // 2), raw))


def widget_sizes(html: str) -> Tuple[int, int]:
    """(Rohbytes, zlib-9-Bytes) – identisch zur Zählweise von Telegram."""
    raw = html.encode("utf-8")
    return len(raw), len(zlib.compress(raw, 9))


def ensure_widget_limits(html: str, state: str) -> None:
    raw, compressed = widget_sizes(html)
    if raw > WIDGET_MAX_HTML_BYTES:
        raise WidgetLimitError(f"Widget-HTML zu groß: {raw} > {WIDGET_MAX_HTML_BYTES} Bytes")
    if compressed > WIDGET_MAX_COMPRESSED_BYTES:
        raise WidgetLimitError(
            f"Widget-HTML komprimiert zu groß: {compressed} > {WIDGET_MAX_COMPRESSED_BYTES} Bytes"
        )
    state_bytes = len(state.encode("utf-8"))
    if state_bytes > WIDGET_MAX_STATE_BYTES:
        raise WidgetLimitError(
            f"Widget-State zu groß: {state_bytes} > {WIDGET_MAX_STATE_BYTES} Bytes"
        )


def format_eur(value: float) -> str:
    """Deutsche Zahlformatierung (1.234,56)."""
    formatted = f"{float(value):,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_coins(value: float) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def _load_timeline(period: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # Lazy import: haelt das Modul unabhaengig von der DB-Fassade und
    # vermeidet Zyklen beim App-Import.
    from database import get_analytics_data

    data = get_analytics_data(period=period)
    timeline = data.get("timeline") or []
    totals = data.get("totals") or {}
    return list(timeline), dict(totals)


def build_chart_widget(period: str = "24h", metric: str = "eur") -> ChartWidget:
    """Lädt die Zeitreihe und baut daraus State, Caption und HTML."""
    norm_period = normalize_period(period)
    norm_metric = normalize_metric(metric)

    timeline, totals = _load_timeline(norm_period)
    metric_key = "total_coins" if norm_metric == "coins" else "eur_net"

    values: List[float] = []
    labels: List[str] = []
    for row in timeline:
        try:
            values.append(max(0.0, float(row.get(metric_key) or 0.0)))
        except (TypeError, ValueError):
            values.append(0.0)
        labels.append(str(row.get("label") or "")[:12])

    encoded, peak = encode_series(values)
    total = float(totals.get(metric_key) or 0.0)

    state_payload = {
        "f": norm_metric,
        "t": PERIOD_LABELS.get(norm_period, norm_period.upper()),
        "m": METRIC_LABELS.get(norm_metric, norm_metric.upper()),
        "v": encoded,
        "mx": round(peak, 4),
        "tot": round(total, 2),
        "lb": labels,
    }
    state = json.dumps(state_payload, separators=(",", ":"), ensure_ascii=False)
    ensure_widget_limits(WIDGET_HTML, state)

    caption = (
        "📈 TT-INTELLIGENCE · EINNAHMEN-CHART\n"
        "Tippe auf den Chart für Werte · /chart 24h | 7d | 30d"
    )
    return ChartWidget(
        html=WIDGET_HTML,
        state=state,
        caption=caption,
        period=norm_period,
        metric=norm_metric,
        total=total,
        peak=peak,
        points=len(values),
    )
