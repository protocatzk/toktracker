import json
import logging
from typing import Any, Dict, List, Optional

from shared.bus import get_bus
from shared.config import config
from shared.contracts import (
    CHANNEL_COMMANDS,
    CHANNEL_RECONCILE,
    PREFIX_DIAG_WORKER,
    PREFIX_LEASE,
)
from shared.database import (
    get_auto_monitor_streamers,
    update_streamer_runtime_state,
)

logger = logging.getLogger("toktracker.monitor_client")


class MonitorClient:
    """
    Abstraktions-Client für das Streamer-Monitoring.
    - Im Monolith / Worker-Prozess: Delegiert direkt an den lokalen monitor_manager.
    - Im Web-/API-/Bot-Container: Kommuniziert transparent über Redis (PubSub & KV-Cache)
      und aktualisiert direkt die DB-Zustände.
    """

    def __init__(self):
        self._local_manager: Optional[Any] = None
        self.bus = get_bus()

    def set_local_manager(self, manager: Any) -> None:
        self._local_manager = manager

    def is_tracking(self, username: str) -> bool:
        clean = username.strip().lstrip("@").lower()
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.is_tracking(clean)

        if config.has_redis:
            raw = self.bus.get_kv_sync(f"{PREFIX_DIAG_WORKER}{clean}")
            if raw:
                try:
                    snap = json.loads(raw)
                    return bool(snap.get("is_running", False))
                except Exception:
                    pass
            # Prüfe Lease-Key
            lease = self.bus.get_kv_sync(f"{PREFIX_LEASE}{clean}")
            if lease:
                return True

        return False

    def get_status(self, username: str) -> str:
        clean = username.strip().lstrip("@").lower()
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.get_status(clean)

        if config.has_redis:
            snap = self.get_worker_diagnostics(clean)
            if snap:
                return f"[{snap.get('state', 'unknown')}] {snap.get('last_message', '')}"

        return "Inaktiv"

    def get_worker_diagnostics(self, username: str) -> Optional[Dict[str, Any]]:
        clean = username.strip().lstrip("@").lower()
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.get_worker_diagnostics(clean)

        if config.has_redis:
            raw = self.bus.get_kv_sync(f"{PREFIX_DIAG_WORKER}{clean}")
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass

        return None

    def get_all_diagnostics(self) -> Dict[str, Any]:
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.get_all_diagnostics()

        snapshots: List[Dict[str, Any]] = []
        if config.has_redis:
            keys = self.bus.scan_keys_sync(f"{PREFIX_DIAG_WORKER}*")
            for k in keys:
                raw = self.bus.get_kv_sync(k)
                if raw:
                    try:
                        snapshots.append(json.loads(raw))
                    except Exception:
                        pass

        active_count = sum(1 for s in snapshots if s.get("is_running"))
        connected_count = sum(1 for s in snapshots if s.get("state") == "connected")

        return {
            "tiktoklive_available": True,
            "env_config": config.public_summary(),
            "workers_total": len(snapshots),
            "workers_running": active_count,
            "workers_connected": connected_count,
            "workers": snapshots,
        }

    def autostart_from_db(self, force: bool = False) -> List[str]:
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.autostart_from_db(force=force)

        # Trigger Ingest Worker über Redis PubSub
        if config.has_redis:
            self.bus.publish_sync(CHANNEL_RECONCILE, {"action": "reconcile", "force": force})

        marked = get_auto_monitor_streamers()
        return [str(s["username"]).strip().lstrip("@").lower() for s in marked]

    def start_tracking(
        self, streamer_id: int, username: str, auto_reconnect: bool = True
    ) -> Dict[str, Any]:
        clean = username.strip().lstrip("@").lower()

        # Immer in DB markieren
        update_streamer_runtime_state(
            clean,
            is_tracking=True,
            auto_monitor=bool(auto_reconnect),
        )

        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.start_tracking(streamer_id, clean, auto_reconnect=auto_reconnect)

        # Ingest Worker per PubSub benachrichtigen
        if config.has_redis:
            self.bus.publish_sync(CHANNEL_RECONCILE, {"action": "start", "username": clean, "streamer_id": streamer_id})

        return {
            "ok": True,
            "message": f"TikTokLive-Worker für @{clean} gestartet (Auto-Monitor={auto_reconnect}).",
            "diagnostics": {
                "streamer_id": streamer_id,
                "username": clean,
                "is_running": True,
                "state": "starting",
                "last_message": "Startbefehl an Ingest-Worker gesendet",
            },
        }

    def stop_tracking(self, username: str) -> Dict[str, Any]:
        clean = username.strip().lstrip("@").lower()

        # In DB deaktivieren
        update_streamer_runtime_state(
            clean,
            is_live=False,
            is_tracking=False,
            auto_monitor=False,
            current_viewers=0,
        )

        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            return self._local_manager.stop_tracking(clean)

        if config.has_redis:
            # Lease sofort löschen, damit Ingest-Instanz Worker stoppt
            self.bus.delete_kv_sync(f"{PREFIX_LEASE}{clean}")
            self.bus.delete_kv_sync(f"{PREFIX_DIAG_WORKER}{clean}")
            self.bus.publish_sync(CHANNEL_RECONCILE, {"action": "stop", "username": clean})

        return {
            "ok": True,
            "message": f"Worker für @{clean} gestoppt.",
        }

    def stop_all(self) -> None:
        if self._local_manager is not None and config.service_role in ("all", "ingest"):
            self._local_manager.stop_all()
            return

        if config.has_redis:
            self.bus.publish_sync(CHANNEL_COMMANDS, {"action": "stop_all"})


monitor_client = MonitorClient()
