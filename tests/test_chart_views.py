"""
Tests für die zusätzlichen Bot-Chart-Ansichten (Admin-Panel-Parität).

Deckt Datenaufbereitung, Widget-Rendering, PNG-Rendering, Cache-Fingerprint,
Tastatur-Callbacks und die Argument-Erkennung von ``/chart`` ab.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from shared import chart_image as ci
from shared import chart_views as cv
from shared.widget_chart import widget_sizes
from telegram_service import TelegramBotService


def _analytics_data() -> dict:
    return {
        "totals": {"total_coins": 123456, "eur_net": 1234.56},
        "streamers_ranking": [
            {"username": f"user{i}", "total_coins": 10000 - i * 700, "eur_net": 100.0 - i}
            for i in range(12)
        ],
        "time_of_day": [
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "coins": (hour * 37) % 900,
                "eur_net": hour * 1.5,
                "events_count": hour,
            }
            for hour in range(24)
        ],
        "top_gifts": [
            {
                "gift_name": f"Gift{i}",
                "total_coins": 9000 - i * 900,
                "eur_net": 90.0 - i * 5,
                "total_quantity": 20 - i,
                "diamond_count": i + 1,
            }
            for i in range(9)
        ],
        "top_gifters": [
            {"sender_username": f"donor{i}", "total_coins": 8000 - i * 600, "eur_net": 80.0 - i}
            for i in range(12)
        ],
        "sessions": [
            {
                "id": i,
                "started_at": f"2026-11-{i:02d}T10:00:00",
                "session_coins": i * 100,
                "eur_net": i * 10.0,
                "peak_viewers": i * 5,
            }
            for i in range(1, 6)
        ],
    }


def _buttons(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


class TestViewNormalization(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(cv.normalize_view("tageszeit"), "timeofday")
        self.assertEqual(cv.normalize_view("GESCHENKE"), "gifts")
        self.assertEqual(cv.normalize_view("spender"), "gifters")
        self.assertEqual(cv.normalize_view("ranking"), "streamers")
        self.assertEqual(cv.normalize_view("unbekannt"), "timeline")
        self.assertTrue(cv.is_view_alias("tageszeit"))
        self.assertFalse(cv.is_view_alias("alpha"))


class TestLoadChartView(unittest.TestCase):
    def test_all_views_use_metric_and_build_series(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            for view in ("streamers", "timeofday", "gifts", "gifters"):
                with self.subTest(view=view):
                    series = cv.load_chart_view(view, "24h", "eur")
                    self.assertEqual(series.view, view)
                    self.assertTrue(series.labels)
                    self.assertEqual(len(series.labels), len(series.values))
                    self.assertGreater(series.total, 0)
                    self.assertIn("TT-INTELLIGENCE", series.caption)

    def test_coin_metric_reads_coin_columns(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            streamers = cv.load_chart_view("streamers", "24h", "coins")
            gifters = cv.load_chart_view("gifters", "24h", "coins")
        self.assertEqual(streamers.values[0], 10000.0)
        self.assertEqual(gifters.values[0], 8000.0)
        self.assertIn("Coins", streamers.caption)

        with patch.object(cv, "_load_analytics", return_value=data):
            sessions = cv.load_chart_view("streamers", "24h", "coins", 7, "alpha")
        self.assertEqual(sessions.values[0], 500.0)

    def test_streamer_selection_uses_sessions(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            series = cv.load_chart_view("streamers", "24h", "eur", 7, "alpha")
        self.assertEqual(series.title, "SESSION-PERFORMANCE")
        self.assertEqual(len(series.values), 5)
        self.assertEqual(series.values[0], 50.0)
        self.assertIn("@alpha", series.caption)

    def test_gift_peak_ignores_other_bucket(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            series = cv.load_chart_view("gifts", "24h", "eur")
        self.assertAlmostEqual(series.peak, 90.0)
        self.assertEqual(series.labels[-1], "Andere")

    def test_empty_data_returns_empty_series(self):
        empty = {"totals": {}, "streamers_ranking": [], "time_of_day": [], "top_gifts": [], "top_gifters": []}
        with patch.object(cv, "_load_analytics", return_value=empty):
            for view in ("streamers", "timeofday", "gifts", "gifters"):
                with self.subTest(view=view):
                    series = cv.load_chart_view(view, "24h", "eur")
                    self.assertEqual(series.values, ())
                    self.assertEqual(series.total, 0.0)


class TestChartViewWidget(unittest.TestCase):
    def test_all_views_fit_telegram_limits(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            for view in ("streamers", "timeofday", "gifts", "gifters"):
                with self.subTest(view=view):
                    widget = cv.build_chart_view_widget(view, "24h", "eur")
                    raw, compressed = widget_sizes(widget.html)
                    self.assertLessEqual(raw, 32768)
                    self.assertLessEqual(compressed, 4096)
                    self.assertEqual(widget.view, view)
                    self.assertGreater(widget.points, 0)
                    self.assertIn("TT-INTELLIGENCE", widget.caption)

    def test_hbar_widget_contains_rows(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            widget = cv.build_chart_view_widget("gifters", "7d", "coins")
        self.assertIn('class="hr"', widget.html)
        self.assertIn("@donor0", widget.html)
        self.assertIn("COINS", widget.html)

    def test_donut_widget_contains_legend(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            widget = cv.build_chart_view_widget("gifts", "24h", "eur")
        self.assertIn("<circle", widget.html)
        self.assertIn("%", widget.html)


class TestChartViewImage(unittest.TestCase):
    def setUp(self) -> None:
        ci.clear_chart_image_cache()

    def test_all_views_render_valid_png(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            for view in ("streamers", "timeofday", "gifts", "gifters"):
                with self.subTest(view=view):
                    image = ci.build_chart_image("24h", "eur", view=view)
                    self.assertTrue(image.png.startswith(b"\x89PNG"))
                    rendered = Image.open(BytesIO(image.png))
                    self.assertEqual(rendered.size, (ci.IMAGE_WIDTH, ci.IMAGE_HEIGHT))
                    self.assertEqual(image.view, view)
                    self.assertIn("TT-INTELLIGENCE", image.caption)

    def test_session_image_for_selected_streamer(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            image = ci.build_chart_image("24h", "eur", 7, "alpha", view="streamers")
        self.assertEqual(image.points, 5)
        self.assertIn("@alpha", image.caption)

    def test_view_cache_renders_once(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            with patch.object(ci, "_render_view_png", wraps=ci._render_view_png) as renderer:
                first = ci.build_chart_image("24h", "eur", view="gifts")
                second = ci.build_chart_image("24h", "eur", view="gifts")
        self.assertEqual(renderer.call_count, 1)
        self.assertEqual(first.digest, second.digest)
        self.assertIs(first, second)

    def test_views_are_cached_separately(self):
        data = _analytics_data()
        with patch.object(cv, "_load_analytics", return_value=data):
            gifts = ci.build_chart_image("24h", "eur", view="gifts")
            gifters = ci.build_chart_image("24h", "eur", view="gifters")
        self.assertNotEqual(gifts.digest, gifters.digest)


class TestChartViewKeyboard(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TelegramBotService()

    def test_view_buttons_preserve_selection_and_callbacks(self):
        markup = self.service._chart_keyboard("7d", "coins", 42, "gifts")
        buttons = _buttons(markup)
        self.assertTrue(any(b.callback_data == "chart_view:42:7d:coins:0:gifts" for b in buttons))
        self.assertTrue(any(b.callback_data == "chart_view:42:24h:coins:0:gifts" for b in buttons))
        self.assertTrue(any(b.callback_data == "chart_pick:7d:coins:gifts" for b in buttons))
        view_buttons = [b for b in buttons if b.callback_data.split(":")[-1] == "streamers"]
        self.assertTrue(view_buttons)
        self.assertIn("STREAMER", view_buttons[0].text)

    def test_timeline_keeps_legacy_callbacks(self):
        markup = self.service._chart_keyboard("24h", "eur")
        buttons = _buttons(markup)
        self.assertTrue(any(b.callback_data == "chart_view:0:24h:eur:0" for b in buttons))
        self.assertTrue(any(b.callback_data == "chart_pick:24h:eur" for b in buttons))

    def test_parse_chart_args_view_and_streamer(self):
        self.assertEqual(
            self.service._parse_chart_args(["7d", "coins", "spender", "@alpha"]),
            ("7d", "coins", "alpha", "gifters"),
        )
        self.assertEqual(
            self.service._parse_chart_args(["tageszeit", "@alpha"]),
            ("24h", "eur", "alpha", "timeofday"),
        )
        self.assertEqual(
            self.service._parse_chart_args(["geschenke"]),
            ("24h", "eur", None, "gifts"),
        )


if __name__ == "__main__":
    unittest.main()
