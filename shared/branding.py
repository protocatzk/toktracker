"""
Zentrale Marken-Definitionen für die sichtbare Oberfläche.

Die technische Infrastruktur (Cookies, localStorage-Keys, Redis-Prefixe,
Docker-Services, Datenbank-Namen) bleibt bewusst unter dem historischen
Namen ``toktracker``. Nur die nach außen sichtbaren Strings werden hier
gebündelt, damit die Umbenennung auf ``TT-INTELLIGENCE`` schrittweise
erfolgen kann.
"""

from typing import Dict

# Marke (durchgehend uppercase, industrieller Stil der Startseite)
BRAND_NAME = "TT-INTELLIGENCE"
BRAND_WORDMARK = "TT-INTELLIGENCE"
BRAND_SHORT = "TT-I"
BRAND_TAGLINE = "LIVE EARNINGS INTELLIGENCE"
BRAND_LEGACY = "toktracker"

# Technische Bezeichner, die aus Kompatibilitätsgründen NICHT umbenannt werden.
LEGACY_SESSION_COOKIE = "toktracker_session"
LEGACY_STORAGE_PREFIX = "toktracker_"


def brand_context() -> Dict[str, str]:
    """Kontext-Dictionary für Jinja-Templates."""
    return {
        "brand_name": BRAND_NAME,
        "brand_wordmark": BRAND_WORDMARK,
        "brand_short": BRAND_SHORT,
        "brand_tagline": BRAND_TAGLINE,
        "brand_legacy": BRAND_LEGACY,
    }
