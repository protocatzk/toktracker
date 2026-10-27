"""
Tests für die Auth-Härtung: Challenge-Sperre nach Fehlversuchen, Token-Manipulation
und abgelaufene Sessions.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import base64
import hashlib
import hmac
import json
import time
import unittest

from shared.auth_store import admin_auth_manager
from shared.config import config


def _sign(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(config.session_secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


class TestChallengeLocking(unittest.TestCase):
    def test_wrong_code_locks_challenge(self):
        challenge = admin_auth_manager.create_challenge(client_info="unittest")
        cid = challenge["challenge_id"]

        for _ in range(admin_auth_manager.MAX_CODE_ATTEMPTS):
            self.assertIsNone(admin_auth_manager.verify_code("000000", challenge_id=cid))

        self.assertEqual(admin_auth_manager.poll_challenge(cid)["status"], "locked")

    def test_locked_challenge_rejects_correct_code(self):
        challenge = admin_auth_manager.create_challenge(client_info="unittest")
        cid = challenge["challenge_id"]
        for _ in range(admin_auth_manager.MAX_CODE_ATTEMPTS):
            admin_auth_manager.verify_code("000000", challenge_id=cid)

        self.assertIsNone(admin_auth_manager.verify_code(challenge["code"], challenge_id=cid))
        self.assertEqual(admin_auth_manager.poll_challenge(cid)["status"], "locked")

    def test_correct_code_consumes_challenge(self):
        challenge = admin_auth_manager.create_challenge(client_info="unittest")
        cid = challenge["challenge_id"]
        self.assertIsNotNone(admin_auth_manager.verify_code(challenge["code"], challenge_id=cid))
        self.assertEqual(admin_auth_manager.poll_challenge(cid)["status"], "consumed")

    def test_attempts_are_counted(self):
        challenge = admin_auth_manager.create_challenge(client_info="unittest")
        cid = challenge["challenge_id"]
        admin_auth_manager.verify_code("000000", challenge_id=cid)
        admin_auth_manager.verify_code("000000", challenge_id=cid)
        self.assertEqual(admin_auth_manager.poll_challenge(cid)["attempts"], 2)


class TestSessionTokens(unittest.TestCase):
    def test_valid_token_roundtrip(self):
        token = admin_auth_manager.create_session_token(admin_label="tester")
        payload = admin_auth_manager.verify_session_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "tester")
        self.assertEqual(payload["role"], "admin")

    def test_tampered_signature_is_rejected(self):
        token = admin_auth_manager.create_session_token()
        body, sig = token.rsplit(".", 1)
        flipped = ("1" if sig[0] == "0" else "0") + sig[1:]
        self.assertIsNone(admin_auth_manager.verify_session_token(f"{body}.{flipped}"))

    def test_modified_payload_is_rejected(self):
        token = admin_auth_manager.create_session_token(role="user")
        body, sig = token.rsplit(".", 1)
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
        payload["role"] = "admin"
        forged_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        self.assertIsNone(admin_auth_manager.verify_session_token(f"{forged_body}.{sig}"))

    def test_expired_token_is_rejected(self):
        expired = _sign({
            "sub": "tester",
            "role": "admin",
            "is_allowed": True,
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 10,
        })
        self.assertIsNone(admin_auth_manager.verify_session_token(expired))

    def test_token_bound_to_session_secret(self):
        foreign = _sign({"sub": "x", "role": "admin", "is_allowed": True, "exp": int(time.time()) + 60})
        self.assertIsNotNone(admin_auth_manager.verify_session_token(foreign))

        original = config.session_secret
        try:
            config.session_secret = "ein-anderes-secret-" + "x" * 32
            self.assertIsNone(admin_auth_manager.verify_session_token(foreign))
        finally:
            config.session_secret = original


if __name__ == "__main__":
    unittest.main()
