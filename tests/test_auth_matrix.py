"""
Tests für die Rechte-Matrix der API: Admin-Routen, Rollen und API-Key-Varianten.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

import httpx

from app import app
from shared.auth_store import admin_auth_manager

ADMIN_ENDPOINTS = (
    "/api/overview",
    "/api/analytics",
    "/api/settings",
    "/api/battles",
    "/api/system/status",
    "/api/telegram/users",
    "/api/site-analytics",
    "/api/admin/sqlite/inspect",
)


class TestAuthorizationMatrix(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_admin_endpoints_reject_anonymous(self):
        for path in ADMIN_ENDPOINTS:
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertIn(res.status_code, (401, 403), f"{path} -> {res.status_code}")

    async def test_wrong_api_key_is_rejected(self):
        res = await self.client.get("/api/overview", headers={"X-API-Key": "definitiv-falsch"})
        self.assertEqual(res.status_code, 401)

    async def test_api_key_header_is_accepted(self):
        res = await self.client.get("/api/overview", headers={"X-API-Key": "test-api-key"})
        self.assertEqual(res.status_code, 200)

    async def test_api_key_query_parameter_is_accepted(self):
        res = await self.client.get("/api/overview", params={"api_key": "test-api-key"})
        self.assertEqual(res.status_code, 200)

    async def test_admin_session_grants_admin_access(self):
        token = admin_auth_manager.create_session_token(admin_label="matrix_admin")
        res = await self.client.get("/api/overview", headers={"X-Admin-Session": token})
        self.assertEqual(res.status_code, 200)

    async def test_bearer_token_is_accepted(self):
        token = admin_auth_manager.create_session_token(admin_label="matrix_admin")
        res = await self.client.get("/api/overview", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)

    async def test_whitelist_user_role_is_forbidden_on_admin_api(self):
        token = admin_auth_manager.create_session_token(role="user", is_allowed=True)
        res = await self.client.get("/api/overview", headers={"X-Admin-Session": token})
        self.assertEqual(res.status_code, 403)

    async def test_whitelist_user_role_can_read_radar(self):
        token = admin_auth_manager.create_session_token(role="user", is_allowed=True)
        res = await self.client.get("/api/donor-radar", headers={"X-Admin-Session": token})
        self.assertEqual(res.status_code, 200)

    async def test_whitelist_user_role_can_read_chat_logs(self):
        token = admin_auth_manager.create_session_token(role="user", is_allowed=True)
        res = await self.client.get("/api/chat-logs", headers={"X-Admin-Session": token})
        self.assertEqual(res.status_code, 200)

    async def test_anonymous_may_not_read_chat_logs(self):
        res = await self.client.get("/api/chat-logs")
        self.assertIn(res.status_code, (401, 403))


class TestAuthEndpointRateLimit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app, client=("198.51.100.23", 12345))
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        from shared.ratelimit import reset_rate_limit

        await reset_rate_limit("auth_password", "198.51.100.23")

    async def test_password_endpoint_locks_after_repeated_failures(self):
        statuses = []
        for _ in range(6):
            res = await self.client.post("/api/auth/password", json={"password": "falsch"})
            statuses.append(res.status_code)

        self.assertEqual(statuses[:5], [401] * 5)
        self.assertEqual(statuses[5], 429)
        self.assertIn("retry-after", {k.lower() for k in res.headers})


if __name__ == "__main__":
    unittest.main()
