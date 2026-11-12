"""
Tests für die Telegram-HTML-Widget-Charts (Bot API 10.4).

Die Widgets haben harte Telegram-Grenzen (32 KB HTML, 4 KB komprimiert,
1024 Bytes State). Diese Tests verhindern, dass eine Template- oder
Datenänderung die Grenzen unbemerkt sprengt.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from unittest.mock import patch

from shared import widget_chart as wc


def _fake_timeline(points: int = 24, metric_key: str = "eur_net") -> list[dict]:
    return [
        {
            "label": f"{i:02d}:00" if points <= 24 else f"{i + 1:02d}.11.",
            "eur_net": float(i * 3.25),
            "usd_net": float(i * 3.5),
            "coins": i * 40,
        }
        for i in range(points)
    ]


class TestWidgetLimits(unittest.TestCase):
    def test_static_html_is_within_telegram_limits(self):
        raw, compressed = wc.widget_sizes(wc.WIDGET_HTML)
        self.assertLessEqual(raw, wc.WIDGET_MAX_HTML_BYTES)
        self.assertLessEqual(compressed, wc.WIDGET_MAX_COMPRESSED_BYTES)
        self.assertNotIn("\x00", wc.WIDGET_HTML)

    def test_widget_is_offline_and_library_free(self):
        source = wc.WIDGET_HTML.lower()
        for forbidden in (
            "<script src",
            "<link",
            "fetch(",
            "xmlhttprequest",
            "websocket",
            "importscripts",
            "url(http",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_widget_uses_telegram_theme_and_state_only(self):
        source = wc.WIDGET_HTML.lower()
        self.assertIn("window.telegramwidget", source)
        self.assertIn("w.chatdata", source)
        self.assertIn("--tg-theme-text-color", wc.WIDGET_HTML)
        self.assertIn("--tg-theme-button-color", wc.WIDGET_HTML)
        self.assertNotIn("background:", source)

    def test_state_limit_is_enforced(self):
        with self.assertRaises(wc.WidgetLimitError):
            wc.ensure_widget_limits(wc.WIDGET_HTML, "x" * (wc.WIDGET_MAX_STATE_BYTES + 1))


class TestSeriesEncoding(unittest.TestCase):
    def test_roundtrip_keeps_peak_and_shape(self):
        values = [0.0, 1.5, 12.75, 0.0, 99.99, 42.0]
        encoded, peak = wc.encode_series(values)
        self.assertAlmostEqual(peak, 99.99)
        decoded = wc.decode_series(encoded)
        self.assertEqual(len(decoded), len(values))
        scale = peak / 60000.0
        reconstructed = [v * scale for v in decoded]
        for original, restored in zip(values, reconstructed):
            self.assertAlmostEqual(original, restored, delta=max(0.01, peak / 60000.0))

    def test_empty_series_is_safe(self):
        encoded, peak = wc.encode_series([])
        self.assertEqual(encoded, "")
        self.assertEqual(peak, 0.0)
        self.assertEqual(wc.decode_series(""), [])

    def test_formatting_matches_german_bot_style(self):
        self.assertEqual(wc.format_eur(1234.5), "1.234,50")
        self.assertEqual(wc.format_eur(0), "0,00")
        self.assertEqual(wc.format_coins(1234567), "1.234.567")


class TestChartWidget(unittest.TestCase):
    def _build(self, points: int = 24, period: str = "24h", metric: str = "eur"):
        timeline = _fake_timeline(points)
        totals = {"eur_net": 1234.56, "total_coins": 987654}
        with patch.object(wc, "_load_timeline", return_value=(timeline, totals)):
            return wc.build_chart_widget(period, metric)

    def test_builds_valid_widget_for_all_periods(self):
        for period in wc.CHART_PERIODS:
            with self.subTest(period=period):
                chart = self._build(points=30, period=period)
                self.assertLessEqual(len(chart.state.encode("utf-8")), wc.WIDGET_MAX_STATE_BYTES)
                self.assertEqual(chart.period, period)
                self.assertEqual(chart.points, 30)
                self.assertTrue(chart.caption)
                self.assertIn("EINNAHMEN-CHART", chart.caption)

    def test_state_contains_render_payload(self):
        import json

        chart = self._build()
        payload = json.loads(chart.state)
        self.assertEqual(payload["f"], "eur")
        self.assertEqual(payload["lb"][0], "00:00")
        self.assertEqual(len(wc.decode_series(payload["v"])), 24)
        self.assertAlmostEqual(payload["tot"], 1234.56)

    def test_coins_metric(self):
        chart = self._build(metric="coins")
        self.assertEqual(chart.metric, "coins")
        self.assertIn("COINS", chart.metric_label)
        self.assertAlmostEqual(chart.total, 987654.0)

    def test_empty_timeline_still_builds(self):
        with patch.object(wc, "_load_timeline", return_value=([], {})):
            chart = wc.build_chart_widget("24h", "eur")
        self.assertEqual(chart.points, 0)
        self.assertEqual(chart.peak, 0.0)
        self.assertLessEqual(len(chart.state.encode("utf-8")), wc.WIDGET_MAX_STATE_BYTES)

    def test_period_and_metric_normalization(self):
        self.assertEqual(wc.normalize_period("Woche"), "7d")
        self.assertEqual(wc.normalize_period("monat"), "30d")
        self.assertEqual(wc.normalize_period("unbekannt"), "24h")
        self.assertEqual(wc.normalize_metric("€"), "eur")
        self.assertEqual(wc.normalize_metric("diamonds"), "coins")
        self.assertEqual(wc.normalize_metric("unbekannt"), "eur")


if __name__ == "__main__":
    unittest.main()
