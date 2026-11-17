"""
Tests für die Streamer-Grid-Kollage (alle Streamer als Karten in einem PNG).
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from shared import streamer_grid as sg


def _rows(count: int = 7) -> list[dict]:
    return [
        {
            "username": f"user{i:02d}",
            "display_name": f"User {i}",
            "is_live": i == 0,
            "current_viewers": 123 if i == 0 else 0,
            "total_coins": 10000 - i * 100,
            "eur_net": 100.0 - i,
            "gift_events_count": 50 - i,
            "pct_of_total": 10.0 - i / 10,
        }
        for i in range(count)
    ]


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), (0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestStreamerGrid(unittest.TestCase):
    def setUp(self) -> None:
        sg.clear_streamer_grid_cache()

    def test_renders_valid_grid_and_sorted_rows(self):
        with patch.object(sg, "load_streamer_grid_rows", return_value=_rows(7)):
            image = sg.build_streamer_grid("all", "eur", "TEST")
        self.assertTrue(image.png.startswith(b"\x89PNG"))
        self.assertEqual(image.count, 7)
        self.assertEqual(image.total_count, 7)
        self.assertEqual(image.period, "all")
        self.assertEqual(image.metric, "eur")
        self.assertEqual((image.width, image.height), (1436, 548))
        self.assertIn("STREAMER GRID", image.caption)
        self.assertIn("7 STREAMER", image.caption)
        self.assertIn("TEST", image.caption)

    def test_cache_renders_only_once(self):
        rows = _rows(7)
        with (
            patch.object(sg, "load_streamer_grid_rows", return_value=rows),
            patch.object(sg, "_render_grid", return_value=_png()) as renderer,
        ):
            first = sg.build_streamer_grid("all", "eur", "CACHE")
            second = sg.build_streamer_grid("all", "eur", "CACHE")
        self.assertEqual(renderer.call_count, 1)
        self.assertIs(first, second)

    def test_cards_are_capped(self):
        rows = _rows(sg.MAX_STREAMER_CARDS + 5)
        with (
            patch.object(sg, "load_streamer_grid_rows", return_value=rows),
            patch.object(sg, "_render_grid", return_value=_png()),
        ):
            image = sg.build_streamer_grid("all", "eur")
        self.assertEqual(image.count, sg.MAX_STREAMER_CARDS)
        self.assertEqual(image.total_count, sg.MAX_STREAMER_CARDS + 5)
        self.assertIn(f"TOP {sg.MAX_STREAMER_CARDS} VON", image.caption)

    def test_empty_data_raises(self):
        from shared.chart_image import ChartImageError

        with (
            patch.object(sg, "load_streamer_grid_rows", return_value=[]),
            self.assertRaises(ChartImageError),
        ):
            sg.build_streamer_grid("all", "eur")


if __name__ == "__main__":
    unittest.main()
