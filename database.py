"""
TokTracker - Database Re-export & Abwärtskompatibilität
Ermöglicht Importe wie `from database import get_db, init_db` sowie `from shared.database import get_db`.
"""

from shared.database import *  # noqa: F403
