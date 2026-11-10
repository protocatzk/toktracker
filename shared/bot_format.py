"""
Einheitliche Textbausteine für Telegram-Nachrichten im Industrial-Stil
der TT-INTELLIGENCE-Oberfläche.

Telegram erlaubt kein CSS. „Design“ entsteht hier deshalb über:
- Mono-Eyebrows in ``<code>`` (// TT-INTELLIGENCE · 01 / TITEL)
- ausgerichtete Kennzahlen in ``<pre>``-Blöcken
- ``<blockquote>`` als linke Führungslinie
- ein reduziertes Glyphensystem (● ○ ◆ ▸ ✓ →) statt Emoji-Ketten
"""

import html
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

BRAND = "TT-INTELLIGENCE"
BRAND_SHORT = "TT-I"
RULE = "────────────────────────"
TELEGRAM_LIMIT = 4096

# Erlaubte Status-Glyphen
LIVE = "● LIVE"
OFFLINE = "○ OFFLINE"


def esc(value: object) -> str:
    """HTML-Escaping für nutzergenerierte Werte."""
    return html.escape(str(value))


def header(index: int, title: str) -> str:
    """Abschnitts-Eyebrow im Stil der Startseite."""
    return f"<code>// {BRAND} · {index:02d} / {esc(title).upper()}</code>"


def eyebrow(label: str) -> str:
    return f"<code>// {esc(label).upper()}</code>"


def rule() -> str:
    return RULE


def kv_table(rows: Iterable[Tuple[str, str]], width: int = 34) -> str:
    """
    Monospace-Tabelle für ausgerichtete Kennzahlen.

    ``rows`` enthält (Label, Wert)-Paare. Der Block bleibt bewusst schmal,
    damit er auf Mobilgeräten ohne horizontales Scrollen lesbar ist.
    """
    lines: List[str] = []
    for label, value in rows:
        lab = str(label).upper()
        val = str(value)
        gap = max(1, width - len(lab) - len(val))
        lines.append(f"{lab}{' ' * gap}{val}")
    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def blockquote(body: str) -> str:
    return f"<blockquote>{body}</blockquote>"


def status(is_live: bool) -> str:
    return LIVE if is_live else OFFLINE


def rank(index: int) -> str:
    return f"{index:02d}"


def footer(timestamp: Optional[datetime] = None) -> str:
    ts = timestamp or datetime.now()
    return f"<code>{BRAND_SHORT} · {ts.strftime('%d.%m.%Y %H:%M')}</code>"


def case_title(title: str) -> str:
    """Überschriften bleiben im industriellen Look uppercase."""
    return f"<b>{esc(title).upper()}</b>"


def bullet(label: str, value: str) -> str:
    return f"▪ {esc(label)}: <b>{value}</b>"


def chunk_message(text: str, limit: int = TELEGRAM_LIMIT) -> Sequence[str]:
    """
    Teilt lange Reports an Absatzgrenzen in Telegram-taugliche Häppchen.

    Einzelne Absätze, die selbst zu lang sind, werden zusätzlich an
    Zeilenumbrüchen getrennt. So bleibt HTML pro Nachricht intakt.
    """
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip("\n"))
        current = ""

    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        flush()
        if len(paragraph) <= limit:
            current = paragraph
            continue
        # Sehr langer Einzelabsatz: zeilenweise aufteilen.
        for line in paragraph.split("\n"):
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= limit:
                current = candidate
            else:
                flush()
                current = line
    flush()
    return chunks or [text[:limit]]
