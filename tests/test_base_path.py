"""
Tests für den Betrieb unter einem URL-Unterpfad (z.B. https://host/track).

Der Reverse-Proxy setzt ``X-Forwarded-Prefix``; die App entfernt den Präfix
vor dem Routing und erzeugt Links/Redirects wieder mit Präfix.
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


class TestBasePathDeployment(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")
        self.base_path_patch = patch.object(config, "app_base_path", "/track")
        self.base_path_patch.start()

    async def asyncTearDown(self):
        self.base_path_patch.stop()
        await self.client.aclose()

    def prefixed(self, path: str) -> str:
        return {"X-Forwarded-Prefix": "/track"} if path else {}

    async def test_health_works_with_and_without_prefix(self):
        # Der Proxy darf den Präfix bereits entfernt haben oder ihn durchreichen.
        for path in ("/api/health", "/track/api/health"):
            with self.subTest(path=path):
                res = await self.client.get(path, headers=self.prefixed(path))
                self.assertEqual(res.status_code, 200)

    async def test_static_assets_work_under_prefix(self):
        for path in ("/track/static/style.css", "/track/static/dashboard.js"):
            with self.subTest(path=path):
                res = await self.client.get(path, headers=self.prefixed(path))
                self.assertEqual(res.status_code, 200)
                self.assertGreater(len(res.content), 0)

    async def test_landing_page_gets_base_tag_and_relative_assets(self):
        res = await self.client.get("/track/", headers=self.prefixed("/track/"))
        self.assertEqual(res.status_code, 200)
        self.assertIn('<base href="/track/"', res.text)
        self.assertIn('href="static/landing.css', res.text)
        self.assertNotIn('href="/static/', res.text)

    async def test_root_deployment_keeps_root_base(self):
        res = await self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn('<base href="/"', res.text)
        self.assertIn('href="static/', res.text)

    async def test_login_page_uses_prefixed_base_and_relative_assets(self):
        res = await self.client.get("/track/login", headers=self.prefixed("/track/login"))
        self.assertEqual(res.status_code, 200)
        self.assertIn('<base href="/track/"', res.text)
        self.assertIn('href="static/style.css', res.text)
        self.assertIn('src="static/common.js', res.text)
        self.assertIn('fetch("api/auth/password"', res.text)
        self.assertNotIn('fetch("/api/', res.text)

    async def test_redirects_are_prefixed(self):
        res = await self.client.get("/track/admin", headers=self.prefixed("/track/admin"), follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers["location"], "/track/login")

    async def test_untrusted_prefix_is_ignored(self):
        res = await self.client.get("/", headers={"X-Forwarded-Prefix": "/evil"})
        self.assertEqual(res.status_code, 200)
        self.assertIn('<base href="/"', res.text)
        self.assertNotIn('<base href="/evil/"', res.text)


if __name__ == "__main__":
    unittest.main()
