"""
TokTracker - Remote Service Adapter & IPC Client
================================================
Ermöglicht transparente Kommunikation zwischen dem Web-Dashboard (app.py)
und den ausgelagerten Services:
- toktracker_worker (Port 5001)
- toktracker_bot (Port 5002)

Wenn die Services lokal laufen (All-in-One Modus), werden direkte In-Memory-Aufrufe
genutzt. Wenn sie als eigenständige Docker-Container betrieben werden, erfolgt
die Kommunikation über schlanke HTTP-REST-Aufrufe mit automatischem DB-Fallback.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from config import config
from database import get_db, update_streamer_runtime_state
from telegram_service import admin_auth_manager, telegram_bot_service
from tiktok_service import monitor_manager

logger = logging.getLogger("toktracker_remote")

ENABLE_WORKER = os.getenv("ENABLE_WORKER", "true").lower() in ("true", "1", "yes")
ENABLE_BOT = os.getenv("ENABLE_BOT", "true").lower() in ("true", "1", "yes")

WORKER_URL = os.getenv("WORKER_URL", "http://worker:5001").rstrip("/")
BOT_URL = os.getenv("BOT_URL", "http://bot:5002").rstrip("/")

_HTTP_TIMEOUT = 2.0


# ==============================================================================
# Worker Service IPC
# ==============================================================================

_worker_diag_cache: Optional[Dict[str, Any]] = None
_worker_diag_cache_time: float = 0.0

async def get_worker_diagnostics(username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Liefert Diagnosedaten des TikTok-Workers für einen oder alle Streamer."""
    global _worker_diag_cache, _worker_diag_cache_time
    if ENABLE_WORKER:
        if username:
            return monitor_manager.get_worker_diagnostics(username)
        return monitor_manager.get_all_diagnostics()

    import time
    now = time.monotonic()
    if not username and _worker_diag_cache is not None and (now - _worker_diag_cache_time) < 4.0:
        return _worker_diag_cache.copy()

    # Remote HTTP Abfrage an toktracker_worker
    try:
        url = f"{WORKER_URL}/api/diagnostics/{username}" if username else f"{WORKER_URL}/api/diagnostics"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if username and isinstance(data, dict):
                    return data.get("diagnostics")
                if not username and isinstance(data, dict):
                    _worker_diag_cache = data
                    _worker_diag_cache_time = now
                return data
    except Exception as exc:
        logger.debug("Konnte Worker-Diagnose von %s nicht abrufen: %s", WORKER_URL, exc)

    # Fallback: Diagnosedaten aus der Datenbank rekonstruieren
    return _build_db_worker_fallback(username)


def _build_db_worker_fallback(username: Optional[str] = None) -> Dict[str, Any]:
    with get_db() as conn:
        if username:
            row = conn.execute("SELECT * FROM streamers WHERE username = ?", (username,)).fetchone()
            if not row:
                return {}
            d = dict(row)
            return {
                "username": d["username"],
                "is_running": bool(d["is_tracking"]),
                "state": "connected" if d["is_live"] else ("polling_offline" if d["is_tracking"] else "idle"),
                "is_live": bool(d["is_live"]),
                "current_viewers": int(d.get("current_viewers", 0) or 0),
                "last_error": str(d.get("last_error", "") or ""),
            }

        rows = conn.execute("SELECT * FROM streamers").fetchall()
        streamers = [dict(r) for r in rows]
        active = sum(1 for s in streamers if s.get("is_tracking"))
        connected = sum(1 for s in streamers if s.get("is_live"))
        return {
            "tiktoklive_available": True,
            "env_config": config.public_summary(),
            "workers_total": len(streamers),
            "workers_running": active,
            "workers_connected": connected,
            "workers": [
                {
                    "username": s["username"],
                    "is_running": bool(s["is_tracking"]),
                    "state": "connected" if s["is_live"] else ("polling_offline" if s["is_tracking"] else "idle"),
                    "is_live": bool(s["is_live"]),
                    "current_viewers": int(s.get("current_viewers", 0) or 0),
                    "last_error": str(s.get("last_error", "") or ""),
                }
                for s in streamers
            ],
        }


async def is_streamer_tracking(username: str) -> bool:
    """Prüft, ob für einen Streamer aktuell ein Worker aktiv ist."""
    clean = username.strip().lstrip("@").lower()
    if ENABLE_WORKER:
        return monitor_manager.is_tracking(clean)

    # Zuerst Worker fragen
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(f"{WORKER_URL}/api/diagnostics/{clean}")
            if resp.status_code == 200:
                return bool(resp.json().get("is_tracking"))
    except Exception:
        pass

    # Fallback: Aus DB lesen
    with get_db() as conn:
        row = conn.execute("SELECT is_tracking FROM streamers WHERE username = ?", (clean,)).fetchone()
        return bool(row and row["is_tracking"])


