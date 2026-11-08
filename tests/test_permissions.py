"""
Tests für das feingranulare Rollen-/Rechte-System.

Die Tests prüfen sowohl die reine Rechte-Matrix als auch die HTTP-Durchsetzung
für viewer, user, moderator und admin.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from unittest.mock import patch

import httpx

from app import app
from shared import access_gate
from shared.auth_store import AdminAuthManager, admin_auth_manager
from shared.db.users import check_telegram_user_access, upsert_telegram_user_permission
from shared.permissions import (
    PERM_ANALYTICS_VIEW,
    PERM_CHATINTEL_VIEW,
    PERM_CRM_EDIT,
    PERM_EXPORT_DOWNLOAD,
    PERM_PUBLIC_VIEW,
    PERM_RADAR_VIEW,
    PERM_SETTINGS_MANAGE,
    PERM_SYSTEM_VIEW,
    PERM_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    ROLE_VIEWER,
    has_permission,
    normalize_role,
    permissions_for,
    role_label,
)


def _payload(role: str, is_allowed=1) -> dict:
    return {"sub": "permission_test", "role": role, "is_allowed": is_allowed}


class TestPermissionMatrix(unittest.TestCase):
    def test_roles_are_normalized(self):
        self.assertEqual(normalize_role("public"), ROLE_VIEWER)
        self.assertEqual(normalize_role("gast"), ROLE_VIEWER)
        self.assertEqual(normalize_role("member"), ROLE_USER)
        self.assertEqual(normalize_role("mod"), ROLE_MODERATOR)
        self.assertEqual(normalize_role("administrator"), ROLE_ADMIN)
        self.assertEqual(normalize_role("unbekannt"), ROLE_VIEWER)

    def test_viewer_only_has_public_permission(self):
        perms = permissions_for(ROLE_VIEWER)
        self.assertIn(PERM_PUBLIC_VIEW, perms)
        self.assertNotIn(PERM_RADAR_VIEW, perms)
        self.assertNotIn(PERM_ANALYTICS_VIEW, perms)

    def test_user_has_whitelist_read_permissions(self):
        perms = permissions_for(ROLE_USER)
        self.assertIn(PERM_RADAR_VIEW, perms)
        self.assertIn(PERM_CHATINTEL_VIEW, perms)
        self.assertNotIn(PERM_ANALYTICS_VIEW, perms)
        self.assertNotIn(PERM_CRM_EDIT, perms)

    def test_moderator_is_read_only(self):
        perms = permissions_for(ROLE_MODERATOR)
        self.assertIn(PERM_ANALYTICS_VIEW, perms)
        self.assertIn(PERM_EXPORT_DOWNLOAD, perms)
        self.assertIn(PERM_SYSTEM_VIEW, perms)
        self.assertNotIn(PERM_CRM_EDIT, perms)
        self.assertNotIn(PERM_SETTINGS_MANAGE, perms)
        self.assertNotIn(PERM_USERS_MANAGE, perms)

    def test_admin_has_all_permissions(self):
        for permission in (
            PERM_ANALYTICS_VIEW,
            PERM_RADAR_VIEW,
            PERM_CHATINTEL_VIEW,
            PERM_EXPORT_DOWNLOAD,
            PERM_SYSTEM_VIEW,
            PERM_CRM_EDIT,
            PERM_SETTINGS_MANAGE,
            PERM_USERS_MANAGE,
        ):
            with self.subTest(permission=permission):
                self.assertTrue(has_permission(_payload(ROLE_ADMIN), permission))

    def test_blocked_user_has_no_permissions(self):
        self.assertEqual(permissions_for(ROLE_ADMIN, -1), frozenset())
        self.assertEqual(permissions_for(ROLE_ADMIN, 0), frozenset())
        self.assertFalse(has_permission(_payload(ROLE_ADMIN, -1), PERM_ANALYTICS_VIEW))
        self.assertFalse(has_permission(_payload(ROLE_ADMIN, 0), PERM_ANALYTICS_VIEW))

    def test_role_labels(self):
        self.assertIn("Gast", role_label(ROLE_VIEWER))
        self.assertIn("Moderator", role_label(ROLE_MODERATOR))
        self.assertIn("Administrator", role_label(ROLE_ADMIN))


class TestAccessGateRoles(unittest.TestCase):
    def test_viewer_passes_gate(self):
        self.assertTrue(access_gate.session_grants_access(_payload(ROLE_VIEWER, True)))

    def test_blocked_admin_is_rejected(self):
        self.assertFalse(access_gate.session_grants_access(_payload(ROLE_ADMIN, -1)))
        self.assertFalse(access_gate.session_grants_access(_payload(ROLE_ADMIN, 0)))

    def test_unknown_role_is_rejected(self):
        self.assertFalse(access_gate.session_grants_access(_payload("unbekannt", True)))


class TestPublicModeRole(unittest.TestCase):
    def test_non_whitelisted_public_user_becomes_viewer(self):
        with patch("shared.db.users.get_telegram_access_mode", return_value="public"):
            access = check_telegram_user_access(
                telegram_id=99000001,
                username="public_viewer_test",
                first_name="Viewer",
                chat_id=99000001,
            )
        self.assertTrue(access["allowed"])
        self.assertEqual(access["role"], ROLE_VIEWER)
        self.assertFalse(access["is_whitelisted"])

    def test_whitelisted_public_user_keeps_role(self):
        upsert_telegram_user_permission(
            "99000002",
            is_allowed=1,
            role=ROLE_MODERATOR,
            first_name="Moderator",
        )
        with patch("shared.db.users.get_telegram_access_mode", return_value="public"):
            access = check_telegram_user_access(
                telegram_id=99000002,
                username="public_moderator_test",
                first_name="Moderator",
                chat_id=99000002,
            )
        self.assertTrue(access["allowed"])
        self.assertEqual(access["role"], ROLE_MODERATOR)
        self.assertTrue(access["is_whitelisted"])

    def test_invalid_role_is_rejected_by_upsert(self):
        with self.assertRaises(ValueError):
            upsert_telegram_user_permission("99000003", role="superuser")


class ApiRoleTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    def token(self, role: str, is_allowed=1) -> str:
        return admin_auth_manager.create_session_token(
            admin_label=f"test_{role}",
            role=role,
            is_allowed=bool(is_allowed) if is_allowed in (0, 1) else True,
        )

    def headers(self, role: str, is_allowed=1) -> dict:
        return {"X-Admin-Session": self.token(role, is_allowed)}

    def cookie_headers(self, role: str, is_allowed=1) -> dict:
        self.client.cookies.set(AdminAuthManager.COOKIE_NAME, self.token(role, is_allowed))
        return {}


class TestApiRoleMatrix(ApiRoleTestCase):
    async def test_viewer_may_only_read_public_api(self):
        headers = self.headers(ROLE_VIEWER)
        self.assertEqual((await self.client.get("/api/public/overview", headers=headers)).status_code, 200)
        for path in ("/api/overview", "/api/donor-radar", "/api/chat-logs", "/api/chat-intelligence/sessions", "/api/settings"):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 403)

    async def test_user_may_read_radar_and_chatintel_but_not_stats(self):
        headers = self.headers(ROLE_USER)
        for path in ("/api/donor-radar", "/api/chat-logs", "/api/chat-intelligence/sessions"):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 200)
        for path in ("/api/overview", "/api/analytics", "/api/settings"):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 403)

    async def test_moderator_may_read_stats_and_exports(self):
        headers = self.headers(ROLE_MODERATOR)
        for path in (
            "/api/overview",
            "/api/analytics",
            "/api/battles",
            "/api/battles/stats",
            "/api/site-analytics",
            "/api/system/status",
            "/api/v1/reports/daily",
            "/api/export/gifts.csv",
            "/api/export/battles.csv",
            "/api/donor-radar",
            "/api/chat-logs",
        ):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 200)

    async def test_moderator_may_not_write_or_manage(self):
        headers = self.headers(ROLE_MODERATOR)
        cases = (
            ("GET", "/api/settings"),
            ("GET", "/api/telegram/users"),
            ("POST", "/api/streamers"),
            ("POST", "/api/gifts"),
            ("POST", "/api/demo/seed"),
            ("GET", "/api/admin/sqlite/inspect"),
            ("POST", "/api/donor-radar/donors/test/crm"),
            ("POST", "/api/donor-radar/donors/test/toggle-vip"),
        )
        for method, path in cases:
            with self.subTest(method=method, path=path):
                res = await self.client.request(method, path, headers=headers, json={})
                self.assertEqual(res.status_code, 403)

    async def test_admin_may_manage(self):
        headers = self.headers(ROLE_ADMIN)
        for path in ("/api/settings", "/api/telegram/users", "/api/overview", "/api/system/status"):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 200)

    async def test_miniapp_status_exposes_permissions(self):
        headers = self.headers(ROLE_MODERATOR)
        res = await self.client.get("/api/miniapp/auth/status", headers=headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["role"], ROLE_MODERATOR)
        self.assertIn(PERM_ANALYTICS_VIEW, body["permissions"])
        self.assertNotIn(PERM_CRM_EDIT, body["permissions"])


class TestPageRoleMatrix(ApiRoleTestCase):
    async def test_stats_page(self):
        self.cookie_headers(ROLE_MODERATOR)
        self.assertEqual((await self.client.get("/stats")).status_code, 200)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_USER)
        self.assertEqual((await self.client.get("/stats")).status_code, 302)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_VIEWER)
        self.assertEqual((await self.client.get("/stats")).status_code, 302)

    async def test_admin_page_is_admin_only(self):
        self.client.cookies.clear()
        self.cookie_headers(ROLE_MODERATOR)
        self.assertEqual((await self.client.get("/admin")).status_code, 302)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_ADMIN)
        self.assertEqual((await self.client.get("/admin")).status_code, 200)

    async def test_radar_page_requires_radar_permission(self):
        self.client.cookies.clear()
        self.cookie_headers(ROLE_VIEWER)
        self.assertEqual((await self.client.get("/donor-radar")).status_code, 302)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_USER)
        self.assertEqual((await self.client.get("/donor-radar")).status_code, 200)

    async def test_chatintel_page_requires_chatintel_permission(self):
        self.client.cookies.clear()
        self.cookie_headers(ROLE_VIEWER)
        self.assertEqual((await self.client.get("/chat-intelligence")).status_code, 403)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_USER)
        self.assertEqual((await self.client.get("/chat-intelligence")).status_code, 200)

    async def test_site_analytics_page_requires_analytics_permission(self):
        self.client.cookies.clear()
        self.cookie_headers(ROLE_USER)
        self.assertEqual((await self.client.get("/site-analytics")).status_code, 302)

        self.client.cookies.clear()
        self.cookie_headers(ROLE_MODERATOR)
        self.assertEqual((await self.client.get("/site-analytics")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
