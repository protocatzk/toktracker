"""
TokTracker - Database Re-export & Abwärtskompatibilität
Ermöglicht Importe wie `from database import get_db, init_db` sowie `from shared.database import get_db`.

Ablauf: Diese Fassade entfällt mit v2.0. Bis dahin bleiben die Importpfade
stabil; neuer Code importiert direkt aus `shared.database`.
"""

from shared.database import *  # noqa: F403
