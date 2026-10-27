"""
Tests für die Zugriffssperre (ACCESS_GATE=whitelist).

Die Sperre ist die äußerste Middleware: Nicht freigeschaltete Besucher sehen nur
Login, statische Assets, /api/health und die Mini-App-Seite (für den Telegram-Login).
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

import httpx

from app import app
from shared import access_gate
from shared.auth_store import AdminAuthManager, admin_auth_manager
from shared.config import config

GATED_PAGES = ("/", "/public", "/panel", "/admin", "/donor-radar", "/chat-intelligence", "/site-analytics")
GATED_APIS = ("/api/overview", "/api/public/overview", "/api/analytics", "/api/battles", "/api/miniapp/data")
PUBLIC_PATHS = ("/login", "/api/health", "/robots.txt", "/miniapp", "/static/style.css", "/pictures/bot_avatar.jpg")


class GateTestCase(unittest.IsolatedAsyncioTestCase):
    gate_value = "whitelist"

    async def asyncSetUp(self):
        self._previous = config.access_gate
        config.access_gate = self.gate_value
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        config.access_gate = self._previous

    def headers_for(self, payload: dict) -> dict:
        token = admin_auth_manager.create_session_token(
            admin_label=payload.get("sub", "gate_test"),
            role=payload.get("role", "admin"),
            is_allowed=payload.get("is_allowed", True),
        )
        return {"X-Admin-Session": token}


class TestGateBlocksAnonymous(GateTestCase):
    async def test_pages_redirect_to_login(self):
        for path in GATED_PAGES:
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertEqual(res.status_code, 302)
                self.assertIn("/login", res.headers["location"])

    async def test_apis_return_401_json(self):
        for path in GATED_APIS:
            with self.subTest(path=path):
                res = await self.client.get(path, headers={"Accept": "application/json"})
                self.assertEqual(res.status_code, 401)
                body = res.json()
                self.assertTrue(body.get("access_gate"))
                self.assertIn("freigeschaltet", body.get("detail", ""))

    async def test_public_paths_stay_reachable(self):
        for path in PUBLIC_PATHS:
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertEqual(res.status_code, 200, f"{path} -> {res.status_code}")

    async def test_robots_and_noindex_header(self):
        robots = await self.client.get("/robots.txt")
        self.assertIn("Disallow: /", robots.text)

        res = await self.client.get("/login")
        self.assertEqual(res.headers.get("x-robots-tag"), "noindex, nofollow")

        blocked = await self.client.get("/public")
        self.assertEqual(blocked.headers.get("x-robots-tag"), "noindex, nofollow")

    async def test_blocked_requests_are_not_tracked(self):
        before = len(await self._recent_page_views())
        for _ in range(3):
            await self.client.get("/public")
        after = len(await self._recent_page_views())
        self.assertEqual(before, after, "Gesperrte Aufrufe dürfen kein Page-View erzeugen")

    async def _recent_page_views(self):
        from shared.db import get_db

        with get_db() as conn:
            rows = conn.execute("SELECT id FROM page_views ORDER BY id DESC LIMIT 50").fetchall()
        return rows


class TestGateAllowsAuthorized(GateTestCase):
    async def test_admin_session_gets_through(self):
        # Seiten-Routen lesen die Session ausschließlich aus dem Cookie.
        token = admin_auth_manager.create_session_token(admin_label="page_admin")
        self.client.cookies.set(AdminAuthManager.COOKIE_NAME, token)
        for path in ("/", "/public", "/admin", "/api/overview", "/api/public/overview"):
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertEqual(res.status_code, 200, f"{path} -> {res.status_code}")

    async def test_admin_session_via_header_for_api(self):
        headers = self.headers_for({"role": "admin"})
        res = await self.client.get("/api/overview", headers=headers)
        self.assertEqual(res.status_code, 200)

    async def test_whitelist_user_gets_pages(self):
        headers = self.headers_for({"role": "user", "is_allowed": True})
        res = await self.client.get("/public", headers=headers)
        self.assertEqual(res.status_code, 200)
        res = await self.client.get("/api/public/overview", headers=headers)
        self.assertEqual(res.status_code, 200)

    async def test_whitelist_user_stays_out_of_admin_api(self):
        headers = self.headers_for({"role": "user", "is_allowed": True})
        res = await self.client.get("/api/settings", headers=headers)
        self.assertEqual(res.status_code, 403)

    async def test_cookie_is_accepted(self):
        token = admin_auth_manager.create_session_token(admin_label="cookie_admin")
        self.client.cookies.set(AdminAuthManager.COOKIE_NAME, token)
        res = await self.client.get("/api/overview")
        self.assertEqual(res.status_code, 200)

    async def test_api_key_is_accepted(self):
        res = await self.client.get("/api/overview", headers={"X-API-Key": "test-api-key"})
        self.assertEqual(res.status_code, 200)

    async def test_invalid_token_is_rejected(self):
        res = await self.client.get("/api/overview", headers={"X-Admin-Session": "forged.token"})
        self.assertEqual(res.status_code, 401)


class TestGateDisabled(GateTestCase):
    gate_value = "off"

    async def test_public_pages_are_open_without_login(self):
        for path in ("/", "/public", "/api/public/overview"):
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertEqual(res.status_code, 200)

    async def test_no_noindex_header(self):
        res = await self.client.get("/public")
        self.assertIsNone(res.headers.get("x-robots-tag"))

    async def test_robots_allows_indexing(self):
        res = await self.client.get("/robots.txt")
        self.assertIn("Allow: /", res.text)


class TestGateHelpers(unittest.TestCase):
    def test_exempt_paths(self):
        for path in ("/login", "/api/auth/telegram/verify", "/api/miniapp/auth/status", "/api/health"):
            self.assertTrue(access_gate.is_exempt_path(path), path)
        self.assertTrue(access_gate.is_exempt_path("/static/common.js"))

    def test_data_paths_are_gated(self):
        for path in ("/", "/public", "/api/public/overview", "/api/overview", "/api/miniapp/data", "/admin"):
            self.assertFalse(access_gate.is_exempt_path(path), path)

    def test_session_grants_access(self):
        self.assertFalse(access_gate.session_grants_access(None))
        self.assertFalse(access_gate.session_grants_access({}))
        self.assertFalse(access_gate.session_grants_access({"role": "user", "is_allowed": False}))
        self.assertTrue(access_gate.session_grants_access({"role": "user", "is_allowed": True}))
        self.assertTrue(access_gate.session_grants_access({"role": "admin"}))

    def test_wants_json(self):
        self.assertTrue(access_gate.wants_json("/api/overview"))
        self.assertTrue(access_gate.wants_json("/public", "application/json"))
        self.assertFalse(access_gate.wants_json("/public", "text/html"))


class TestSessionTtlDuringGate(unittest.TestCase):
    def test_ttl_is_24h_while_gate_is_active(self):
        previous = config.access_gate
        try:
            config.access_gate = "whitelist"
            self.assertEqual(admin_auth_manager.session_ttl_seconds(), AdminAuthManager.SESSION_TTL_GATED_SECONDS)
            config.access_gate = "off"
            self.assertEqual(admin_auth_manager.session_ttl_seconds(), AdminAuthManager.SESSION_TTL_SECONDS)
        finally:
            config.access_gate = previous

    def test_new_tokens_expire_within_ttl(self):
        import time

        previous = config.access_gate
        try:
            config.access_gate = "whitelist"
            payload = admin_auth_manager.verify_session_token(admin_auth_manager.create_session_token())
            self.assertIsNotNone(payload)
            self.assertLessEqual(payload["exp"] - int(time.time()), AdminAuthManager.SESSION_TTL_GATED_SECONDS + 2)
        finally:
            config.access_gate = previous


if __name__ == "__main__":
    unittest.main()
