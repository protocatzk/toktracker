"""
Tests für Datenbank-Operationen und Aggregationen (shared/database.py).
Prüft Datenintegrität und Dual-Database-Kompatibilität ohne externe Netzwerkaufrufe.
"""
try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

from shared.database import (
    get_all_streamers_summary,
    get_auto_monitor_streamers,
    get_dashboard_overview,
    get_db,
    get_settings,
)


class TestDatabaseOperations(unittest.TestCase):
    def test_get_settings(self):
        settings = get_settings()
        self.assertIsInstance(settings, dict)
        self.assertIn("usd_per_diamond", settings)
        self.assertIn("usd_to_eur_rate", settings)
        self.assertIn("telegram_access_mode", settings)
        self.assertGreater(float(settings["usd_per_diamond"]), 0)

    def test_get_dashboard_overview(self):
        overview = get_dashboard_overview(period="all", force_refresh=True)
        self.assertIsInstance(overview, dict)
        self.assertIn("totals", overview)
        self.assertIn("streamers", overview)
        self.assertIn("recent_gifts", overview)

        totals = overview.get("totals", {})
        self.assertIn("streamer_count", totals)
        self.assertIn("total_coins", totals)
        self.assertIn("eur_net", totals)

    def test_get_auto_monitor_streamers(self):
        streamers = get_auto_monitor_streamers()
        self.assertIsInstance(streamers, list)
        for s in streamers:
            self.assertIn("id", s)
            self.assertIn("username", s)

    def test_get_all_streamers_summary(self):
        summary = get_all_streamers_summary()
        self.assertIsInstance(summary, list)

    def test_db_context_manager_query(self):
        with get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM streamers")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertGreaterEqual(int(row[0]), 0)


if __name__ == "__main__":
    unittest.main()
