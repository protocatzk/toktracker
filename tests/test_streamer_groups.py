"""
Tests für Streamer-Gruppen als gemeinsamer Analyse-Scope.

Deckt CRUD/Mitgliedschaften, Analytics-, Chart- und Overview-Filter, die
Bot-Argumenterkennung sowie die REST-Endpunkte ab.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
import uuid
from datetime import datetime
from unittest.mock import patch

import httpx

from app import app
from shared import chart_views as cv
from shared import widget_chart as wc
from shared.auth_store import admin_auth_manager
from shared.db import (
    create_streamer_group,
    delete_streamer_group,
    get_analytics_data,
    get_chart_timeline,
    get_dashboard_overview,
    get_group_streamer_ids,
    get_streamer_group,
    get_streamer_group_by_name,
    init_db,
    list_streamer_groups,
    record_gift_event,
    set_streamer_group_members,
    update_streamer_group,
    upsert_streamer,
)
from telegram_service import TelegramBotService


def _unique(prefix: str = "grp") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _streamer(prefix: str = "grp") -> dict:
    return upsert_streamer(username=_unique(prefix), display_name="Test Streamer")


def _gift(streamer_id: int, coins: int, sender: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    record_gift_event(
        streamer_id=streamer_id,
        sender_username=sender,
        gift_name=f"Gift{coins}",
        diamond_count=coins,
        repeat_count=1,
        created_at=now,
    )


class TestStreamerGroupCrud(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_create_update_and_delete(self):
        name = _unique("Team")
        group = create_streamer_group(name, "Beschreibung", "#58a6ff")
        self.assertEqual(group["name"], name)
        self.assertEqual(group["member_count"], 0)

        self.assertEqual(get_streamer_group(group["id"])["name"], name)
        self.assertEqual(get_streamer_group_by_name(name.lower())["id"], group["id"])
        self.assertIn(group["id"], [g["id"] for g in list_streamer_groups()])

        updated = update_streamer_group(
            group["id"], name=name + " X", description="Neu", color="#abcdef"
        )
        self.assertEqual(updated["name"], name + " X")
        self.assertEqual(updated["description"], "Neu")

        self.assertTrue(delete_streamer_group(group["id"]))
        self.assertIsNone(get_streamer_group(group["id"]))
        self.assertFalse(delete_streamer_group(group["id"]))

    def test_duplicate_names_are_case_insensitive(self):
        name = _unique("Dupe")
        create_streamer_group(name)
        with self.assertRaises(ValueError):
            create_streamer_group(name.upper())

    def test_membership_many_to_many_and_invalid_ids(self):
        first = _streamer("member")
        second = _streamer("member")
        group_a = create_streamer_group(_unique("A"), streamer_ids=[first["id"], second["id"]])
        group_b = create_streamer_group(_unique("B"), streamer_ids=[first["id"]])

        self.assertEqual(sorted(get_group_streamer_ids(group_a["id"])), sorted([first["id"], second["id"]]))
        self.assertEqual(get_group_streamer_ids(group_b["id"]), [first["id"]])

        kept = set_streamer_group_members(group_a["id"], [first["id"], 99999999])
        self.assertEqual(kept, [first["id"]])
        self.assertEqual(get_streamer_group(group_a["id"])["member_count"], 1)

        # Streamer bleibt in Gruppe B, obwohl Gruppe A neu gesetzt wurde.
        self.assertEqual(get_group_streamer_ids(group_b["id"]), [first["id"]])


class TestGroupAnalyticsScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_analytics_chart_and_overview_are_scoped(self):
        first = _streamer("scope")
        second = _streamer("scope")
        _gift(first["id"], 100, "alice")
        _gift(second["id"], 300, "bob")
        group = create_streamer_group(_unique("Scope"), streamer_ids=[first["id"]])

        analytics = get_analytics_data(group_id=group["id"], period="all")
        self.assertEqual(analytics["totals"]["total_coins"], 100)
        self.assertEqual(analytics["selected_group"]["id"], group["id"])
        self.assertEqual(
            [row["id"] for row in analytics["streamers_ranking"]],
            [first["id"]],
        )

        timeline = get_chart_timeline(period="24h", group_id=group["id"])
        self.assertEqual(timeline["totals"]["total_coins"], 100)
        self.assertEqual(timeline["group_id"], group["id"])

        overview = get_dashboard_overview(
            period="all", group_id=group["id"], force_refresh=True
        )
        self.assertEqual(overview["totals"]["total_coins"], 100)
        self.assertEqual(overview["totals"]["streamer_count"], 1)
        self.assertEqual(
            [s["id"] for s in overview["streamers"]], [first["id"]]
        )
        self.assertTrue(
            all(g["streamer_username"] == first["username"] for g in overview["recent_gifts"])
        )

        series = wc.load_chart_series(
            "24h", "coins", group_id=group["id"], group_name=group["name"]
        )
        self.assertEqual(series.total, 100)
        self.assertTrue(series.title_text.startswith("GRUPPE ·"))

        view = cv.load_chart_view(
            "streamers",
            "all",
            "coins",
            group_id=group["id"],
            group_name=group["name"],
        )
        self.assertEqual(view.group_name, group["name"])
        self.assertEqual(view.values, (100.0,))
        self.assertIn("GRUPPE", view.caption)

    def test_empty_group_returns_empty_scope(self):
        group = create_streamer_group(_unique("Leer"))
        analytics = get_analytics_data(group_id=group["id"], period="all")
        self.assertEqual(analytics["totals"]["total_coins"], 0)
        self.assertEqual(analytics["streamers_ranking"], [])

        overview = get_dashboard_overview(
            period="all", group_id=group["id"], force_refresh=True
        )
        self.assertEqual(overview["streamers"], [])
        self.assertEqual(overview["totals"]["streamer_count"], 0)

    def test_streamer_scope_wins_over_group(self):
        first = _streamer("prec")
        second = _streamer("prec")
        _gift(first["id"], 50, "carol")
        _gift(second["id"], 80, "dave")
        group = create_streamer_group(_unique("Prec"), streamer_ids=[second["id"]])

        analytics = get_analytics_data(
            streamer_id=first["id"], period="all", group_id=group["id"]
        )
        self.assertEqual(analytics["totals"]["total_coins"], 50)


class TestGroupBotArgs(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TelegramBotService()

    def test_group_reference_parsing(self):
        self.assertEqual(self.service._group_reference("gruppe:team alpha"), "team alpha")
        self.assertEqual(self.service._group_reference("GROUP:Core"), "Core")
        self.assertEqual(self.service._group_reference("g:7"), "7")
        self.assertEqual(self.service._group_reference("@streamer"), "")

    def test_chart_args_include_group(self):
        period, metric, streamer, view, group_ref = self.service._parse_chart_args(
            ["gruppe:Team Alpha", "7d", "coins", "spender"]
        )
        self.assertEqual(period, "7d")
        self.assertEqual(metric, "coins")
        self.assertIsNone(streamer)
        self.assertEqual(view, "gifters")
        self.assertEqual(group_ref, "Team Alpha")

        # Mehrwortige Gruppennamen ohne Anführungszeichen
        self.assertEqual(
            self.service._parse_chart_args(["gruppe:Team", "Alpha", "7d"])[4],
            "Team Alpha",
        )

    def test_group_keyboard_uses_group_callbacks_and_reset(self):
        markup = self.service._chart_keyboard(
            "7d", "coins", group_id=42, view="gifts"
        )
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("chart_gview:42:7d:coins:0:gifts", callbacks)
        self.assertIn("chart_view:0:7d:coins:0:gifts", callbacks)
        self.assertIn("chart_gview:42:24h:coins:0:gifts", callbacks)
        self.assertIn("chart_pick:7d:coins:gifts", callbacks)

    def test_picker_lists_groups_before_streamers(self):
        groups = [{"id": 42, "name": "Alpha", "member_count": 3}]
        streamers = [
            {"id": 1, "username": "one", "display_name": "One", "is_live": False},
        ]
        with patch("telegram_service.list_streamer_groups", return_value=groups), patch(
            "telegram_service.list_streamers_for_picker", return_value=streamers
        ):
            text, markup = self.service._format_chart_picker("24h", "eur", 0, 999)
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertTrue(any(cb.startswith("chart_group:42:") for cb in callbacks))
        self.assertTrue(any(cb.startswith("chart_stream:1:") for cb in callbacks))
        self.assertIn("GRUPPEN", text)


class TestGroupApiEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(
            transport=self.transport, base_url="http://testserver"
        )
        self.cookies = {admin_auth_manager.COOKIE_NAME: admin_auth_manager.create_session_token()}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_group_crud_and_scoped_endpoints(self):
        streamer = _streamer("api")
        _gift(streamer["id"], 77, "erin")
        name = _unique("API")

        res = await self.client.post(
            "/api/streamer-groups",
            json={"name": name, "description": "API-Test", "streamer_ids": [streamer["id"]]},
            cookies=self.cookies,
        )
        self.assertEqual(res.status_code, 200, res.text)
        group = res.json()["group"]

        res = await self.client.get("/api/streamer-groups", cookies=self.cookies)
        self.assertEqual(res.status_code, 200)
        self.assertIn(group["id"], [g["id"] for g in res.json()["groups"]])

        res = await self.client.get(
            "/api/analytics",
            params={"period": "all", "group_id": group["id"]},
            cookies=self.cookies,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["totals"]["total_coins"], 77)
        self.assertEqual(res.json()["selected_group"]["id"], group["id"])

        res = await self.client.put(
            f"/api/streamer-groups/{group['id']}/members",
            json={"streamer_ids": []},
            cookies=self.cookies,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["group"]["member_count"], 0)

        res = await self.client.delete(
            f"/api/streamer-groups/{group['id']}", cookies=self.cookies
        )
        self.assertEqual(res.status_code, 200)

    async def test_group_scopes_overview_and_gift_export(self):
        included = _streamer("export")
        excluded = _streamer("export")
        _gift(included["id"], 12, "frank")
        _gift(excluded["id"], 34, "grace")
        group = create_streamer_group(_unique("Export"), streamer_ids=[included["id"]])

        res = await self.client.get(
            "/api/overview",
            params={"period": "all", "group_id": group["id"]},
            cookies=self.cookies,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["totals"]["total_coins"], 12)

        res = await self.client.get(
            "/api/export/gifts.csv",
            params={"group_id": group["id"]},
            cookies=self.cookies,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(included["username"], res.text)
        self.assertNotIn(excluded["username"], res.text)

    async def test_delete_unknown_group_returns_404(self):
        res = await self.client.delete("/api/streamer-groups/99999999", cookies=self.cookies)
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
