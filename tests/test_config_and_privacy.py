"""
Tests für Config-Härtung (SESSION_SECRET) und Datenschutz-Maskierung.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

from shared.config import AppConfig
from shared.privacy import apply_public_privacy, mask_donor_rows, mask_name


class TestSessionSecretHardening(unittest.TestCase):
    def test_short_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            AppConfig(session_secret="zu-kurz")

    def test_explicit_secret_has_env_source(self):
        cfg = AppConfig(session_secret="s" * 40)
        self.assertEqual(cfg.session_secret_source, "env")
        self.assertEqual(cfg.session_secret, "s" * 40)

    def test_secret_is_derived_when_sources_available(self):
        cfg = AppConfig(session_secret="", telegram_bot_token="123:abc", api_key="key")
        self.assertEqual(cfg.session_secret_source, "derived")
        self.assertEqual(len(cfg.session_secret), 64)

    def test_ephemeral_secret_is_random_per_instance(self):
        first = AppConfig(session_secret="", telegram_bot_token="", api_key="")
        second = AppConfig(session_secret="", telegram_bot_token="", api_key="")
        self.assertEqual(first.session_secret_source, "ephemeral")
        self.assertEqual(len(first.session_secret), 64)
        self.assertNotEqual(first.session_secret, second.session_secret)

    def test_invalid_cookie_secure_value_falls_back_to_auto(self):
        cfg = AppConfig(session_secret="s" * 40, session_cookie_secure="unsinn")
        self.assertEqual(cfg.session_cookie_secure, "auto")


class TestPrivacyMasking(unittest.TestCase):
    def test_mask_name_keeps_shape_but_hides_identity(self):
        self.assertEqual(mask_name("maxmuster"), "m*******r")
        self.assertEqual(mask_name("abc"), "a**")
        self.assertEqual(mask_name("ab"), "a*")
        self.assertEqual(mask_name(""), "")
        self.assertEqual(mask_name(None), "")

    def test_mask_is_deterministic(self):
        self.assertEqual(mask_name("donor123"), mask_name("donor123"))

    def test_mask_donor_rows_does_not_mutate_input(self):
        rows = [{"sender_username": "maxmuster", "sender_nickname": "Max", "total_coins": 10}]
        masked = mask_donor_rows(rows)
        self.assertEqual(rows[0]["sender_username"], "maxmuster")
        self.assertNotEqual(masked[0]["sender_username"], "maxmuster")
        self.assertEqual(masked[0]["total_coins"], 10)

    def test_apply_public_privacy_masks_top_gifters_only(self):
        payload = {
            "top_gifters": [{"sender_username": "donor123"}],
            "streamer": {"username": "streamer_public"},
            "totals": {"total_coins": 5},
        }
        masked = apply_public_privacy(payload, show_donors=False)
        self.assertNotEqual(masked["top_gifters"][0]["sender_username"], "donor123")
        self.assertEqual(masked["streamer"]["username"], "streamer_public")
        self.assertEqual(masked["totals"], {"total_coins": 5})

    def test_apply_public_privacy_is_noop_when_enabled(self):
        payload = {"top_gifters": [{"sender_username": "donor123"}]}
        self.assertEqual(apply_public_privacy(payload, show_donors=True)["top_gifters"][0]["sender_username"], "donor123")


if __name__ == "__main__":
    unittest.main()
