"""
TokTracker - Schemas Re-export & Abwärtskompatibilität
Ermöglicht Importe wie `from schemas import StreamerCreate` sowie `from shared.schemas import StreamerCreate`.

Ablauf: Diese Fassade entfällt mit v2.0. Bis dahin bleiben die Importpfade
stabil; neuer Code importiert direkt aus `shared.schemas`.
"""

from shared.schemas import *  # noqa: F403
