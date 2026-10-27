"""
Tests für Lease-Semantik (Sharding/Failover) auf dem In-Memory-Bus und – falls
konfiguriert – auf Redis.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid

from shared.bus.memory_bus import MemoryBus


class TestMemoryBusLeases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bus = MemoryBus()
        self.key = f"tt:lease:test:{uuid.uuid4().hex}"

    async def test_acquire_renew_release(self):
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-a", 30))
        self.assertTrue(await self.bus.renew_lease(self.key, "inst-a", 30))
        self.assertFalse(await self.bus.release_lease(self.key, "inst-b"))
        self.assertTrue(await self.bus.release_lease(self.key, "inst-a"))

    async def test_second_instance_cannot_steal_active_lease(self):
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-a", 30))
        self.assertFalse(await self.bus.acquire_lease(self.key, "inst-b", 30))
        self.assertFalse(await self.bus.renew_lease(self.key, "inst-b", 30))

    async def test_lease_expiry_allows_failover(self):
        # ttl=0 -> Lease ist sofort abgelaufen, andere Instanz darf übernehmen.
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-a", 0))
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-b", 30))
        self.assertFalse(await self.bus.release_lease(self.key, "inst-a"))


class TestRedisBusLeases(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from tests._bootstrap import TEST_REDIS_URL

        if not TEST_REDIS_URL:
            self.skipTest("Kein Test-Redis konfiguriert (TOKTRACKER_TEST_REDIS_URL)")

        from shared.bus.redis_bus import RedisBus

        self.bus = RedisBus(TEST_REDIS_URL)
        self.key = f"tt:lease:test:{uuid.uuid4().hex}"

    async def asyncTearDown(self):
        if hasattr(self, "bus"):
            try:
                await self.bus.release_lease(self.key, "inst-a")
            finally:
                await self.bus.disconnect()

    async def test_redis_lease_lifecycle(self):
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-a", 30))
        self.assertFalse(await self.bus.acquire_lease(self.key, "inst-b", 30))
        self.assertTrue(await self.bus.renew_lease(self.key, "inst-a", 30))
        self.assertTrue(await self.bus.release_lease(self.key, "inst-a"))
        self.assertTrue(await self.bus.acquire_lease(self.key, "inst-b", 30))


if __name__ == "__main__":
    unittest.main()
