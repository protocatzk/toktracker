"""
Tests für die Reconnect-/Stall-Härtung des TikTokLive-Workers.

Alle Tests laufen ohne echte TikTok-/Redis-Verbindung und ohne API-Quota.
"""
try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from shared.database import (
    get_active_stream_session,
    start_stream_session,
    upsert_streamer,
)
from tiktok_service import (
    DisconnectReason,
    ReconnectPolicy,
    StreamerMonitorManager,
    StreamerWorker,
    classify_disconnect,
    sign_cooldown_seconds,
)


class TestReconnectPolicy(unittest.TestCase):
    def test_exponential_backoff_without_jitter(self):
        policy = ReconnectPolicy(base_seconds=5, max_seconds=120, factor=1.8, jitter=0)
        self.assertAlmostEqual(policy.delay(1), 5.0)
        self.assertAlmostEqual(policy.delay(2), 9.0)
        self.assertAlmostEqual(policy.delay(3), 16.2)
        self.assertAlmostEqual(policy.delay(10), 120.0)

    def test_jitter_stays_within_bounds(self):
        policy = ReconnectPolicy(base_seconds=5, max_seconds=120, factor=1.8, jitter=0.25)
        for failures in range(1, 12):
            delay = policy.delay(failures)
            raw = min(120.0, 5.0 * (1.8 ** (failures - 1)))
            self.assertGreaterEqual(delay, max(1.0, raw * 0.75) - 0.001)
            self.assertLessEqual(delay, raw * 1.25 + 0.001)

    def test_stable_reset(self):
        policy = ReconnectPolicy(stable_reset_seconds=60)
        self.assertFalse(policy.is_stable(59.9))
        self.assertTrue(policy.is_stable(60.0))


class _RateLimitError(Exception):
    retry_after = 90

    @property
    def reset_time(self):
        return int(time.time()) + 120


class _SignError(Exception):
    reason = "SIGN_NOT_200"
    response = SimpleNamespace(status_code=503)


class _AuthError(Exception):
    reason = "AUTHENTICATED_WS"


class TestClassifyDisconnect(unittest.TestCase):
    def test_offline_value_error(self):
        exc = ValueError("invalid literal for int() with base 10: ''")
        self.assertEqual(classify_disconnect(exc), DisconnectReason.OFFLINE)

    def test_rate_limit(self):
        self.assertEqual(classify_disconnect(_RateLimitError()), DisconnectReason.RATE_LIMIT)

    def test_sign_error(self):
        self.assertEqual(classify_disconnect(_SignError()), DisconnectReason.SIGN_ERROR)

    def test_auth_error(self):
        self.assertEqual(classify_disconnect(_AuthError()), DisconnectReason.AUTH)

    def test_network_error(self):
        self.assertEqual(classify_disconnect(OSError("connection reset")), DisconnectReason.NETWORK)

    def test_unknown_error(self):
        self.assertEqual(classify_disconnect(RuntimeError("boom")), DisconnectReason.UNKNOWN)

    def test_sign_cooldown_prefers_reset_time(self):
        self.assertGreaterEqual(sign_cooldown_seconds(_RateLimitError(), default=60), 110)


class TestProxyFallback(unittest.TestCase):
    def test_ws_proxy_falls_back_to_web_proxy(self):
        from shared.config import config

        with (
            patch.object(config, "tiktok_ws_proxy", None),
            patch.object(config, "tiktok_web_proxy", "http://proxy.local:8080"),
        ):
            self.assertEqual(config.effective_ws_proxy, "http://proxy.local:8080")


class TestWorkerDiagnostics(unittest.TestCase):
    def test_snapshot_contains_health_fields(self):
        worker = StreamerWorker(streamer_id=1, username="@resilience_test")
        worker.diag.state = "connected"
        worker.diag.last_disconnect_reason = "network"
        worker.diag.close_code = 1006

        # Deterministische monotonic-Clock: auf frisch gebooteten CI-Runnern
        # kann time.monotonic() kleiner als 120 sein, wodurch die alten
        # Subtraktionen negativ wurden und der Snapshot 0 lieferte.
        with patch("tiktok_service.time.monotonic", return_value=1000.0):
            worker._last_frame_mono = 970.0
            worker._connected_at_mono = 880.0
            snap = worker.get_snapshot()
        self.assertEqual(snap["transport"], "tiktoklive")
        self.assertGreaterEqual(snap["last_frame_age_seconds"], 29)
        self.assertGreaterEqual(snap["connected_for_seconds"], 119)
        self.assertEqual(snap["last_disconnect_reason"], "network")
        self.assertEqual(snap["close_code"], 1006)

    def test_cleanup_runs_only_once(self):
        worker = StreamerWorker(streamer_id=2, username="@cleanup_test")
        with (
            patch.object(worker, "_finish_active_battle_if_any") as finish,
            patch.object(worker, "_flush_all_pending_streaks") as streaks,
            patch.object(worker, "_flush_chat_buffer") as chats,
            patch.object(worker, "_end_active_session") as session,
        ):
            worker._cleanup_runtime_state()
            worker._cleanup_runtime_state()

        finish.assert_called_once()
        streaks.assert_called_once()
        chats.assert_called_once()
        session.assert_called_once()


