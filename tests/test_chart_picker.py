"""
Tests für den paginierten Streamer-Picker der Telegram-Charts.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from unittest.mock import patch

from telegram_service import TelegramBotService


def _streamers(count: int = 10) -> list[dict]:
    return [
        {
            "id": i + 1,
            "username": f"streamer_{i + 1}",
            "display_name": f"Streamer {i + 1}",
            "is_live": i % 2 == 0,
            "is_tracking": True,
        }
        for i in range(count)
    ]


def _buttons(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


class TestChartPicker(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TelegramBotService()

    def test_first_page_contains_eight_streamers_and_next(self):
        with patch("telegram_service.list_streamers_for_picker", return_value=_streamers(10)):
            text, markup = self.service._format_chart_picker("24h", "eur", 0, 999)

        self.assertIn("1/2", text)
        self.assertIn("10", text)
        buttons = _buttons(markup)
        streamer_buttons = [b for b in buttons if b.callback_data.startswith("chart_stream:")]
        self.assertEqual(len(streamer_buttons), 8)
        self.assertEqual(streamer_buttons[0].callback_data, "chart_stream:1:24h:eur:999")
        self.assertIn("🟢", streamer_buttons[0].text)
        next_buttons = [b for b in buttons if b.callback_data == "chart_page:1:24h:eur:999"]
        self.assertEqual(len(next_buttons), 1)
        self.assertEqual(next_buttons[0].text, "▶️")
        self.assertTrue(any(b.callback_data == "chart_cancel:0" for b in buttons))

    def test_second_page_has_previous_and_last_streamers(self):
        with patch("telegram_service.list_streamers_for_picker", return_value=_streamers(10)):
            text, markup = self.service._format_chart_picker("7d", "coins", 1, 42)

        self.assertIn("2/2", text)
        buttons = _buttons(markup)
        streamer_buttons = [b for b in buttons if b.callback_data.startswith("chart_stream:")]
        self.assertEqual(len(streamer_buttons), 2)
        prev_buttons = [b for b in buttons if b.callback_data == "chart_page:0:7d:coins:42"]
        self.assertEqual(len(prev_buttons), 1)
        self.assertEqual(prev_buttons[0].text, "◀️")

    def test_empty_streamer_list(self):
        with patch("telegram_service.list_streamers_for_picker", return_value=[]):
            text, markup = self.service._format_chart_picker("24h", "eur", 0, 0)

        self.assertIn("0", text)
        buttons = _buttons(markup)
        self.assertFalse(any(b.callback_data.startswith("chart_stream:") for b in buttons))
        self.assertTrue(any(b.callback_data == "chart_cancel:0" for b in buttons))

    def test_chart_keyboard_offers_picker_and_global_reset(self):
        global_markup = self.service._chart_keyboard("24h", "eur")
        global_picker = [
            b for b in _buttons(global_markup) if b.callback_data == "chart_pick:24h:eur"
        ]
        self.assertEqual(len(global_picker), 1)
        self.assertFalse(
            any(b.text == "🌐 ALLE" for b in _buttons(global_markup))
        )

        streamer_markup = self.service._chart_keyboard("7d", "coins", 42)
        streamer_buttons = _buttons(streamer_markup)
        self.assertTrue(any(b.text == "🌐 ALLE" for b in streamer_buttons))
        self.assertTrue(
            any(b.callback_data == "chart_view:0:7d:coins:0" for b in streamer_buttons)
        )
        self.assertTrue(
            any(b.callback_data == "chart_pick:7d:coins" for b in streamer_buttons)
        )


if __name__ == "__main__":
    unittest.main()
