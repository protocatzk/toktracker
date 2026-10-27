"""
TokTracker - Datenschutz-Helfer für öffentliche Datenflächen.

Das öffentliche Panel (`/`, `/public`) und die Mini-App sind bewusst ohne Login
nutzbar. Spender-Namen sind dort ein optionales Feature und werden über das
Setting `public_show_donors` (Default: 0 = maskiert) gesteuert.

Die Maskierung ist deterministisch (gleicher Name -> gleiche Maske), damit
Aggregationen im UI konsistent bleiben, aber keine Rückschlüsse auf die
vollständige Identität möglich sind.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# Felder, in denen Spender-Identitäten in API-Antworten auftauchen können.
DONOR_NAME_FIELDS = (
    "sender_username",
    "sender_nickname",
    "username",
    "nickname",
)


def mask_name(value: Optional[str]) -> str:
    """Maskiert einen Namen: 'maxmuster' -> 'm********r'."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) == 1:
        return "*"
    if len(raw) == 2:
        return f"{raw[0]}*"
    if len(raw) <= 4:
        return f"{raw[0]}{'*' * (len(raw) - 1)}"
    return f"{raw[0]}{'*' * (len(raw) - 2)}{raw[-1]}"


def mask_donor_rows(
    rows: Optional[Iterable[Any]],
    fields: Iterable[str] = DONOR_NAME_FIELDS,
) -> List[Dict[str, Any]]:
    """Gibt Kopien der Zeilen zurück, in denen Spender-Namen maskiert sind."""
    masked: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            masked.append(row)
            continue
        copy = dict(row)
        for field in fields:
            if field in copy and copy[field]:
                copy[field] = mask_name(copy[field])
        masked.append(copy)
    return masked


def apply_public_privacy(payload: Any, show_donors: bool) -> Any:
    """
    Entfernt/maskiert Spender-Namen in gängigen Antwort-Strukturen, wenn
    `show_donors` deaktiviert ist. Strukturen ohne entsprechende Felder bleiben unverändert.
    """
    if show_donors or not isinstance(payload, dict):
        return payload

    result = dict(payload)
    for key in ("recent_gifts", "top_gifters", "gifts"):
        if key in result and isinstance(result[key], list):
            result[key] = mask_donor_rows(result[key])
    return result