class TestGracefulShutdownSession(unittest.TestCase):
    def _worker_with_session(self, username):
        streamer = upsert_streamer(username)
        streamer_id = int(streamer["id"])
        session_id = start_stream_session(streamer_id, room_id="room-preserve")
        worker = StreamerWorker(streamer_id, username)
        worker.diag.session_id = session_id
        return streamer_id, session_id, worker

    def test_preserve_db_state_keeps_session_active(self):
        streamer_id, session_id, worker = self._worker_with_session(
            "alert_preserve_session"
        )
        worker._preserve_db_state = True

        with (
            patch.object(worker, "_finish_active_battle_if_any"),
            patch.object(worker, "_flush_all_pending_streaks"),
            patch.object(worker, "_flush_chat_buffer"),
        ):
            worker._cleanup_runtime_state()

        active = get_active_stream_session(streamer_id)
        self.assertIsNotNone(active)
        self.assertEqual(int(active["id"]), session_id)

    def test_manual_stop_ends_session(self):
        streamer_id, session_id, worker = self._worker_with_session(
            "alert_manual_stop_session"
        )
        worker._preserve_db_state = False

        with (
            patch.object(worker, "_finish_active_battle_if_any"),
            patch.object(worker, "_flush_all_pending_streaks"),
            patch.object(worker, "_flush_chat_buffer"),
        ):
            worker._cleanup_runtime_state()

        self.assertIsNone(get_active_stream_session(streamer_id))

    def test_manual_stop_closes_stale_session_without_diag_state(self):
        streamer = upsert_streamer("alert_stale_session")
        streamer_id = int(streamer["id"])
        start_stream_session(streamer_id, room_id="room-stale")
        worker = StreamerWorker(streamer_id, "alert_stale_session")
        worker._preserve_db_state = False
        self.assertIsNone(worker.diag.session_id)

        with (
            patch.object(worker, "_finish_active_battle_if_any"),
            patch.object(worker, "_flush_all_pending_streaks"),
            patch.object(worker, "_flush_chat_buffer"),
        ):
            worker._cleanup_runtime_state()

        self.assertIsNone(get_active_stream_session(streamer_id))


class TestPauseTracking(unittest.TestCase):
    def test_pause_preserves_db_state_and_session(self):
        manager = StreamerMonitorManager()
        worker = MagicMock()
        manager._workers["paused_streamer"] = worker

        result = manager.pause_tracking("@paused_streamer")

        worker.stop.assert_called_once_with(preserve_db_state=True)
        self.assertTrue(result["ok"])


class TestChatDeduplication(unittest.TestCase):
    def test_replayed_message_is_ignored(self):
        worker = StreamerWorker(streamer_id=3, username="@chat_dedupe")
        event = SimpleNamespace(
            user=SimpleNamespace(id="42", unique_id="viewer", nickname="Viewer"),
            comment="hello",
            common=SimpleNamespace(msg_id="msg-1"),
        )
        with patch("tiktok_service.get_cached_donor_tier", return_value=""):
            worker._process_comment_event(event)
            worker._process_comment_event(event)

        self.assertEqual(len(worker._chat_buffer), 1)


class TestSupervisorReconnect(unittest.IsolatedAsyncioTestCase):
    class FakeClient:
        def __init__(self):
            self.disconnect = AsyncMock()

        def on(self, event):
            return lambda fn: fn

    class FakeRateLimit(Exception):
        @property
        def retry_after(self):
            return 60

        @property
        def reset_time(self):
            return int(time.time()) + 60

    async def _run_until(self, worker, predicate, timeout=3.0):
        task = asyncio.create_task(worker._supervisor_loop())
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if predicate():
                    return
                await asyncio.sleep(0.01)
            self.fail("Supervisor-Zustand wurde nicht rechtzeitig erreicht")
        finally:
            worker._stop_event.set()
            await asyncio.wait_for(task, timeout=5.0)

    async def test_offline_enters_polling_state(self):
        from TikTokLive.client.errors import UserOfflineError

        worker = StreamerWorker(streamer_id=5, username="@offline_state")
        client = self.FakeClient()
        with (
            patch.object(worker, "_create_configured_client", return_value=client),
            patch.object(
                worker,
                "_start_client_with_age_bypass",
                new=AsyncMock(side_effect=UserOfflineError()),
            ),
            patch.object(worker, "_offline_poll_seconds", return_value=0.2),
            patch("tiktok_service.update_streamer_runtime_state"),
        ):
            await self._run_until(worker, lambda: worker.diag.state == "polling_offline")

        self.assertEqual(worker.diag.last_disconnect_reason, "offline")

    async def test_rate_limit_sets_backoff_and_counter(self):
        worker = StreamerWorker(streamer_id=6, username="@rate_limit_state")
        client = self.FakeClient()
        with (
            patch.object(worker, "_create_configured_client", return_value=client),
            patch.object(
                worker,
                "_start_client_with_age_bypass",
                new=AsyncMock(side_effect=self.FakeRateLimit()),
            ),
            patch("tiktok_service._set_sign_cooldown") as cooldown,
            patch("tiktok_service.update_streamer_runtime_state"),
        ):
            await self._run_until(worker, lambda: worker.diag.sign_rate_limited >= 1)

        self.assertEqual(worker.diag.state, "backoff")
        self.assertEqual(worker.diag.sign_rate_limited, 1)
        cooldown.assert_called_once()


class TestForceDisconnect(unittest.IsolatedAsyncioTestCase):
    async def test_cancels_websocket_task(self):
        worker = StreamerWorker(streamer_id=4, username="@force_disconnect")
        client = SimpleNamespace(disconnect=AsyncMock())
        ws_task = asyncio.create_task(asyncio.sleep(60))

        await worker._force_disconnect(client, ws_task)

        client.disconnect.assert_awaited_once()
        self.assertTrue(ws_task.cancelled())


if __name__ == "__main__":
    unittest.main()
