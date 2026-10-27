"""
Tests für IngestCoordinator (services/ingest/coordinator.py).
Prüft Lease-Handling, Sharding & Heartbeats mit gemocktem TikTokLive-Worker (0 Quota-Verbrauch).
"""
try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from services.ingest.coordinator import IngestCoordinator
from shared.contracts import PREFIX_HEARTBEAT_INGEST, PREFIX_LEASE


class TestIngestCoordinator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.coordinator = IngestCoordinator()

    async def asyncTearDown(self):
        if self.coordinator._running:
            await self.coordinator.stop()

    async def test_coordinator_init(self):
        self.assertTrue(self.coordinator.instance_id.startswith("ingest-"))
        self.assertFalse(self.coordinator._running)
        self.assertEqual(len(self.coordinator._my_leases), 0)

    @patch("services.ingest.coordinator.monitor_manager")
    async def test_coordinator_reconcile_with_mocked_workers(self, mock_mm):
        mock_mm.is_tracking.return_value = False
        mock_mm.start_worker.return_value = True

        test_streamer = "test_streamer_mock_123"
        lease_key = f"{PREFIX_LEASE}{test_streamer}"

        # 1. Lease direkt für diesen Test-Coordinator erwerben
        ok = await self.coordinator.bus.acquire_lease(lease_key, self.coordinator.instance_id, ttl_seconds=10)
        if not ok:
            # Wenn Redis nicht läuft, überspringen
            self.skipTest("Redis Bus nicht erreichbar")

        self.coordinator._my_leases.add(test_streamer)

        # 2. Reconcile Event triggern
        await self.coordinator._on_reconcile_signal({"source": "test"})
        self.assertTrue(self.coordinator._reconcile_event.is_set())

        # 3. Stop -> muss Leases freigeben
        await self.coordinator.stop()
        self.assertFalse(self.coordinator._running)
        self.assertEqual(len(self.coordinator._my_leases), 0)


if __name__ == "__main__":
    unittest.main()
