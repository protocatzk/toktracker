import asyncio
import json
import logging
import math
import os
import secrets
import time
from typing import Dict, Set

from shared.bus import get_bus
from shared.contracts import (
    CHANNEL_COMMANDS,
    CHANNEL_RECONCILE,
    PREFIX_DIAG_WORKER,
    PREFIX_HEARTBEAT_INGEST,
    PREFIX_LEASE,
)
from shared.database import (
    get_auto_monitor_streamers,
)
from tiktok_service import monitor_manager

logger = logging.getLogger("toktracker.ingest_coordinator")


class IngestCoordinator:
    """
    Koordiniert die automatische Verteilung von TikTokLive-Workern über mehrere
    Ingest-Instanzen per Redis-Lease (Sharding & Failover).
    """

    def __init__(self):
        nodename = os.uname().nodename if hasattr(os, "uname") else "host"
        self.instance_id = f"ingest-{nodename}-{os.getpid()}-{secrets.token_hex(3)}"
        self.bus = get_bus()
        self._running = False
        self._my_leases: Set[str] = set()
        self._reconcile_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        logger.info("IngestCoordinator gestartet (Instanz-ID: %s)", self.instance_id)

        # Reconcile-PubSub abonnieren
        await self.bus.subscribe(CHANNEL_RECONCILE, self._on_reconcile_signal)
        await self.bus.subscribe(CHANNEL_COMMANDS, self._on_command_signal)

        # Heartbeat & Reconcile Tasks
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._reconcile_loop())
        asyncio.create_task(self._telemetry_push_loop())

        # Initialer Trigger
        self._reconcile_event.set()

    async def stop(self) -> None:
        logger.info("Stoppe IngestCoordinator (%s)...", self.instance_id)
        self._running = False

        # Alle lokalen Worker mit preserve_db_state=True stoppen
        monitor_manager.stop_all()

        # Eigene Leases in Redis sofort freigeben, damit andere Instanzen direkt übernehmen
        for uname in list(self._my_leases):
            try:
                await self.bus.release_lease(f"{PREFIX_LEASE}{uname}", self.instance_id)
            except Exception:
                pass
        self._my_leases.clear()

        # Heartbeat löschen
        try:
            await self.bus.delete_kv(f"{PREFIX_HEARTBEAT_INGEST}{self.instance_id}")
        except Exception:
            pass

    async def _on_reconcile_signal(self, msg: Dict) -> None:
        logger.debug("Reconcile-Signal empfangen: %s", msg)
        self._reconcile_event.set()

    async def _on_command_signal(self, msg: Dict) -> None:
        action = msg.get("action")
        if action == "stop_all":
            logger.info("stop_all Signal empfangen – stoppe alle Worker...")
            monitor_manager.stop_all()
            for uname in list(self._my_leases):
                await self.bus.release_lease(f"{PREFIX_LEASE}{uname}", self.instance_id)
            self._my_leases.clear()

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                hb_key = f"{PREFIX_HEARTBEAT_INGEST}{self.instance_id}"
                await self.bus.set_kv(hb_key, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ttl=15)
            except Exception as exc:
                logger.debug("Fehler beim Senden des Ingest-Heartbeats: %s", exc)
            await asyncio.sleep(5.0)

    async def _reconcile_loop(self) -> None:
        while self._running:
            try:
                await self._perform_reconcile()
            except Exception as exc:
                logger.error("Fehler im Reconcile-Zyklus: %s", exc)

            # Warte 5 Sekunden oder bis zum nächsten expliziten Event
            try:
                await asyncio.wait_for(self._reconcile_event.wait(), timeout=5.0)
                self._reconcile_event.clear()
            except asyncio.TimeoutError:
                pass

    async def _perform_reconcile(self) -> None:
        if not self._running:
            return

        # 1. Gewünschte Streamer aus DB abfragen
        desired_streamers = await asyncio.to_thread(get_auto_monitor_streamers)
        desired_map = {str(s["username"]).strip().lstrip("@").lower(): s for s in desired_streamers}

        # 2. Bestehende Leases verlängern oder abbauen
        for uname in list(self._my_leases):
            if uname not in desired_map:
                # Streamer wurde deaktiviert -> Worker stoppen und Lease freigeben
                logger.info("Streamer @%s nicht mehr in DB aktiv -> stoppe Worker", uname)
                monitor_manager.stop_tracking(uname)
                await self.bus.release_lease(f"{PREFIX_LEASE}{uname}", self.instance_id)
                self._my_leases.remove(uname)
                continue

            # Lease verlängern
            renewed = await self.bus.renew_lease(f"{PREFIX_LEASE}{uname}", self.instance_id, ttl=30)
            if not renewed:
                logger.warning("Lease für @%s verloren -> stoppe Worker auf dieser Instanz", uname)
                monitor_manager.stop_tracking(uname)
                self._my_leases.remove(uname)

        # 3. Aktive Ingest-Instanzen ermitteln für Fair-Sharing
        hb_keys = await self.bus.scan_keys(f"{PREFIX_HEARTBEAT_INGEST}*")
        active_instances = max(1, len(hb_keys))
        fair_share = math.ceil(len(desired_map) / active_instances) if desired_map else 0

        # 4. Freie Streamer übernehmen (bis zum fairen Anteil)
        for uname, s_info in desired_map.items():
            if uname in self._my_leases:
                # Prüfen, ob lokaler Worker noch lebt
                if not monitor_manager.is_tracking(uname):
                    monitor_manager.start_tracking(int(s_info["id"]), uname, auto_reconnect=True)
                continue

            if len(self._my_leases) >= fair_share:
                # Kapazitätsgrenze für diesen Worker erreicht
                continue

            lease_key = f"{PREFIX_LEASE}{uname}"
            acquired = await self.bus.acquire_lease(lease_key, self.instance_id, ttl=30)
            if acquired:
                logger.info("Lease für @%s erhalten -> starte Worker auf %s", uname, self.instance_id)
                self._my_leases.add(uname)
                monitor_manager.start_tracking(int(s_info["id"]), uname, auto_reconnect=True)

    async def _telemetry_push_loop(self) -> None:
        """Pushed alle 2 Sekunden aktuelle Snapshots aller überwachten Streamer nach Redis."""
        while self._running:
            try:
                for uname in list(self._my_leases):
                    snap = monitor_manager.get_worker_diagnostics(uname)
                    if snap:
                        await self.bus.set_kv(
                            f"{PREFIX_DIAG_WORKER}{uname}",
                            json.dumps(snap, default=str),
                            ttl=15,
                        )
            except Exception as exc:
                logger.debug("Fehler beim Pushen der Worker-Telemetrie: %s", exc)
            await asyncio.sleep(2.0)
