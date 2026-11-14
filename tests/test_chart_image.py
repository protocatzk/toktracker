"""
Tests für die serverseitig gerenderten Chart-Bilder (/chart als PNG).
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
from shared.widget_chart import ChartSeries


def _series(points: int = 24, metric: str = "eur", streamer: str = "") -> ChartSeries:
    values = tuple(float(i * 3.25) for i in range(points))
    labels = tuple(f"{i:02d}:00" for i in range(points))
    return ChartSeries(
        period="24h",
        metric=metric,
        values=values,
        labels=labels,
        total=1234.56 if metric == "eur" else 987654.0,
        peak=max(values, default=0.0),
        streamer_id=42 if streamer else None,
        streamer_name=streamer,
    )


class TestChartImageRendering(unittest.TestCase):
    def test_renders_rgba_png_with_scrim(self):
        png = ci._render_png(_series())
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(BytesIO(png))
        self.assertEqual(image.size, (ci.IMAGE_WIDTH, ci.IMAGE_HEIGHT))
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertGreater(image.getpixel((ci.IMAGE_WIDTH // 2, ci.IMAGE_HEIGHT // 2))[3], 100)
        self.assertLess(len(png), 250_000)

    def test_empty_series_still_renders(self):
        png = ci._render_png(
            ChartSeries(
                period="24h",
                metric="eur",
                values=(),
                labels=(),
                total=0.0,
                peak=0.0,
            )
        )
        image = Image.open(BytesIO(png))
        self.assertEqual(image.size, (ci.IMAGE_WIDTH, ci.IMAGE_HEIGHT))

    def test_coins_series_renders(self):
        png = ci._render_png(_series(metric="coins"))
        self.assertGreater(len(png), 1000)


class TestChartImageCache(unittest.TestCase):
    def test_same_data_is_rendered_only_once(self):
        ci.clear_chart_image_cache()
        series = _series()
        with patch.object(ci, "load_chart_series", return_value=series):
            with patch.object(ci, "_render_png", wraps=ci._render_png) as renderer:
                first = ci.build_chart_image("24h", "eur")
                second = ci.build_chart_image("24h", "eur")
        self.assertEqual(renderer.call_count, 1)
        self.assertEqual(first.digest, second.digest)
        self.assertIs(first, second)

    def test_streamer_caption(self):
        ci.clear_chart_image_cache()
        series = _series(streamer="alpha")
        with patch.object(ci, "load_chart_series", return_value=series):
            image = ci.build_chart_image("24h", "eur", 42, "alpha")
        self.assertIn("@alpha", image.caption)
        self.assertEqual(image.streamer_id, 42)

    def test_changed_data_produces_new_image(self):
        ci.clear_chart_image_cache()
        first_series = _series()
        second_series = _series()
        second_series = ChartSeries(
            period=second_series.period,
            metric=second_series.metric,
            values=second_series.values + (999.0,),
            labels=second_series.labels + ("99:00",),
            total=second_series.total + 999.0,
            peak=999.0,
        )
        with patch.object(ci, "load_chart_series", side_effect=[first_series, second_series]):
            first = ci.build_chart_image("24h", "eur")
            second = ci.build_chart_image("24h", "eur")
        self.assertNotEqual(first.digest, second.digest)


if __name__ == "__main__":
    unittest.main()
