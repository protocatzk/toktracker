"""
Tests für das verteilte Rate-Limiting (shared/ratelimit.py) und den Bus-Zähler.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid
from unittest import mock

from shared.bus import get_bus
from shared.ratelimit import check_rate_limit, reset_rate_limit


class TestRateLimit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.identifier = f"unit-{uuid.uuid4().hex}"
        self.bucket = f"bucket-{uuid.uuid4().hex}"

    async def asyncTearDown(self):
        await reset_rate_limit(self.bucket, self.identifier)

    async def test_allows_up_to_limit_then_blocks(self):
        for expected_hit in (1, 2, 3):
            result = await check_rate_limit(self.bucket, self.identifier, 3, 60)
            self.assertTrue(result.allowed)
            self.assertEqual(result.hits, expected_hit)

        blocked = await check_rate_limit(self.bucket, self.identifier, 3, 60)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.hits, 4)
        self.assertEqual(blocked.retry_after, 60)

    async def test_reset_clears_counter(self):
        for _ in range(3):
            await check_rate_limit(self.bucket, self.identifier, 3, 60)
        self.assertFalse((await check_rate_limit(self.bucket, self.identifier, 3, 60)).allowed)

        await reset_rate_limit(self.bucket, self.identifier)
        self.assertTrue((await check_rate_limit(self.bucket, self.identifier, 3, 60)).allowed)

    async def test_identifiers_are_isolated(self):
        for _ in range(2):
            await check_rate_limit(self.bucket, self.identifier, 2, 60)
        self.assertFalse((await check_rate_limit(self.bucket, self.identifier, 2, 60)).allowed)
        self.assertTrue((await check_rate_limit(self.bucket, "andere-ip", 2, 60)).allowed)

    async def test_zero_limit_disables_limiting(self):
        result = await check_rate_limit(self.bucket, self.identifier, 0, 60)
        self.assertTrue(result.allowed)

    async def test_fail_open_when_bus_is_unavailable(self):
        with mock.patch("shared.ratelimit.get_bus", side_effect=RuntimeError("bus down")):
            result = await check_rate_limit(self.bucket, self.identifier, 1, 60)
        self.assertTrue(result.allowed)
        self.assertEqual(result.hits, 0)


class TestBusCounter(unittest.IsolatedAsyncioTestCase):
    async def test_increment_is_atomic_and_monotonic(self):
        bus = get_bus()
        key = f"tt:test:incr:{uuid.uuid4().hex}"
        try:
            self.assertEqual(await bus.incr_kv(key, 60), 1)
            self.assertEqual(await bus.incr_kv(key, 60), 2)
            self.assertEqual(await bus.incr_kv(key, 60), 3)
        finally:
            await bus.delete_kv(key)

    async def test_counter_survives_reads(self):
        bus = get_bus()
        key = f"tt:test:incr:{uuid.uuid4().hex}"
        try:
            await bus.incr_kv(key, 60)
            self.assertEqual(await bus.get_kv(key), "1")
            self.assertEqual(await bus.incr_kv(key, 60), 2)
        finally:
            await bus.delete_kv(key)


if __name__ == "__main__":
    unittest.main()
