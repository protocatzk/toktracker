"""
Tests für die Telegram-HTML-Widget-Charts (Bot API 10.4).

Die Widgets haben harte Telegram-Grenzen (32 KB HTML, 4 KB komprimiert).
Das Chart wird serverseitig als SVG gerendert; diese Tests verhindern, dass
Template- oder Datenänderungen die Grenzen sprengen oder wieder eine
JS-abhängige Darstellung einführen.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import re
import unittest
from unittest.mock import patch

from shared import widget_chart as wc


def _fake_timeline(points: int = 24) -> list[dict]:
    return [
        {
            "bucket": f"2026-11-12T{i:02d}" if points <= 24 else f"2026-11-{i + 1:02d}",
            "label": f"{i:02d}:00" if points <= 24 else f"{i + 1:02d}.11.",
            "eur_net": float(i * 3.25),
            "coins": i * 40,
            "events_count": i,
        }
        for i in range(points)
    ]


class TestWidgetLimits(unittest.TestCase):
    def test_all_variants_fit_telegram_limits(self):
        for period in wc.CHART_PERIODS:
            for metric in wc.CHART_METRICS:
                with self.subTest(period=period, metric=metric):
                    chart = _build(points=30, period=period, metric=metric)
                    raw, compressed = wc.widget_sizes(chart.html)
                    self.assertLessEqual(raw, wc.WIDGET_MAX_HTML_BYTES)
                    self.assertLessEqual(compressed, wc.WIDGET_MAX_COMPRESSED_BYTES)
                    self.assertNotIn("\x00", chart.html)

    def test_widget_is_offline_and_library_free(self):
        source = _build().html.lower()
        for forbidden in (
            "<script src",
            "<link",
            "fetch(",
            "xmlhttprequest",
            "websocket",
            "importscripts",
            "url(http",
            "createelementns",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_widget_uses_telegram_theme(self):
        source = _build().html
        self.assertIn("--tg-theme-text-color", source)
        self.assertIn("--tg-theme-button-color", source)
        self.assertNotIn("background:", source)

    def test_html_size_limit_is_enforced(self):
        with self.assertRaises(wc.WidgetLimitError):
            wc.ensure_widget_limits("x" * (wc.WIDGET_MAX_HTML_BYTES + 1))


class TestServerRenderedSvg(unittest.TestCase):
    def test_chart_is_rendered_in_html_not_in_javascript(self):
        source = _build(points=24).html
        self.assertIn("<svg", source)
        self.assertIn('class="ln"', source)
        self.assertIn('class="ar"', source)
        self.assertIn('class="pt"', source)
        self.assertNotIn("TelegramWidget", source)

    def test_values_and_labels_are_embedded(self):
        source = _build(points=24).html
        vals = re.search(r'data-vals="([^"]*)"', source)
        labels = re.search(r'data-labels="([^"]*)"', source)
        self.assertIsNotNone(vals)
        self.assertIsNotNone(labels)
        self.assertEqual(len(vals.group(1).split(",")), 24)
        self.assertEqual(len(labels.group(1).split("|")), 24)

    def test_labels_are_html_escaped(self):
        timeline = [{"label": "<b>12:00</b>", "eur_net": 1.0, "coins": 10}]
        with patch.object(wc, "_load_timeline", return_value=(timeline, {})):
            chart = wc.build_chart_widget("24h", "eur")
        self.assertIn("&lt;b&gt;", chart.html)
        self.assertNotIn("<b>12:00</b>", chart.html)

    def test_empty_timeline_is_handled(self):
        with patch.object(wc, "_load_timeline", return_value=([], {})):
            chart = wc.build_chart_widget("24h", "eur")
        self.assertEqual(chart.points, 0)
        self.assertNotIn("<svg", chart.html)
        self.assertIn("Keine Daten im Zeitraum.", chart.html)
        self.assertIn("0,00", chart.caption)


class TestFormatting(unittest.TestCase):
    def test_formatting_matches_german_bot_style(self):
        self.assertEqual(wc.format_eur(1234.5), "1.234,50")
        self.assertEqual(wc.format_eur(0), "0,00")
        self.assertEqual(wc.format_coins(1234567), "1.234.567")

    def test_tick_indices(self):
        self.assertEqual(wc._tick_indices(0), [])
        self.assertEqual(wc._tick_indices(1), [0])
        self.assertEqual(wc._tick_indices(24), [0, 8, 15, 23])


def _build(
    points: int = 24,
    period: str = "24h",
    metric: str = "eur",
    streamer_id: int | None = None,
    streamer_name: str = "",
):
    timeline = _fake_timeline(points)
    totals = {"eur_net": 1234.56, "total_coins": 987654}
    with patch.object(wc, "_load_timeline", return_value=(timeline, totals)):
        return wc.build_chart_widget(
            period, metric, streamer_id, streamer_name
        )


class TestChartTimeline(unittest.TestCase):
    def test_lightweight_query_structure_on_sqlite(self):
        from shared.database import get_chart_timeline

        data = get_chart_timeline("24h", force_refresh=True)
        self.assertEqual(data["period"], "24h")
        self.assertIn("timeline", data)
        self.assertIn("eur_net", data["totals"])
        self.assertIn("total_coins", data["totals"])
        for row in data["timeline"]:
            self.assertIn("label", row)
            self.assertIn("eur_net", row)
            self.assertIn("coins", row)

    def test_streamer_filter(self):
        from datetime import datetime

        from shared.database import (
            get_chart_timeline,
            record_gift_event,
            upsert_streamer,
        )

        alpha = upsert_streamer("chart_alpha")
        beta = upsert_streamer("chart_beta")
        now = datetime.now().isoformat(timespec="seconds")
        record_gift_event(alpha["id"], "fan", "Rose", 1, repeat_count=10, created_at=now)
        record_gift_event(beta["id"], "fan", "Rose", 1, repeat_count=5, created_at=now)

        alpha_data = get_chart_timeline("24h", streamer_id=alpha["id"], force_refresh=True)
        beta_data = get_chart_timeline("24h", streamer_id=beta["id"], force_refresh=True)
        self.assertEqual(alpha_data["streamer_id"], alpha["id"])
        self.assertGreaterEqual(alpha_data["totals"]["total_coins"], 10)
        self.assertGreaterEqual(beta_data["totals"]["total_coins"], 5)
        self.assertNotEqual(
            alpha_data["totals"]["total_coins"],
            beta_data["totals"]["total_coins"],
        )

        from shared.database import list_streamers_for_picker

        names = {row["username"] for row in list_streamers_for_picker()}
        self.assertIn("chart_alpha", names)
        self.assertIn("chart_beta", names)


class TestChartWidget(unittest.TestCase):
    def test_builds_valid_widget_for_all_periods(self):
        for period in wc.CHART_PERIODS:
            with self.subTest(period=period):
                chart = _build(points=30, period=period)
                self.assertEqual(chart.period, period)
                self.assertEqual(chart.points, 30)
                self.assertTrue(chart.caption)
                self.assertIn("TT-INTELLIGENCE", chart.caption)
                self.assertIn(chart.period_label, chart.caption)

    def test_caption_contains_totals_for_unsupported_clients(self):
        chart = _build()
        self.assertIn("€ 1.234,56", chart.caption)
        self.assertIn("Peak", chart.caption)

    def test_coins_metric(self):
        chart = _build(metric="coins")
        self.assertEqual(chart.metric, "coins")
        self.assertIn("COINS", chart.metric_label)
        self.assertAlmostEqual(chart.total, 987654.0)
        self.assertIn("Coins", chart.caption)

    def test_streamer_title_and_caption(self):
        chart = _build(streamer_id=42, streamer_name="alpha")
        self.assertEqual(chart.streamer_id, 42)
        self.assertEqual(chart.streamer_name, "alpha")
        self.assertIn("@alpha", chart.html)
        self.assertIn("@alpha", chart.caption)

    def test_force_refresh_is_forwarded(self):
        with patch.object(wc, "_load_timeline", return_value=([], {})) as loader:
            wc.build_chart_widget("7d", "eur", streamer_id=42, force_refresh=True)
        loader.assert_called_once_with("7d", 42, True)

    def test_period_and_metric_normalization(self):
        self.assertEqual(wc.normalize_period("Woche"), "7d")
        self.assertEqual(wc.normalize_period("monat"), "30d")
        self.assertEqual(wc.normalize_period("unbekannt"), "24h")
        self.assertEqual(wc.normalize_metric("€"), "eur")
        self.assertEqual(wc.normalize_metric("diamonds"), "coins")
        self.assertEqual(wc.normalize_metric("unbekannt"), "eur")


if __name__ == "__main__":
    unittest.main()
