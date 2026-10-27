"""
TokTracker - Verteiltes Rate-Limiting über den Message-Bus.

Nutzt den atomaren `incr_kv`-Zähler des Buses (Redis in Produktion, Memory-Fallback
lokal). Zähler-Schlüssel enthalten nur einen SHA-256-Auszug der Client-IP, damit keine
personenbezogenen Daten in Redis landen.

Verhalten bei Bus-Ausfall: Fail-open mit Warnung. Ein blockiertes Auth-Backend darf
den Login nicht komplett unbrauchbar machen – die Challenge-/Attempt-Logik in
`shared.auth_store` schützt zusätzlich.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from shared.bus import get_bus

logger = logging.getLogger("toktracker.ratelimit")

KEY_PREFIX = "tt:rl:"


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    hits: int
    limit: int
    retry_after: int


def _bucket_key(bucket: str, identifier: str) -> str:
    digest = hashlib.sha256((identifier or "unknown").encode("utf-8")).hexdigest()[:16]
    return f"{KEY_PREFIX}{bucket}:{digest}"


async def check_rate_limit(
    bucket: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    """Zählt einen Treffer im Fenster und meldet, ob er erlaubt ist."""
    if limit <= 0:
        return RateLimitResult(True, 0, limit, 0)

    try:
        hits = await get_bus().incr_kv(_bucket_key(bucket, identifier), ttl=window_seconds)
    except Exception as exc:  # noqa: BLE001 - Fail-open ist hier bewusst
        logger.warning("Rate-Limit-Zähler für '%s' nicht verfügbar (%s) – Anfrage wird durchgelassen.", bucket, exc)
        return RateLimitResult(True, 0, limit, 0)

    allowed = hits <= limit
    return RateLimitResult(allowed, hits, limit, 0 if allowed else window_seconds)


async def reset_rate_limit(bucket: str, identifier: str) -> None:
    """Setzt den Zähler zurück (z.B. nach erfolgreichem Login)."""
    try:
        await get_bus().delete_kv(_bucket_key(bucket, identifier))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Rate-Limit-Reset für '%s' fehlgeschlagen: %s", bucket, exc)
