"""
TokTracker - Database Re-export & Abwärtskompatibilität.

Die Implementierung liegt in `shared.db` (Verbindungen, Schema, Settings,
Streamer, Gifts, Battles, Donors, Analytics, Chat, Web-Analytics, SQLite-Import).
Dieses Modul bleibt als stabile Import-Fassade erhalten:

    from database import get_db, init_db
    from shared.database import get_dashboard_overview
"""

from shared.db import *  # noqa: F401,F403
from shared.db import __all__ as __all__
