"""
System-Endpunkte: Einstellungen und Demo-Daten.
"""

import logging

from fastapi import APIRouter, Depends

from config import config
from schemas import SettingsUpdateRequest
from shared.api_deps import require_permission
from shared.bus import get_bus
from shared.contracts import CHANNEL_SETTINGS_CHANGED
from shared.database import (
    clear_demo_data,
    get_settings,
    init_db,
    seed_demo_data,
    update_settings,
)
from shared.permissions import PERM_SETTINGS_MANAGE, PERM_SYSTEM_MANAGE

logger = logging.getLogger("toktracker.system")

router = APIRouter()


@router.get("/api/settings", tags=["System & Workers"], dependencies=[Depends(require_permission(PERM_SETTINGS_MANAGE))])
def api_get_settings():
    init_db()
    return get_settings()


@router.post("/api/settings", tags=["System & Workers"], dependencies=[Depends(require_permission(PERM_SETTINGS_MANAGE))])
def api_update_settings(payload: SettingsUpdateRequest):
    init_db()
    updated = update_settings(payload.model_dump(exclude_none=True))
    if config.has_redis:
        try:
            get_bus().publish_sync(CHANNEL_SETTINGS_CHANGED, {"action": "settings_changed"})
        except Exception:
            pass
    return {"ok": True, "settings": updated}


@router.post("/api/demo/seed", tags=["Dashboard & Data"], dependencies=[Depends(require_permission(PERM_SYSTEM_MANAGE))])
def api_seed_demo():
    init_db()
    seed_demo_data()
    return {"ok": True, "message": "Demo-Daten geladen."}


@router.post("/api/demo/clear", tags=["Dashboard & Data"], dependencies=[Depends(require_permission(PERM_SYSTEM_MANAGE))])
def api_clear_demo():
    init_db()
    removed = clear_demo_data()
    return {"ok": True, "removed": removed}
