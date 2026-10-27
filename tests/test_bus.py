"""
Tests für Bus-Implementierungen (MemoryBus & RedisBus).
Prüft KV-Store, PubSub, Leases und RPC ohne externe TikTok-/Telegram-Quoten.
"""
import asyncio
import os
import unittest
from shared.bus.memory_bus import MemoryBus
from shared.bus.redis_bus import RedisBus


class TestMemoryBus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = MemoryBus()
        await self.bus.connect()

    async def asyncTearDown(self):
        await self.bus.disconnect()

    async def test_kv_operations_async(self):
        await self.bus.set_kv("test:key1", "hello_async")
        val = await self.bus.get_kv("test:key1")
        self.assertEqual(val, "hello_async")
        await self.bus.delete_kv("test:key1")
        self.assertIsNone(await self.bus.get_kv("test:key1"))

    def test_kv_operations_sync(self):
        self.bus.set_kv_sync("test:key2", "hello_sync")
        val = self.bus.get_kv_sync("test:key2")
        self.assertEqual(val, "hello_sync")
        self.bus.delete_kv_sync("test:key2")
        self.assertIsNone(self.bus.get_kv_sync("test:key2"))

    async def test_scan_keys(self):
        await self.bus.set_kv("test:scan:1", "a")
        await self.bus.set_kv("test:scan:2", "b")
        keys = await self.bus.scan_keys("test:scan:*")
        self.assertIn("test:scan:1", keys)
        self.assertIn("test:scan:2", keys)

    async def test_lease_acquire_renew_release(self):
        # 1. Acquire
        ok = await self.bus.acquire_lease("test:lease:1", "owner_A", ttl_seconds=5)
        self.assertTrue(ok)
        # 2. Another owner cannot acquire
        fail = await self.bus.acquire_lease("test:lease:1", "owner_B", ttl_seconds=5)
        self.assertFalse(fail)
        # 3. Renew by owner
        renew_ok = await self.bus.renew_lease("test:lease:1", "owner_A", ttl_seconds=5)
        self.assertTrue(renew_ok)
        # 4. Release
        rel_ok = await self.bus.release_lease("test:lease:1", "owner_A")
        self.assertTrue(rel_ok)
        # 5. Now owner B can acquire
        ok_b = await self.bus.acquire_lease("test:lease:1", "owner_B", ttl_seconds=5)
        self.assertTrue(ok_b)

    async def test_rpc_flow(self):
        async def mock_handler(req):
            return {"echo": req.get("msg"), "status": "ok"}

        await self.bus.rpc_listen("test:queue:rpc", mock_handler)
        res = await self.bus.rpc_call("test:queue:rpc", {"msg": "hello_rpc"}, timeout=2.0)
        self.assertEqual(res.get("echo"), "hello_rpc")
        self.assertEqual(res.get("status"), "ok")


class TestRedisBusIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        try:
            self.bus = RedisBus(self.redis_url)
            await self.bus.connect()
            # Test connectivity
            await self.bus.set_kv("test:ping", "pong", ttl=5)
        except Exception as e:
            self.skipTest(f"Redis nicht erreichbar unter {self.redis_url}: {e}")

    async def asyncTearDown(self):
        if hasattr(self, "bus") and self.bus:
            try:
                await self.bus.delete_kv("test:ping")
                await self.bus.disconnect()
            except Exception:
                pass

    async def test_redis_kv_async_and_sync(self):
        await self.bus.set_kv("test:rk1", "val1", ttl=10)
        self.assertEqual(await self.bus.get_kv("test:rk1"), "val1")
        self.assertEqual(self.bus.get_kv_sync("test:rk1"), "val1")
        await self.bus.delete_kv("test:rk1")
        self.assertIsNone(await self.bus.get_kv("test:rk1"))

    async def test_redis_lease_and_sharding(self):
        lease_key = "test:sharding:lease:streamer_1"
        try:
            # 1. Acquire
            ok = await self.bus.acquire_lease(lease_key, "worker_alpha", ttl_seconds=5)
            self.assertTrue(ok)
            # 2. Worker beta must fail
            fail = await self.bus.acquire_lease(lease_key, "worker_beta", ttl_seconds=5)
            self.assertFalse(fail)
            # 3. Renew
            self.assertTrue(await self.bus.renew_lease(lease_key, "worker_alpha", ttl_seconds=5))
            # 4. Release
            self.assertTrue(await self.bus.release_lease(lease_key, "worker_alpha"))
            # 5. Beta can acquire now
            self.assertTrue(await self.bus.acquire_lease(lease_key, "worker_beta", ttl_seconds=5))
        finally:
            await self.bus.release_lease(lease_key, "worker_beta")

    async def test_redis_rpc(self):
        queue = "test:rpc:math"

        async def math_handler(req):
            op = req.get("op")
            a, b = req.get("a", 0), req.get("b", 0)
            if op == "add":
                return {"result": a + b}
            return {"error": "unknown op"}

        await self.bus.rpc_listen(queue, math_handler)
        # Kurze Pause für den Listener-Start
        await asyncio.sleep(0.05)
        resp = await self.bus.rpc_call(queue, {"op": "add", "a": 12, "b": 30}, timeout=2.0)
        self.assertEqual(resp.get("result"), 42)


if __name__ == "__main__":
    unittest.main()
