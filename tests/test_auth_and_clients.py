"""
Tests für AdminAuthManager, MonitorClient und BotClient.
Prüft Challenge-Handling, Cookie-Signierung und Client-Abstraktionen.
"""
try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

from shared.auth_store import admin_auth_manager
from shared.bot_client import bot_client
from shared.monitor_client import monitor_client


class TestAuthAndClients(unittest.TestCase):
    def test_admin_auth_challenge_flow(self):
        # 1. Challenge erstellen
        ch = admin_auth_manager.create_challenge(client_info="Unit-Test-Runner")
        self.assertIn("challenge_id", ch)
        self.assertIn("code", ch)
        self.assertEqual(len(ch["code"]), 6)
        cid = ch["challenge_id"]

        # 2. Challenge abrufen
        loaded = admin_auth_manager.poll_challenge(cid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["status"], "pending")

        # 3. Freigabe durch Admin
        admin_auth_manager.approve_challenge(cid, admin_label="admin_test_bot")
        approved = admin_auth_manager.poll_challenge(cid)
        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], "approved")

    def test_session_token_generation_and_verification(self):
        token = admin_auth_manager.create_session_token()
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

        # Token verifizieren
        valid = admin_auth_manager.verify_session_token(token)
        self.assertTrue(valid)

        # Ungültiges Token abweisen
        self.assertFalse(admin_auth_manager.verify_session_token("invalid_token_12345"))
        self.assertFalse(admin_auth_manager.verify_session_token(""))

    def test_monitor_client_queries(self):
        # Nicht-existenter Streamer
        status = monitor_client.get_status("streamer_not_existing_xyz123")
        self.assertIsInstance(status, str)
        self.assertIn(status.lower(), ("gestoppt", "unbekannt", "offline", "inaktiv"))

        diag = monitor_client.get_worker_diagnostics("streamer_not_existing_xyz123")
        self.assertIsNone(diag)

    def test_bot_client_status(self):
        diag = bot_client.get_diagnostics()
        self.assertIsInstance(diag, dict)
        self.assertIn("state", diag)


if __name__ == "__main__":
    unittest.main()
