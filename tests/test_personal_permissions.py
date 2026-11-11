"""
Tests für die persönliche Rechte-Schicht (Phase 1).

Deckt die reine Auflösung, die DB-Speicherung und die HTTP-Durchsetzung ab.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

import httpx

from app import app
from shared.auth_store import admin_auth_manager
from shared.db.users import (
    check_telegram_user_access,
    get_telegram_user_by_identifier,
    get_telegram_user_permission_overrides,
    list_telegram_users,
    replace_telegram_user_permissions,
    upsert_telegram_user_permission,
)
from shared.permissions import (
    PERM_ANALYTICS_VIEW,
    PERM_BOT_ANALYTICS_VIEW,
    PERM_EXPORT_DOWNLOAD,
    PERM_RADAR_VIEW,
    PERM_SYSTEM_MANAGE,
    PERM_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    ROLE_VIEWER,
    bot_command_allowed,
    has_permission,
    permissions_for,
)


def _payload(role: str, is_allowed=1, grants=(), denies=()) -> dict:
    return {
        "sub": "personal_permission_test",
        "role": role,
        "is_allowed": is_allowed,
        "permission_grants": list(grants),
        "permission_denies": list(denies),
    }


class TestOverrideResolution(unittest.TestCase):
    def test_grant_adds_permission_without_changing_role(self):
        perms = permissions_for(ROLE_USER, grants=[PERM_ANALYTICS_VIEW])
        self.assertIn(PERM_ANALYTICS_VIEW, perms)
        self.assertIn(PERM_RADAR_VIEW, perms)
        self.assertNotIn(PERM_EXPORT_DOWNLOAD, perms)

    def test_deny_removes_inherited_permission(self):
        perms = permissions_for(ROLE_MODERATOR, denies=[PERM_ANALYTICS_VIEW])
        self.assertNotIn(PERM_ANALYTICS_VIEW, perms)
        self.assertIn(PERM_EXPORT_DOWNLOAD, perms)

    def test_deny_wins_over_grant(self):
        perms = permissions_for(
            ROLE_USER,
            grants=[PERM_ANALYTICS_VIEW],
            denies=[PERM_ANALYTICS_VIEW],
        )
        self.assertNotIn(PERM_ANALYTICS_VIEW, perms)

    def test_blocked_account_ignores_grants(self):
        self.assertEqual(
            permissions_for(ROLE_ADMIN, -1, grants=[PERM_ANALYTICS_VIEW]),
            frozenset(),
        )
        self.assertEqual(
            permissions_for(ROLE_ADMIN, 0, grants=[PERM_ANALYTICS_VIEW]),
            frozenset(),
        )

    def test_unknown_permissions_are_ignored(self):
        perms = permissions_for(ROLE_USER, grants=["does.not.exist"])
        self.assertNotIn("does.not.exist", perms)

    def test_session_payload_uses_overrides(self):
        payload = _payload(
            ROLE_USER,
            grants=[PERM_ANALYTICS_VIEW],
            denies=[PERM_RADAR_VIEW],
        )
        self.assertTrue(has_permission(payload, PERM_ANALYTICS_VIEW))
        self.assertFalse(has_permission(payload, PERM_RADAR_VIEW))

    def test_bot_command_uses_overrides(self):
        self.assertFalse(bot_command_allowed("overview", ROLE_USER, 1))
        self.assertTrue(
            bot_command_allowed(
                "overview",
                ROLE_USER,
                1,
                grants=[PERM_BOT_ANALYTICS_VIEW],
            )
        )


class TestPermissionStorage(unittest.TestCase):
    def _create_user(self, telegram_id: int, role: str = ROLE_USER) -> dict:
        return upsert_telegram_user_permission(
            str(telegram_id),
            is_allowed=1,
            role=role,
            first_name=f"Permission Test {telegram_id}",
            username_override=f"permtest_{telegram_id}",
        )

    def test_replace_and_read_overrides(self):
        user = self._create_user(88100001)
        result = replace_telegram_user_permissions(
            int(user["id"]),
            grants=[PERM_EXPORT_DOWNLOAD],
            denies=[PERM_RADAR_VIEW],
            created_by="@tester",
        )
        self.assertEqual(result["grants"], [PERM_EXPORT_DOWNLOAD])
        self.assertEqual(result["denies"], [PERM_RADAR_VIEW])
        self.assertEqual(
            get_telegram_user_permission_overrides(int(user["id"])),
            {"grants": [PERM_EXPORT_DOWNLOAD], "denies": [PERM_RADAR_VIEW]},
        )

    def test_replace_is_atomic_and_clears_old_entries(self):
        user = self._create_user(88100002)
        replace_telegram_user_permissions(int(user["id"]), grants=[PERM_EXPORT_DOWNLOAD])
        replace_telegram_user_permissions(int(user["id"]), denies=[PERM_RADAR_VIEW])
        self.assertEqual(
            get_telegram_user_permission_overrides(int(user["id"])),
            {"grants": [], "denies": [PERM_RADAR_VIEW]},
        )

    def test_unknown_permission_is_rejected(self):
        user = self._create_user(88100003)
        with self.assertRaises(ValueError):
            replace_telegram_user_permissions(int(user["id"]), grants=["frei.erfunden"])

    def test_overlapping_grant_and_deny_is_rejected(self):
        user = self._create_user(88100004)
        with self.assertRaises(ValueError):
            replace_telegram_user_permissions(
                int(user["id"]),
                grants=[PERM_ANALYTICS_VIEW],
                denies=[PERM_ANALYTICS_VIEW],
            )

    def test_list_users_includes_overrides_and_effective_permissions(self):
        user = self._create_user(88100005)
        replace_telegram_user_permissions(
            int(user["id"]),
            grants=[PERM_ANALYTICS_VIEW],
            denies=[PERM_RADAR_VIEW],
        )
        row = next(u for u in list_telegram_users() if int(u["id"]) == int(user["id"]))
        self.assertEqual(row["permission_grants"], [PERM_ANALYTICS_VIEW])
        self.assertEqual(row["permission_denies"], [PERM_RADAR_VIEW])
        self.assertIn(PERM_ANALYTICS_VIEW, row["effective_permissions"])
        self.assertNotIn(PERM_RADAR_VIEW, row["effective_permissions"])

    def test_access_check_includes_effective_permissions(self):
        user = self._create_user(88100006)
        replace_telegram_user_permissions(int(user["id"]), grants=[PERM_ANALYTICS_VIEW])
        access = check_telegram_user_access(
            telegram_id=88100006,
            username="permission_access_test",
            first_name="Permission Access",
            chat_id=88100006,
        )
        self.assertTrue(access["allowed"])
        self.assertEqual(access["role"], ROLE_USER)
        self.assertIn(PERM_ANALYTICS_VIEW, access["permissions"])
        self.assertEqual(access["permission_grants"], [PERM_ANALYTICS_VIEW])

    def test_identifier_lookup_supports_session_labels(self):
        user = self._create_user(88100007)
        for identifier in ("88100007", "id:88100007", "tg_88100007", f"@{user['username']}"):
            with self.subTest(identifier=identifier):
                found = get_telegram_user_by_identifier(identifier)
                self.assertIsNotNone(found)
                self.assertEqual(int(found["id"]), int(user["id"]))


class TestPermissionApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    def admin_headers(self, telegram_id=None) -> dict:
        token = admin_auth_manager.create_session_token(
            admin_label="@permission_admin",
            role=ROLE_ADMIN,
            is_allowed=True,
            telegram_id=telegram_id,
        )
        return {"X-Admin-Session": token}

    def user_headers(self, user: dict) -> dict:
        token = admin_auth_manager.create_session_token(
            admin_label=f"@{user['username']}",
            role=user.get("role") or ROLE_USER,
            is_allowed=True,
            telegram_id=int(user["telegram_id"]),
        )
        return {"X-Admin-Session": token}

    async def _create_user(self, telegram_id: int, role: str = ROLE_USER) -> dict:
        return upsert_telegram_user_permission(
            str(telegram_id),
            is_allowed=1,
            role=role,
            first_name=f"API Permission Test {telegram_id}",
            username_override=f"apipermtest_{telegram_id}",
        )

    async def test_admin_can_read_and_write_permissions(self):
        user = await self._create_user(88200001)
        headers = self.admin_headers()

        res = await self.client.get(
            f"/api/v1/telegram/users/{user['id']}/permissions", headers=headers
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["grants"], [])

        res = await self.client.put(
            f"/api/v1/telegram/users/{user['id']}/permissions",
            headers=headers,
            json={"grants": [PERM_ANALYTICS_VIEW], "denies": [PERM_RADAR_VIEW]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["grants"], [PERM_ANALYTICS_VIEW])
        self.assertEqual(body["denies"], [PERM_RADAR_VIEW])
        self.assertIn(PERM_ANALYTICS_VIEW, body["effective_permissions"])

    async def test_grant_is_applied_to_api_request_without_relogin(self):
        user = await self._create_user(88200002)
        headers = self.admin_headers()
        await self.client.put(
            f"/api/v1/telegram/users/{user['id']}/permissions",
            headers=headers,
            json={"grants": [PERM_ANALYTICS_VIEW]},
        )

        res = await self.client.get("/api/overview", headers=self.user_headers(user))
        self.assertEqual(res.status_code, 200, res.text)

    async def test_deny_is_applied_to_api_request(self):
        user = await self._create_user(88200003, role=ROLE_MODERATOR)
        headers = self.admin_headers()
        await self.client.put(
            f"/api/v1/telegram/users/{user['id']}/permissions",
            headers=headers,
            json={"denies": [PERM_ANALYTICS_VIEW]},
        )

        res = await self.client.get("/api/overview", headers=self.user_headers(user))
        self.assertEqual(res.status_code, 403, res.text)

    async def test_self_edit_is_rejected(self):
        user = await self._create_user(88200004, role=ROLE_ADMIN)
        headers = self.admin_headers(telegram_id=int(user["telegram_id"]))
        res = await self.client.put(
            f"/api/v1/telegram/users/{user['id']}/permissions",
            headers=headers,
            json={"grants": [PERM_SYSTEM_MANAGE]},
        )
        self.assertEqual(res.status_code, 403, res.text)

    async def test_critical_permission_requires_admin_role(self):
        actor = await self._create_user(88200005, role=ROLE_USER)
        target = await self._create_user(88200006, role=ROLE_USER)
        replace_telegram_user_permissions(int(actor["id"]), grants=[PERM_USERS_MANAGE, PERM_SYSTEM_MANAGE])

        token = admin_auth_manager.create_session_token(
            admin_label=f"@{actor['username']}",
            role=ROLE_USER,
            is_allowed=True,
            telegram_id=int(actor["telegram_id"]),
        )
        res = await self.client.put(
            f"/api/v1/telegram/users/{target['id']}/permissions",
            headers={"X-Admin-Session": token},
            json={"grants": [PERM_SYSTEM_MANAGE]},
        )
        self.assertEqual(res.status_code, 403, res.text)

    async def test_non_admin_cannot_grant_foreign_permission(self):
        actor = await self._create_user(88200007, role=ROLE_USER)
        target = await self._create_user(88200008, role=ROLE_USER)
        replace_telegram_user_permissions(int(actor["id"]), grants=[PERM_USERS_MANAGE])

        token = admin_auth_manager.create_session_token(
            admin_label=f"@{actor['username']}",
            role=ROLE_USER,
            is_allowed=True,
            telegram_id=int(actor["telegram_id"]),
        )
        res = await self.client.put(
            f"/api/v1/telegram/users/{target['id']}/permissions",
            headers={"X-Admin-Session": token},
            json={"grants": [PERM_EXPORT_DOWNLOAD]},
        )
        self.assertEqual(res.status_code, 403, res.text)

    async def test_non_admin_cannot_change_admin_permissions(self):
        actor = await self._create_user(88200010, role=ROLE_USER)
        target = await self._create_user(88200011, role=ROLE_ADMIN)
        replace_telegram_user_permissions(int(actor["id"]), grants=[PERM_USERS_MANAGE])

        token = admin_auth_manager.create_session_token(
            admin_label=f"@{actor['username']}",
            role=ROLE_USER,
            is_allowed=True,
            telegram_id=int(actor["telegram_id"]),
        )
        res = await self.client.put(
            f"/api/v1/telegram/users/{target['id']}/permissions",
            headers={"X-Admin-Session": token},
            json={"denies": [PERM_RADAR_VIEW]},
        )
        self.assertEqual(res.status_code, 403, res.text)

    async def test_viewer_without_users_manage_cannot_read_permissions(self):
        user = await self._create_user(88200009)
        token = admin_auth_manager.create_session_token(
            admin_label=f"@{user['username']}",
            role=ROLE_VIEWER,
            is_allowed=True,
            telegram_id=int(user["telegram_id"]),
        )
        res = await self.client.get(
            f"/api/v1/telegram/users/{user['id']}/permissions",
            headers={"X-Admin-Session": token},
        )
        self.assertEqual(res.status_code, 403, res.text)


if __name__ == "__main__":
    unittest.main()
