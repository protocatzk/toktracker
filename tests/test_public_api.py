"""
Tests für öffentliche Datenflächen: Datenschutz-Maskierung und Payload-Hygiene
(kein `raw_data_json`, keine Spender-Listen in öffentlichen Battle-Antworten).
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid

import httpx

from app import app
from shared.database import (
    delete_streamer,
    get_battle_details,
    get_settings,
    invalidate_overview_cache,
    record_battle_finish,
    record_battle_start,
    record_gift_event,
    update_settings,
    upsert_streamer,
)

DONOR = "donor_geheim_4711"


class TestPublicDonorPrivacy(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.username = f"public_test_{uuid.uuid4().hex[:10]}"
        self.streamer = upsert_streamer(username=self.username, display_name="Public Test")
        self.streamer_id = int(self.streamer["id"])
        record_gift_event(
            streamer_id=self.streamer_id,
            sender_username=DONOR,
            sender_nickname=DONOR,
            gift_name="Rose",
            diamond_count=25,
            event_uid=f"public-{uuid.uuid4().hex}",
        )
        update_settings({"public_show_donors": 0})
        invalidate_overview_cache()

    def tearDown(self):
        update_settings({"public_show_donors": 0})
        invalidate_overview_cache()
        delete_streamer(self.streamer_id)

    async def _get(self, path, params=None):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path, params=params)

    async def test_public_overview_masks_donor_names_by_default(self):
        self.assertFalse(bool(get_settings().get("public_show_donors")))
        res = await self._get("/api/public/overview", params={"period": "all"})
        self.assertEqual(res.status_code, 200)
        gifts = res.json()["recent_gifts"]
        self.assertTrue(gifts)
        for gift in gifts:
            self.assertNotEqual(gift["sender_username"], DONOR)
            self.assertIn("*", gift["sender_username"])
        self.assertEqual(gifts[0]["streamer_username"], self.username)

    async def test_public_overview_shows_donors_when_enabled(self):
        update_settings({"public_show_donors": 1})
        res = await self._get("/api/public/overview", params={"period": "all"})
        self.assertEqual(res.status_code, 200)
        senders = [g["sender_username"] for g in res.json()["recent_gifts"]]
        self.assertIn(DONOR, senders)

    async def test_public_streamer_detail_masks_top_gifters(self):
        res = await self._get(f"/api/public/streamers/{self.username}", params={"period": "all"})
        self.assertEqual(res.status_code, 200)
        for gifter in res.json()["top_gifters"]:
            self.assertNotEqual(gifter["sender_username"], DONOR)

    async def test_public_analytics_masks_top_gifters(self):
        res = await self._get("/api/public/analytics", params={"period": "all"})
        self.assertEqual(res.status_code, 200)
        for gifter in res.json()["top_gifters"]:
            self.assertNotEqual(gifter["sender_username"], DONOR)


class TestBattlePayloadHygiene(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.username = f"battle_test_{uuid.uuid4().hex[:10]}"
        self.streamer = upsert_streamer(username=self.username, display_name="Battle Test")
        self.streamer_id = int(self.streamer["id"])

        self.started_at = "2026-02-01T10:00:00"
        self.ended_at = "2026-02-01T10:05:00"
        self.battle_id = record_battle_start(
            streamer_id=self.streamer_id,
            battle_id=f"btl-{uuid.uuid4().hex[:8]}",
            opponent_username="gegner_test",
            started_at=self.started_at,
            duration_seconds=300,
        )
        record_gift_event(
            streamer_id=self.streamer_id,
            sender_username=DONOR,
            gift_name="Rose",
            diamond_count=10,
            event_uid=f"battle-{uuid.uuid4().hex}",
            created_at="2026-02-01T10:01:00",
        )
        record_battle_finish(
            battle_db_id=self.battle_id,
            streamer_score=1200,
            opponent_score=800,
            result="WIN",
            raw_data_json='{"internal_payload": true}',
            ended_at=self.ended_at,
        )

    def tearDown(self):
        delete_streamer(self.streamer_id)

    def test_public_details_hide_raw_payload_and_gifts(self):
        details = get_battle_details(self.battle_id)
        self.assertIsNotNone(details)
        self.assertNotIn("raw_data_json", details)
        self.assertEqual(details["gifts"], [])

    def test_admin_details_include_raw_payload_and_gifts(self):
        details = get_battle_details(self.battle_id, include_raw=True, include_gifts=True)
        self.assertIsNotNone(details)
        self.assertIn("raw_data_json", details)
        self.assertEqual(len(details["gifts"]), 1)
        self.assertEqual(details["gifts"][0]["sender_username"], DONOR)

    async def test_miniapp_battle_endpoint_is_sanitized(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get(f"/api/miniapp/battles/{self.battle_id}")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertNotIn("raw_data_json", payload)
        self.assertEqual(payload["gifts"], [])

    async def test_public_battle_list_has_no_raw_payload(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/api/public/battles", params={"period": "all", "limit": 5})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["battles"])
        for battle in res.json()["battles"]:
            self.assertNotIn("raw_data_json", battle)
            if battle.get("partner_battle"):
                self.assertNotIn("raw_data_json", battle["partner_battle"])


if __name__ == "__main__":
    unittest.main()
