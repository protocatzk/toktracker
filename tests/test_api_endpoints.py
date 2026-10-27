"""
Tests für FastAPI REST-API & Web-Dashboard Endpunkte.
Prüft Public- und Admin-Routen, Auth-Absicherung und JSON-Schemas in-process (0 Netzwerk-Overhead).
"""
try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

import httpx

from app import app
from shared.auth_store import admin_auth_manager


class TestApiEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")
        self.admin_token = admin_auth_manager.create_session_token()

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_public_pages(self):
        # 1. Login-Seite
        res_login = await self.client.get("/login")
        self.assertEqual(res_login.status_code, 200)
        self.assertIn("login", res_login.text.lower())

        # 2. Öffentliches User-Panel
        res_public = await self.client.get("/public")
        self.assertEqual(res_public.status_code, 200)

        # 3. Öffentliche Overview-API
        res_pub_api = await self.client.get("/api/public/overview")
        self.assertEqual(res_pub_api.status_code, 200)
        data = res_pub_api.json()
        self.assertIn("totals", data)
        self.assertIn("streamers", data)

    async def test_health_endpoint_is_public_and_lean(self):
        res = await self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")
        self.assertIn("bus", body)

    async def test_api_docs_are_disabled_by_default(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                res = await self.client.get(path)
                self.assertEqual(res.status_code, 404)

    async def test_admin_auth_protection(self):
        # Ohne Token -> 401
        res_unauth = await self.client.get("/api/overview")
        self.assertEqual(res_unauth.status_code, 401)

        # Mit gültigem Token -> 200
        res_auth = await self.client.get(
            "/api/overview",
            cookies={admin_auth_manager.COOKIE_NAME: self.admin_token},
        )
        self.assertEqual(res_auth.status_code, 200)
        data = res_auth.json()
        self.assertIn("streamers", data)
        self.assertIn("recent_gifts", data)
        self.assertIn("telegram_users", data)
        self.assertIn("settings", data)

    async def test_system_status_endpoint(self):
        res = await self.client.get(
            "/api/system/status",
            cookies={admin_auth_manager.COOKIE_NAME: self.admin_token},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("workers_running", data)
        self.assertIn("telegram_bot", data)

    async def test_static_assets_served(self):
        res_js = await self.client.get("/static/dashboard.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("updateAdminBannerPreview", res_js.text)

        res_css = await self.client.get("/static/style.css")
        self.assertEqual(res_css.status_code, 200)


if __name__ == "__main__":
    unittest.main()
