"""
Tests für die Finanzberechnung (Coins -> USD -> EUR) und Zeitraum-Filter.

Die Erwartungswerte folgen den Default-Kursen aus DEFAULT_SETTINGS
(usd_per_diamond=0.005, usd_to_eur_rate=0.92).
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid

from shared.database import (
    _get_period_cutoff,
    delete_streamer,
    get_analytics_data,
    get_settings,
    record_gift_event,
    upsert_streamer,
)


class TestPeriodCutoff(unittest.TestCase):
    def test_all_has_no_cutoff(self):
        self.assertIsNone(_get_period_cutoff("all"))
        self.assertIsNone(_get_period_cutoff("unbekannt"))

    def test_known_periods_return_sql_timestamp(self):
        for period in ("today", "24h", "7d", "30d"):
            with self.subTest(period=period):
                cutoff = _get_period_cutoff(period)
                self.assertIsNotNone(cutoff)
                self.assertEqual(len(cutoff), 19)
                self.assertRegex(cutoff, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


class TestGiftRevenue(unittest.TestCase):
    def setUp(self):
        self.username = f"money_test_{uuid.uuid4().hex[:10]}"
        self.streamer = upsert_streamer(username=self.username, display_name="Money Test")
        self.streamer_id = int(self.streamer["id"])

    def tearDown(self):
        delete_streamer(self.streamer_id)

    def test_coin_to_currency_conversion(self):
        cfg = get_settings()
        event, created = record_gift_event(
            streamer_id=self.streamer_id,
            sender_username="donor_money",
            gift_name="Rose",
            diamond_count=100,
            repeat_count=2,
            event_uid=f"money-{uuid.uuid4().hex}",
        )
        self.assertTrue(created)
        self.assertIsNotNone(event)

        expected_coins = 200
        expected_usd_net = round(expected_coins * cfg["usd_per_diamond"], 4)
        expected_eur_net = round(expected_usd_net * cfg["usd_to_eur_rate"], 4)
        expected_usd_gross = round(expected_coins * cfg["gross_usd_per_coin"], 4)
        expected_eur_gross = round(expected_usd_gross * cfg["usd_to_eur_rate"], 4)

        self.assertEqual(int(event["total_coins"]), expected_coins)
        self.assertAlmostEqual(float(event["usd_net"]), expected_usd_net, places=4)
        self.assertAlmostEqual(float(event["eur_net"]), expected_eur_net, places=4)
        self.assertAlmostEqual(float(event["usd_gross"]), expected_usd_gross, places=4)
        self.assertAlmostEqual(float(event["eur_gross"]), expected_eur_gross, places=4)

    def test_analytics_totals_match_event_sum(self):
        for repeat in (1, 3):
            record_gift_event(
                streamer_id=self.streamer_id,
                sender_username="donor_a",
                gift_name="Rose",
                diamond_count=50,
                repeat_count=repeat,
                event_uid=f"money-{uuid.uuid4().hex}",
            )

        analytics = get_analytics_data(streamer_id=self.streamer_id, period="all")
        totals = analytics["totals"]
        self.assertEqual(totals["total_coins"], 200)  # 50*1 + 50*3
        self.assertEqual(totals["gift_events_count"], 2)
        self.assertEqual(totals["unique_gifters"], 1)
        self.assertAlmostEqual(totals["usd_net"], 1.0, places=2)
        self.assertAlmostEqual(totals["eur_net"], 0.92, places=2)

    def test_duplicate_event_uid_is_ignored(self):
        event_uid = f"money-{uuid.uuid4().hex}"
        _, created_first = record_gift_event(
            streamer_id=self.streamer_id,
            sender_username="donor_dup",
            gift_name="Rose",
            diamond_count=10,
            event_uid=event_uid,
        )
        second_event, created_second = record_gift_event(
            streamer_id=self.streamer_id,
            sender_username="donor_dup",
            gift_name="Rose",
            diamond_count=10,
            event_uid=event_uid,
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertIsNone(second_event)

        analytics = get_analytics_data(streamer_id=self.streamer_id, period="all")
        self.assertEqual(analytics["totals"]["total_coins"], 10)


if __name__ == "__main__":
    unittest.main()
