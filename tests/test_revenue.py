"""
Tests für das Revenue-Profilmodell und die Snapshot-Berechnung.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid

from shared.database import (
    assign_streamer_revenue_profile,
    get_revenue_profile,
    get_revenue_profile_for_streamer,
    list_revenue_profiles,
    record_gift_event,
    update_revenue_profile,
    upsert_streamer,
)
from shared.revenue import compute_gift_revenue


class TestRevenueMath(unittest.TestCase):
    def test_default_profile_math(self):
        revenue = compute_gift_revenue(100, None)
        self.assertAlmostEqual(revenue["usd_gross"], 1.05, places=4)
        self.assertAlmostEqual(revenue["usd_net"], 0.525, places=4)
        self.assertAlmostEqual(revenue["eur_net"], 0.483, places=4)
        self.assertLessEqual(revenue["usd_net_low"], revenue["usd_net"])
        self.assertGreaterEqual(revenue["usd_net_high"], revenue["usd_net"])

    def test_profile_cuts(self):
        profile = {
            "coin_price_usd": 0.02,
            "creator_share_pct": 0.6,
            "agency_share_pct": 0.10,
            "payout_fee_pct": 0.05,
            "tax_pct": 0.20,
            "fx_rate": 0.90,
            "coin_price_uncertainty_pct": 0.0,
            "creator_share_uncertainty_pct": 0.0,
            "agency_share_max_pct": 0.10,
            "tax_max_pct": 0.20,
            "fx_uncertainty_pct": 0.0,
        }
        revenue = compute_gift_revenue(1000, profile)
        gross = 1000 * 0.02
        expected_net = gross * 0.6 * 0.9 * 0.95 * 0.8
        self.assertAlmostEqual(revenue["usd_gross"], gross, places=4)
        self.assertAlmostEqual(revenue["usd_net"], expected_net, places=4)
        self.assertAlmostEqual(revenue["eur_net"], expected_net * 0.90, places=4)
        # Ohne Unsicherheit sind Low/High identisch.
        self.assertAlmostEqual(revenue["usd_net_low"], expected_net, places=4)
        self.assertAlmostEqual(revenue["usd_net_high"], expected_net, places=4)


class TestRevenueProfiles(unittest.TestCase):
    def test_default_profiles_exist(self):
        profiles = list_revenue_profiles()
        names = {p["name"] for p in profiles}
        self.assertIn("DE Standard", names)
        self.assertIn("Pakistan (DE-Zuschauer)", names)
        self.assertTrue(any(int(p.get("is_default") or 0) for p in profiles))

    def test_streamer_gets_default_and_can_be_reassigned(self):
        streamer = upsert_streamer(f"revenue_profile_{uuid.uuid4().hex[:8]}")
        streamer_id = int(streamer["id"])
        default_profile = get_revenue_profile_for_streamer(streamer_id)
        self.assertIsNotNone(default_profile)

        pakistan = next(
            p for p in list_revenue_profiles() if p["name"] == "Pakistan (DE-Zuschauer)"
        )
        self.assertTrue(assign_streamer_revenue_profile(streamer_id, int(pakistan["id"])))
        assigned = get_revenue_profile_for_streamer(streamer_id)
        self.assertEqual(int(assigned["id"]), int(pakistan["id"]))
        self.assertEqual(assigned["creator_region"], "PK")

        # Zurück auf Default.
        self.assertTrue(assign_streamer_revenue_profile(streamer_id, None))
        fallback = get_revenue_profile_for_streamer(streamer_id)
        self.assertTrue(int(fallback.get("is_default") or 0))

    def test_record_gift_stores_snapshot_and_analytics_stays_stable(self):
        from shared.database import get_analytics_data

        streamer = upsert_streamer(f"revenue_snapshot_{uuid.uuid4().hex[:8]}")
        streamer_id = int(streamer["id"])
        profile = get_revenue_profile_for_streamer(streamer_id)

        event, created = record_gift_event(
            streamer_id=streamer_id,
            sender_username="revenue_tester",
            gift_name="Rose",
            diamond_count=100,
            repeat_count=1,
            event_uid=f"revenue-{uuid.uuid4().hex}",
        )
        self.assertTrue(created)
        self.assertEqual(int(event["revenue_profile_id"]), int(profile["id"]))
        self.assertAlmostEqual(float(event["usd_net"]), 0.525, places=4)

        # Profil nachträglich ändern: Der gespeicherte Event bleibt unverändert.
        update_revenue_profile(
            int(profile["id"]),
            {
                "coin_price_usd": 0.02,
                "creator_share_pct": 0.5,
            },
        )
        try:
            analytics = get_analytics_data(streamer_id=streamer_id, period="all")
            self.assertAlmostEqual(analytics["totals"]["usd_net"], 0.53, places=2)
        finally:
            update_revenue_profile(
                int(profile["id"]),
                {
                    "coin_price_usd": profile["coin_price_usd"],
                    "creator_share_pct": profile["creator_share_pct"],
                },
            )


if __name__ == "__main__":
    unittest.main()
