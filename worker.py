"""
TokTracker - Dedizierter TikTokLive Monitoring Worker Service
============================================================
Dieser Service läuft als eigenständiger Prozess / Docker-Container (toktracker_worker)
und übernimmt das gesamte TikTok-Livestream-Monitoring, WebSocket-Handling und
Event-Persistieren in die zentrale MariaDB / SQLite Datenbank.

Bietet eine schlanke interne HTTP-API auf Port 5001 für Healthchecks,
System-Diagnosen und sofortige Start/Stopp-Befehle durch das Web-Dashboard.
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, Query, Response
from pydantic import BaseModel

try:
    import uvloop
    uvloop.install()
    UVLOOP_AVAILABLE = True
except Exception:
    uvloop = None  # type: ignore
    UVLOOP_AVAILABLE = False

from config import config
from database import get_db, init_db
from tiktok_service import monitor_manager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] toktracker_worker: %(message)s",
)
logger = logging.getLogger("toktracker_worker")

WORKER_PORT = int(os.getenv("WORKER_PORT", "5001"))
_sync_task: Optional[asyncio.Task] = None
_running = True


async def _db_sync_loop() -> None:
    """
    Periodischer Synchronisations-Loop:
    Prüft alle 5 Sekunden die Datenbank auf Änderungen an Streamern (Tracking aktiv/inaktiv),
    sodass Tracking-Aktionen aus dem Web-Panel oder Telegram-Bot automatisch und verzögerungsfrei
    vom Worker übernommen werden.
    """
    logger.info("DB-Synchronisations-Loop aktiv (Intervall: 5s)...")
    while _running:
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, username, is_tracking, auto_monitor FROM streamers"
                ).fetchall()

            for r in rows:
                sid = int(r["id"])
                uname = str(r["username"]).strip().lstrip("@").lower()
                should_track = bool(r["is_tracking"] or r["auto_monitor"])
                is_currently_tracked = monitor_manager.is_tracking(uname)

                if should_track and not is_currently_tracked:
                    logger.info("Starte Tracking für @%s laut DB...", uname)
                    monitor_manager.start_tracking(
                        streamer_id=sid,
                        username=uname,
                        auto_reconnect=bool(r["auto_monitor"]),
                    )
                elif not should_track and is_currently_tracked:
                    logger.info("Stoppe Tracking für @%s laut DB...", uname)
                    monitor_manager.stop_tracking(username=uname, preserve_db_state=False)

        except Exception as exc:
            logger.debug("Fehler im DB-Sync-Loop: %s", exc)

        await asyncio.sleep(5.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sync_task, _running
    _running = True
    logger.info("TokTracker Worker-Service startet...")
    init_db()

    # 1. Alle aktiven Streamer aus der DB starten
    started = monitor_manager.autostart_from_db(force=True)
    logger.info("Auto-Start abgeschlossen: %d Streamer initialisiert.", len(started))

    # 2. Hintergrund-Sync starten
    _sync_task = asyncio.create_task(_db_sync_loop())

    yield

    # Shutdown
    _running = False
    if _sync_task:
        _sync_task.cancel()
    logger.info("TokTracker Worker-Service fährt herunter... Stoppe alle TikTok-Verbindungen.")
    monitor_manager.stop_all(preserve_db_state=True)


app = FastAPI(
    title="TokTracker Worker Service",
    description="Interner TikTok Live Stream Monitoring Daemon",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check():
    diag = monitor_manager.get_all_diagnostics()
    return {
        "ok": True,
        "service": "toktracker_worker",
        "loop_engine": "uvloop" if UVLOOP_AVAILABLE else "asyncio",
        "workers_total": diag.get("workers_total", 0),
        "workers_running": diag.get("workers_running", 0),
        "workers_connected": diag.get("workers_connected", 0),
    }


@app.get("/api/diagnostics", tags=["Diagnostics"])
async def get_diagnostics():
    """Liefert die vollständige System- und Worker-Diagnose für das Web-Dashboard."""
    return monitor_manager.get_all_diagnostics()


@app.get("/api/diagnostics/{username}", tags=["Diagnostics"])
async def get_streamer_diagnostics(username: str):
    """Liefert die Diagnose für einen spezifischen Streamer."""
    clean = username.strip().lstrip("@").lower()
    diag = monitor_manager.get_worker_diagnostics(clean)
    is_tracking = monitor_manager.is_tracking(clean)
    status = monitor_manager.get_status(clean)
    return {
        "username": clean,
        "is_tracking": is_tracking,
        "status": status,
        "diagnostics": diag,
    }


class TrackingRequest(BaseModel):
    streamer_id: int
    username: str
    auto_reconnect: bool = True


@app.post("/api/tracking/start", tags=["Control"])
async def start_tracking(payload: TrackingRequest):
    """Startet das Tracking für einen Streamer sofort."""
    clean = payload.username.strip().lstrip("@").lower()
    res = monitor_manager.start_tracking(
        streamer_id=payload.streamer_id,
        username=clean,
        auto_reconnect=payload.auto_reconnect,
    )
    return {"ok": True, "result": res}


@app.post("/api/tracking/stop", tags=["Control"])
async def stop_tracking(
    username: str = Query(..., description="TikTok Nutzername"),
    preserve_db_state: bool = Query(False),
):
    """Beendet das Tracking für einen Streamer sofort."""
    clean = username.strip().lstrip("@").lower()
    res = monitor_manager.stop_tracking(clean, preserve_db_state=preserve_db_state)
    return {"ok": True, "result": res}


@app.post("/api/sync", tags=["Control"])
async def trigger_sync():
    """Löst eine sofortige Synchronisierung mit der Datenbank aus."""
    started = monitor_manager.autostart_from_db(force=True)
    return {"ok": True, "restarted": started}


def main():
    loop_name = "uvloop" if UVLOOP_AVAILABLE else "asyncio"
    logger.info("Starte Worker auf Port %d (Event-Loop: %s)...", WORKER_PORT, loop_name)
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT, log_level="info", loop="uvloop" if UVLOOP_AVAILABLE else "auto")


if __name__ == "__main__":
    main()
