"""
Lifecycle-Guards für die eingefrorene Telegram Mini-App.

Die Mini-App ist Legacy: Bei ``MINIAPP_ENABLED=0`` (Default) müssen alle
Einstiegspfade auf das responsive Web-Panel umleiten und in der Oberfläche
ausgeblendet sein. Bei ``1`` bleibt der alte Stand erreichbar.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from unittest.mock import patch

import httpx

from app import app
from shared.config import config


class TestMiniAppLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_frozen_routes_redirect_to_web_panel(self):
        with patch.object(config, "miniapp_enabled", False):
            for path in ("/miniapp", "/app", "/webapp"):
                with self.subTest(path=path):
                    res = await self.client.get(path)
                    self.assertEqual(res.status_code, 302)
                    self.assertIn("/login", res.headers["location"])
                    self.assertIn("next=%2Fpublic", res.headers["location"])

    async def test_enabled_route_renders_miniapp(self):
        with patch.object(config, "miniapp_enabled", True):
            res = await self.client.get("/miniapp")
            self.assertEqual(res.status_code, 200)
            self.assertIn("miniapp.css", res.text)
            self.assertIn("TT-INTELLIGENCE", res.text)

    async def test_public_page_hides_miniapp_links_when_frozen(self):
        with patch.object(config, "miniapp_enabled", False):
            res = await self.client.get("/public")
            self.assertEqual(res.status_code, 200)
            self.assertNotIn('href="miniapp"', res.text)

    async def test_public_page_shows_miniapp_links_when_enabled(self):
        with patch.object(config, "miniapp_enabled", True):
            res = await self.client.get("/public")
            self.assertEqual(res.status_code, 200)
            self.assertIn('href="miniapp"', res.text)


if __name__ == "__main__":
    unittest.main()