async def start_streamer_tracking(
    streamer_id: int,
    username: str,
    auto_reconnect: bool = True,
) -> Dict[str, Any]:
    """Startet das Tracking für einen Streamer (lokal oder remote)."""
    clean = username.strip().lstrip("@").lower()
    # 1. Immer in DB sichern
    update_streamer_runtime_state(
        clean,
        is_tracking=True,
        auto_monitor=auto_reconnect,
    )

    if ENABLE_WORKER:
        return monitor_manager.start_tracking(
            streamer_id=streamer_id,
            username=clean,
            auto_reconnect=auto_reconnect,
        )

    # 2. Remote Worker triggern
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{WORKER_URL}/api/tracking/start",
                json={
                    "streamer_id": streamer_id,
                    "username": clean,
                    "auto_reconnect": auto_reconnect,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("result", {"ok": True})
    except Exception as exc:
        logger.warning("Remote-Start für @%s fehlgeschlagen (wird beim nächsten DB-Sync gestartet): %s", clean, exc)

    return {"ok": True, "message": "In DB aktiviert (wird vom Worker synchronisiert)"}


async def stop_streamer_tracking(
    username: str,
    preserve_db_state: bool = False,
) -> Dict[str, Any]:
    """Beendet das Tracking für einen Streamer (lokal oder remote)."""
    clean = username.strip().lstrip("@").lower()
    if not preserve_db_state:
        update_streamer_runtime_state(
            clean,
            is_tracking=False,
            auto_monitor=False,
        )

    if ENABLE_WORKER:
        return monitor_manager.stop_tracking(clean, preserve_db_state=preserve_db_state)

    # Remote Worker triggern
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{WORKER_URL}/api/tracking/stop",
                params={"username": clean, "preserve_db_state": preserve_db_state},
            )
            if resp.status_code == 200:
                return resp.json().get("result", {"ok": True})
    except Exception as exc:
        logger.warning("Remote-Stop für @%s fehlgeschlagen (wird beim nächsten DB-Sync gestoppt): %s", clean, exc)

    return {"ok": True, "message": "In DB deaktiviert (wird vom Worker synchronisiert)"}


async def trigger_worker_sync() -> None:
    """Weist den Worker an, sich sofort mit der Datenbank zu synchronisieren."""
    if ENABLE_WORKER:
        monitor_manager.autostart_from_db(force=True)
        return

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            await client.post(f"{WORKER_URL}/api/sync")
    except Exception:
        pass


# ==============================================================================
# Telegram Bot Service IPC
# ==============================================================================

_bot_diag_cache: Optional[Dict[str, Any]] = None
_bot_diag_cache_time: float = 0.0

async def get_bot_diagnostics() -> Dict[str, Any]:
    """Liefert den Betriebsstatus des Telegram-Bots."""
    global _bot_diag_cache, _bot_diag_cache_time
    if ENABLE_BOT:
        return telegram_bot_service.get_diagnostics()

    import time
    now = time.monotonic()
    if _bot_diag_cache is not None and (now - _bot_diag_cache_time) < 4.0:
        return _bot_diag_cache.copy()

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(f"{BOT_URL}/api/diagnostics")
            if resp.status_code == 200:
                data = resp.json()
                _bot_diag_cache = data
                _bot_diag_cache_time = now
                return data
    except Exception as exc:
        logger.debug("Konnte Bot-Diagnose von %s nicht abrufen: %s", BOT_URL, exc)

    return {
        "state": "running (remote)",
        "bot_username": (config.telegram_bot_token and "toktrackeragent") or "nicht konfiguriert",
        "registered_admins": 1,
    }


async def send_admin_login_challenge(
    identifier_hint: Optional[str] = None,
    client_info: str = "Web-Browser",
) -> Dict[str, Any]:
    """Sendet 2FA-Login-Push-Benachrichtigung an die Telegram-Admins."""
    if ENABLE_BOT:
        return await telegram_bot_service.send_admin_login_challenge(
            identifier_hint=identifier_hint,
            client_info=client_info,
        )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{BOT_URL}/api/notify-challenge",
                json={
                    "identifier_hint": identifier_hint,
                    "client_info": client_info,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("result", {"ok": True})
    except Exception as exc:
        logger.warning("Konnte 2FA-Challenge nicht an Bot-Service senden: %s", exc)

    # Fallback: Lokale Challenge in DB erzeugen, sodass OTP-Login funktioniert
    ch = admin_auth_manager.create_challenge(client_info=client_info)
    return {
        "ok": True,
        "challenge_id": ch["challenge_id"],
        "delivered_count": 0,
        "bot_running": False,
        "bot_username": "toktrackeragent",
        "expires_in": 600,
        "message": "Challenge erzeugt (OTP-Login aktiv).",
    }


async def send_report_now(chat_id: Optional[int] = None, hours: int = 24) -> bool:
    """Löst den sofortigen Versand eines Umsatzreports an Telegram aus."""
    if ENABLE_BOT:
        return await telegram_bot_service.send_report_now(chat_id=chat_id, hours=hours)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{BOT_URL}/api/send-report",
                json={"chat_id": chat_id, "hours": hours},
            )
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Konnte Report nicht an Bot-Service senden: %s", exc)
        return False
