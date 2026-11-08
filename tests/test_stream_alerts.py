"""
Tests für Live-Alert-Abonnements (Telegram-Gruppen) und Session-Helfer.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from shared.contracts import CHANNEL_LIVE_STATUS, EVENT_LIVE_STATUS
from shared.database import (
    add_streamer_alert,
    end_stream_session,
    get_active_stream_session,
    list_streamer_alert_subscriptions,
    mark_streamer_alert_notified,
    remove_streamer_alert,
    start_stream_session,
    upsert_streamer,
)


class TestStreamerAlerts(unittest.TestCase):
    def setUp(self):
        self.streamer = upsert_streamer(
            "alert_test_streamer",
            display_name="Alert Test",
            avatar_url="https://example.invalid/avatar.jpg",
        )
        self.streamer_id = int(self.streamer["id"])
        self.chat_a = -1009000000001
        self.chat_b = -1009000000002

    def _clear(self):
        remove_streamer_alert(self.streamer_id, self.chat_a)
        remove_streamer_alert(self.streamer_id, self.chat_b)

    def test_add_and_list_alerts(self):
        self._clear()
        add_streamer_alert(
            self.streamer_id,
            self.chat_a,
            chat_title="Testgruppe A",
            created_by_telegram_id=123,
            created_by_username="admin",
        )
        add_streamer_alert(
            self.streamer_id,
            self.chat_b,
            chat_title="Testgruppe B",
        )

        by_streamer = list_streamer_alert_subscriptions(streamer_id=self.streamer_id)
        self.assertEqual(len(by_streamer), 2)
        self.assertEqual({int(a["chat_id"]) for a in by_streamer}, {self.chat_a, self.chat_b})
        self.assertEqual(by_streamer[0]["streamer_username"], "alert_test_streamer")

        by_chat = list_streamer_alert_subscriptions(chat_id=self.chat_a)
        self.assertEqual(len(by_chat), 1)
        self.assertEqual(int(by_chat[0]["streamer_id"]), self.streamer_id)
        self.assertEqual(by_chat[0]["chat_title"], "Testgruppe A")

    def test_duplicate_subscription_is_updated_not_duplicated(self):
        self._clear()
        first = add_streamer_alert(self.streamer_id, self.chat_a, chat_title="Alt")
        second = add_streamer_alert(self.streamer_id, self.chat_a, chat_title="Neu")
        self.assertEqual(int(first["id"]), int(second["id"]))
        self.assertEqual(second["chat_title"], "Neu")

        subscriptions = list_streamer_alert_subscriptions(chat_id=self.chat_a)
        self.assertEqual(len(subscriptions), 1)

    def test_remove_alert(self):
        self._clear()
        add_streamer_alert(self.streamer_id, self.chat_a, chat_title="Test")
        self.assertTrue(remove_streamer_alert(self.streamer_id, self.chat_a))
        self.assertFalse(remove_streamer_alert(self.streamer_id, self.chat_a))
        self.assertEqual(list_streamer_alert_subscriptions(chat_id=self.chat_a), [])

    def test_mark_notified_is_idempotent_per_session(self):
        self._clear()
        alert = add_streamer_alert(self.streamer_id, self.chat_a, chat_title="Test")

        self.assertTrue(mark_streamer_alert_notified(int(alert["id"]), 4242))
        self.assertFalse(mark_streamer_alert_notified(int(alert["id"]), 4242))
        self.assertTrue(mark_streamer_alert_notified(int(alert["id"]), 4243))

        subscriptions = list_streamer_alert_subscriptions(chat_id=self.chat_a)
        self.assertEqual(int(subscriptions[0]["last_notified_session_id"]), 4243)


class TestActiveStreamSession(unittest.TestCase):
    def test_active_session_lifecycle(self):
        streamer = upsert_streamer("alert_session_streamer")
        streamer_id = int(streamer["id"])

        self.assertIsNone(get_active_stream_session(streamer_id))

        session_id = start_stream_session(streamer_id, room_id="room-1", title="Test")
        active = get_active_stream_session(streamer_id)
        self.assertIsNotNone(active)
        self.assertEqual(int(active["id"]), int(session_id))

        # Erneuter Aufruf mit gleichem Room liefert die bestehende Session.
        same_session_id = start_stream_session(streamer_id, room_id="room-1", title="Test")
        self.assertEqual(int(same_session_id), int(session_id))

        end_stream_session(streamer_id, session_id)
        self.assertIsNone(get_active_stream_session(streamer_id))


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)

    async def send_photo(self, **kwargs):
        self.messages.append(kwargs)


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()


class TestTelegramAlertDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_send_and_deduplicate_live_alert(self):
        from telegram_service import TelegramBotService

        streamer = upsert_streamer(
            "alert_dispatch_streamer",
            display_name="Dispatch Test",
            avatar_url="",
        )
        streamer_id = int(streamer["id"])
        chat_id = -1009000000100
        remove_streamer_alert(streamer_id, chat_id)
        add_streamer_alert(streamer_id, chat_id, chat_title="Dispatch Gruppe")

        service = TelegramBotService()
        service._state = "running"
        service._app = FakeApp()

        payload = {
            "type": EVENT_LIVE_STATUS,
            "streamer_id": streamer_id,
            "username": "alert_dispatch_streamer",
            "display_name": "Dispatch Test",
            "avatar_url": "",
            "room_id": "room-dispatch",
            "session_id": 9001,
            "title": "Dispatch Stream",
            "timestamp": "2026-11-08T16:00:00",
        }

        await service._send_live_status_alert(payload)
        self.assertEqual(len(service._app.bot.messages), 1)
        message = service._app.bot.messages[0]
        self.assertEqual(int(message["chat_id"]), chat_id)
        self.assertIn("ist jetzt LIVE", message["text"])

        # Derselbe Session-Alert darf nicht doppelt verschickt werden.
        await service._send_live_status_alert(payload)
        self.assertEqual(len(service._app.bot.messages), 1)

        subscriptions = list_streamer_alert_subscriptions(chat_id=chat_id)
        self.assertEqual(int(subscriptions[0]["last_notified_session_id"]), 9001)
        remove_streamer_alert(streamer_id, chat_id)


class TestAlertCommand(unittest.IsolatedAsyncioTestCase):
    async def test_alert_command_add_list_and_remove(self):
        from telegram_service import TelegramBotService

        streamer = upsert_streamer("alert_command_streamer", display_name="Command Test")
        streamer_id = int(streamer["id"])
        chat_id = -1009000000200
        remove_streamer_alert(streamer_id, chat_id)

        replies = []
        message = SimpleNamespace(reply_text=AsyncMock(side_effect=lambda text, **kw: replies.append(text)))
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=chat_id, title="Command Gruppe", type="group"),
            effective_user=SimpleNamespace(id=555, username="admin"),
        )
        context = SimpleNamespace(args=["@alert_command_streamer"])

        service = TelegramBotService()
        service._authorize = AsyncMock(return_value={"permissions": {"streamers.manage"}})

        await service._cmd_alert(update, context)
        self.assertIn("aktiviert", replies[-1])
        subscriptions = list_streamer_alert_subscriptions(chat_id=chat_id)
        self.assertEqual(len(subscriptions), 1)

        context.args = ["list"]
        await service._cmd_alert(update, context)
        self.assertIn("@alert_command_streamer", replies[-1])

        context.args = ["off", "@alert_command_streamer"]
        await service._cmd_alert(update, context)
        self.assertIn("deaktiviert", replies[-1])
        self.assertEqual(list_streamer_alert_subscriptions(chat_id=chat_id), [])


class TestLiveStatusEvent(unittest.IsolatedAsyncioTestCase):
    async def test_publish_live_status_payload(self):
        from tiktok_service import StreamerWorker

        captured = {}

        class FakeBus:
            def publish_sync(self, channel, message):
                captured["channel"] = channel
                captured["message"] = message

        worker = StreamerWorker(streamer_id=42, username="@AlertStreamer")
        with patch("tiktok_service.get_bus", return_value=FakeBus()):
            await worker._publish_live_status_event(
                session_id=777,
                room_id="room-42",
                title="Teststream",
                display_name="Alert Streamer",
                avatar_url="https://example.invalid/alert.jpg",
                timestamp="2026-11-08T15:00:00",
            )

        self.assertEqual(captured["channel"], CHANNEL_LIVE_STATUS)
        payload = captured["message"]
        self.assertEqual(payload["type"], EVENT_LIVE_STATUS)
        self.assertEqual(payload["streamer_id"], 42)
        self.assertEqual(payload["username"], "alertstreamer")
        self.assertEqual(payload["session_id"], 777)
        self.assertEqual(payload["room_id"], "room-42")
        self.assertEqual(payload["title"], "Teststream")


if __name__ == "__main__":
    unittest.main()
