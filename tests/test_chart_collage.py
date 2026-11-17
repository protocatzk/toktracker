"""
Tests für den komplexen ``/collage``-Parameterparser und den PNG-Renderer.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from shared import chart_collage as cc
from shared import chart_image as ci
from telegram_service import TelegramBotService


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (ci.IMAGE_WIDTH, ci.IMAGE_HEIGHT), (0, 0, 0)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def _tile(view: str = "timeline", label: str = "") -> cc.CollageTile:
    return cc.CollageTile(view=view, label=label)


class TestCollageParser(unittest.TestCase):
    def test_defaults_produce_four_standard_views(self):
        request = cc.parse_collage_args([])
        self.assertEqual(len(request.tiles), 4)
        self.assertEqual((request.cols, request.rows), (2, 2))
        self.assertEqual(
            [tile.view for tile in request.tiles],
            ["timeline", "streamers", "timeofday", "gifts"],
        )
        self.assertFalse(request.force_refresh)

    def test_positional_options_and_per_tile_overrides(self):
        request = cc.parse_collage_args(
            [
                "@alice",
                "7d",
                "coins",
                "2x1",
                "verlauf",
                "streamer|@bob|30d|eur|label=VIP",
            ]
        )
        self.assertEqual((request.cols, request.rows), (2, 1))
        self.assertEqual(request.period, "7d")
        self.assertEqual(request.metric, "coins")
        first, second = request.tiles
        self.assertEqual(first.view, "timeline")
        self.assertEqual(first.scope_ref, "@alice")
        self.assertEqual(first.period, "7d")
        self.assertEqual(first.metric, "coins")
        self.assertEqual(second.view, "streamers")
        self.assertEqual(second.scope_ref, "@bob")
        self.assertEqual(second.period, "30d")
        self.assertEqual(second.metric, "eur")
        self.assertEqual(second.label, "VIP")

    def test_key_value_options_and_group_plus_notation(self):
        request = cc.parse_collage_args(
            [
                "scope=gruppe:Team+Alpha",
                "views=verlauf,geschenke",
                "layout=2x2",
                "title=Q4 Report",
                "refresh=1",
            ]
        )
        self.assertEqual(request.tiles[0].scope_ref, "gruppe:Team Alpha")
        self.assertEqual(request.tiles[1].view, "gifts")
        self.assertEqual((request.cols, request.rows), (2, 2))
        self.assertEqual(request.title, "Q4 Report")
        self.assertTrue(request.force_refresh)

    def test_explicit_all_scope_overrides_global_scope(self):
        request = cc.parse_collage_args(
            ["scope=@alice", "views=verlauf,verlauf|all|24h|eur"]
        )
        self.assertEqual(request.tiles[0].scope_ref, "@alice")
        self.assertEqual(request.tiles[1].scope_ref, "")

    def test_max_tiles_is_enforced(self):
        with self.assertRaises(cc.CollageError):
            cc.parse_collage_args(
                ["views=verlauf,streamer,tageszeit"],
                max_tiles=2,
            )

    def test_layout_must_fit_all_tiles(self):
        with self.assertRaises(cc.CollageError):
            cc.parse_collage_args(["layout=1x1", "views=verlauf,streamer"])

    def test_unknown_option_and_missing_view_raise(self):
        with self.assertRaises(cc.CollageError):
            cc.parse_collage_args(["farbe=blau"])
        with self.assertRaises(cc.CollageError):
            cc.parse_collage_args(["tile=@alice"])

    def test_grid_inference(self):
        self.assertEqual(cc.infer_grid(1), (1, 1))
        self.assertEqual(cc.infer_grid(2), (2, 1))
        self.assertEqual(cc.infer_grid(3), (2, 2))
        self.assertEqual(cc.infer_grid(5), (3, 2))
        self.assertEqual(cc.infer_grid(9), (3, 3))


class TestCollageRendering(unittest.TestCase):
    def setUp(self) -> None:
        cc.clear_chart_collage_cache()

    def test_renders_grid_png_and_caption(self):
        png = _png()
        tiles = [_tile(view) for view in ("timeline", "streamers", "gifts", "gifters")]
        with patch.object(
            cc, "build_chart_image", return_value=SimpleNamespace(png=png)
        ) as builder:
            collage = cc.build_chart_collage(tiles, rows=2, cols=2, title="TEST")
        self.assertEqual(builder.call_count, 4)
        self.assertTrue(collage.png.startswith(b"\x89PNG"))
        self.assertEqual((collage.cols, collage.rows), (2, 2))
        self.assertIn("BILDERKOLLAGE", collage.caption)
        self.assertIn("2×2", collage.caption)
        self.assertIn("TEST", collage.caption)
        self.assertEqual(len(collage.digest), 64)

    def test_collage_is_cached(self):
        png = _png()
        tiles = [_tile("timeline"), _tile("gifts")]
        with patch.object(
            cc, "build_chart_image", return_value=SimpleNamespace(png=png)
        ) as builder:
            first = cc.build_chart_collage(tiles)
            second = cc.build_chart_collage(tiles)
        self.assertEqual(builder.call_count, 2)
        self.assertIs(first, second)

    def test_too_many_tiles_raise(self):
        with self.assertRaises(cc.CollageError):
            cc.build_chart_collage([_tile() for _ in range(10)])

    def test_invalid_grid_raises(self):
        with self.assertRaises(cc.CollageError):
            cc.build_chart_collage([_tile()], rows=4, cols=4)

    def test_tile_label_is_embedded(self):
        png = _png()
        with patch.object(cc, "build_chart_image", return_value=SimpleNamespace(png=png)):
            plain = cc.build_chart_collage([_tile("timeline")], rows=1, cols=1)
            labelled = cc.build_chart_collage(
                [_tile("timeline", label="VIP")], rows=1, cols=1
            )
        self.assertNotEqual(plain.digest, labelled.digest)


class TestCollageCommand(unittest.IsolatedAsyncioTestCase):
    def _service(self):
        service = TelegramBotService()
        service._authorize = AsyncMock(return_value={"permissions": set()})
        service._resolve_collage_tiles = AsyncMock(return_value=[_tile()])
        service._send_chart_image = AsyncMock()
        message = SimpleNamespace(
            text="/collage @alice 7d eur 2x2",
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=-100),
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(
            args=["@alice", "7d", "eur", "2x2"],
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )
        return service, update, context

    async def test_command_renders_and_sends_collage(self):
        service, update, context = self._service()
        collage = SimpleNamespace(png=b"png", caption="caption", digest="digest")
        with patch(
            "telegram_service.build_chart_collage", return_value=collage
        ) as builder:
            await service._cmd_collage(update, context)
        self.assertEqual(builder.call_count, 1)
        service._send_chart_image.assert_awaited_once()
        update.effective_message.reply_text.assert_not_awaited()

    async def test_command_without_args_shows_help(self):
        service, update, context = self._service()
        update.effective_message.text = "/collage"
        context.args = []
        with (
            patch(
                "telegram_service.list_streamers_for_picker",
                return_value=[{"username": "alpha", "is_live": 1}],
            ),
            patch(
                "telegram_service.list_streamer_groups",
                return_value=[{"name": "Team Alpha", "member_count": 2}],
            ),
        ):
            await service._cmd_collage(update, context)
        update.effective_message.reply_text.assert_awaited_once()
        text = update.effective_message.reply_text.await_args.args[0]
        self.assertIn("/collage @alpha 7d eur 2x2", text)
        self.assertIn("scope=gruppe:Team+Alpha", text)
        service._send_chart_image.assert_not_awaited()

    def test_help_examples_use_real_streamer_and_group_data(self):
        service = TelegramBotService()
        text = service._collage_help_text(
            [{"username": "alpha"}, {"username": "beta"}],
            [
                {"name": "Team Alpha", "member_count": 2},
                {"name": "Leere Gruppe", "member_count": 0},
            ],
        )
        self.assertIn("/collage @alpha 7d eur 2x2", text)
        self.assertIn("scope=gruppe:Team+Alpha", text)
        self.assertIn("streamer|@beta|7d|coins", text)
        self.assertNotIn("@alice", text)
        self.assertNotIn("gruppe:Leere+Gruppe", text)

    def test_help_examples_fall_back_without_data(self):
        service = TelegramBotService()
        text = service._collage_help_text([], [])
        self.assertIn("Noch keine Streamer oder Gruppen", text)


if __name__ == "__main__":
    unittest.main()
