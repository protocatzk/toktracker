"""
System-Endpunkte: Einstellungen, Demo-Daten und SQLite-Import.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import config
from schemas import SettingsUpdateRequest, SqliteImportRequest
from shared.api_deps import require_permission
from shared.bus import get_bus
from shared.contracts import CHANNEL_SETTINGS_CHANGED
from shared.database import (
    clear_demo_data,
    get_settings,
    import_from_sqlite_database,
    init_db,
    inspect_sqlite_database,
    seed_demo_data,
    update_settings,
)
from shared.monitor_client import monitor_client as monitor_manager
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


@router.get(
    "/api/admin/sqlite/inspect",
    tags=["System & Workers"],
    summary="Untersucht eine SQLite-Datei vor dem Import (Standard: tiktok_earnings.db)",
    dependencies=[Depends(require_permission(PERM_SYSTEM_MANAGE))],
)
def api_sqlite_inspect(file_path: Optional[str] = Query(None)):
    target_path = file_path.strip() if file_path and file_path.strip() else config.db_path
    if not os.path.exists(target_path):
        raise HTTPException(
            status_code=404,
            detail=f"SQLite-Datei '{target_path}' wurde auf dem Server nicht gefunden."
        )
    try:
        inspection = inspect_sqlite_database(target_path)
        # Zusätzliche Info über aktuelle Ziel-Datenbank
        inspection["target_db"] = {
            "engine": config.db_engine,
            "target": (
                f"{config.mysql_user}@{config.mysql_host}:{config.mysql_port}/{config.mysql_database}"
                if config.is_mysql
                else os.path.basename(config.db_path)
            ),
        }
        return {"ok": True, "data": inspection}
    except Exception:
        logger.exception("SQLite-Analyse fehlgeschlagen")
        raise HTTPException(
            status_code=500,
            detail="Die SQLite-Datei konnte nicht analysiert werden. Details stehen im Server-Log.",
        ) from None


@router.post(
    "/api/admin/sqlite/import",
    tags=["System & Workers"],
    summary="Führt den Datenimport aus der SQLite-Datei in die aktive Datenbank aus",
    dependencies=[Depends(require_permission(PERM_SYSTEM_MANAGE))],
)
def api_sqlite_import(payload: Optional[SqliteImportRequest] = None):
    init_db()
    req = payload or SqliteImportRequest()
    target_path = (req.file_path or "").strip() or config.db_path
    if not os.path.exists(target_path):
        raise HTTPException(
            status_code=404,
            detail=f"SQLite-Datei '{target_path}' wurde auf dem Server nicht gefunden."
        )

    try:
        result = import_from_sqlite_database(
            sqlite_file_path=target_path,
            import_tables=req.tables,
            mode=req.mode,
        )
        # Nach dem Import auto-start für neu importierte Streamer triggern
        try:
            monitor_manager.autostart_from_db(force=True)
        except Exception:
            pass
        return {"ok": True, "result": result}
    except Exception:
        logger.exception("SQLite-Import fehlgeschlagen")
        raise HTTPException(
            status_code=500,
            detail="Der SQLite-Import ist fehlgeschlagen. Details stehen im Server-Log.",
        ) from None
