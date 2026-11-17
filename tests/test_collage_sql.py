"""
Tests für die SQL-inspirierte ``/collage``-Syntax.

Die Tests prüfen nur das Mapping auf ``CollageRequest``-Strukturen; es wird
keine Datenbankabfrage und kein Rendering ausgelöst.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import shlex
import unittest

from shared import collage_sql as cs
from shared.chart_collage import CollageError


def _parse(query: str, max_tiles: int = 9):
    return cs.parse_collage_sql(shlex.split(query), max_tiles=max_tiles)


class TestCollageSqlParser(unittest.TestCase):
    def test_natural_select_with_bare_where(self):
        request = _parse(
            "SELECT verlauf, streamer, tageszeit, geschenke "
            "FROM @saaliimo WHERE 7d AND eur GRID 2x2 "
            "TITLE 'SAALIIMO · 7T'"
        )
        self.assertEqual(
            [tile.view for tile in request.tiles],
            ["timeline", "streamers", "timeofday", "gifts"],
        )
        self.assertEqual(request.tiles[0].scope_ref, "@saaliimo")
        self.assertEqual(request.tiles[0].period, "7d")
        self.assertEqual(request.tiles[0].metric, "eur")
        self.assertEqual((request.cols, request.rows), (2, 2))
        self.assertEqual(request.title, "SAALIIMO · 7T")

    def test_streamer_keyword_and_key_value_where(self):
        request = _parse(
            "SELECT verlauf streamer FROM STREAMER @alice "
            "WHERE period = 7d AND metric = coins LAYOUT 2x1"
        )
        self.assertEqual([tile.view for tile in request.tiles], ["timeline", "streamers"])
        self.assertEqual(request.tiles[0].scope_ref, "@alice")
        self.assertEqual(request.tiles[1].period, "7d")
        self.assertEqual(request.tiles[1].metric, "coins")
        self.assertEqual((request.cols, request.rows), (2, 1))

    def test_group_with_quoted_name_and_spaces(self):
        request = _parse(
            'SELECT streamer, geschenke FROM GROUP "Team Alpha" '
            "WHERE 30d AND coins GRID 3x1"
        )
        self.assertEqual(request.tiles[0].scope_ref, "gruppe:Team Alpha")
        self.assertEqual((request.cols, request.rows), (3, 1))

    def test_group_with_classic_plus_token(self):
        request = _parse("SELECT streamer FROM gruppe:Team+Alpha WHERE 7d")
        self.assertEqual(request.tiles[0].scope_ref, "gruppe:Team Alpha")

    def test_group_with_unquoted_multiword_name(self):
        request = _parse("SELECT streamer FROM GROUP Team Alpha WHERE 7d")
        self.assertEqual(request.tiles[0].scope_ref, "gruppe:Team Alpha")

    def test_union_all_keeps_per_tile_options_and_labels(self):
        request = _parse(
            "SELECT verlauf AS 'TOP 1' FROM @alpha WHERE 24h AND eur "
            "UNION ALL SELECT verlauf AS 'TOP 2' FROM @beta "
            "WHERE 7d AND coins GRID 2x1"
        )
        self.assertEqual(len(request.tiles), 2)
        first, second = request.tiles
        self.assertEqual(first.scope_ref, "@alpha")
        self.assertEqual(first.period, "24h")
        self.assertEqual(first.metric, "eur")
        self.assertEqual(first.label, "TOP 1")
        self.assertEqual(second.scope_ref, "@beta")
        self.assertEqual(second.period, "7d")
        self.assertEqual(second.metric, "coins")
        self.assertEqual(second.label, "TOP 2")
        self.assertEqual((request.cols, request.rows), (2, 1))

    def test_union_without_all_and_with_inheritance(self):
        request = _parse(
            "SELECT verlauf FROM @alpha WHERE 7d AND eur "
            "UNION SELECT streamer"
        )
        self.assertEqual(request.tiles[1].scope_ref, "@alpha")
        self.assertEqual(request.tiles[1].period, "7d")
        self.assertEqual(request.tiles[1].metric, "eur")

    def test_german_aliases_and_refresh(self):
        request = _parse(
            "SELECT verlauf FROM @alpha WO 7d UND eur "
            "RASTER 2x2 NEU TITEL 'Q4'"
        )
        self.assertEqual((request.cols, request.rows), (2, 2))
        self.assertTrue(request.force_refresh)
        self.assertEqual(request.title, "Q4")

    def test_sql_prefix_is_optional(self):
        request = _parse("sql SELECT verlauf FROM @alpha")
        self.assertEqual(len(request.tiles), 1)

    def test_from_all(self):
        request = _parse("SELECT verlauf FROM ALL WHERE 7d")
        self.assertEqual(request.tiles[0].scope_ref, "")

    def test_all_time_period(self):
        request = _parse("SELECT verlauf, streamer FROM ALL WHERE all AND eur")
        self.assertEqual(request.tiles[0].period, "all")
        self.assertEqual(request.tiles[1].period, "all")

    def test_where_comma_and_unquoted_title(self):
        request = _parse(
            "SELECT verlauf FROM @alpha WHERE period=7d,metric=coins "
            "TITLE Q4 Report"
        )
        self.assertEqual(request.tiles[0].period, "7d")
        self.assertEqual(request.tiles[0].metric, "coins")
        self.assertEqual(request.title, "Q4 Report")

    def test_invalid_queries_raise(self):
        invalid = [
            "SELECT unbekannt FROM @alpha",
            "SELECT verlauf FROM @alpha WHERE farbe=blau",
            "SELECT verlauf FROM @alpha UNION ALL verlauf",
            "SELECT verlauf FROM @alpha GRID 1x1 WHERE 7d",
            "SELECT verlauf FROM @alpha UNION ALL SELECT streamer FROM @b "
            "UNION ALL SELECT geschenke FROM @c UNION ALL SELECT spender FROM @d "
            "UNION ALL SELECT tageszeit FROM @e UNION ALL SELECT verlauf FROM @f "
            "UNION ALL SELECT streamer FROM @g UNION ALL SELECT geschenke FROM @h "
            "UNION ALL SELECT spender FROM @i UNION ALL SELECT tageszeit FROM @j",
            "SELECT FROM @alpha",
            "SELECT verlauf FROM GROUP",
        ]
        for query in invalid:
            with self.subTest(query=query), self.assertRaises(CollageError):
                _parse(query, max_tiles=9)

    def test_requires_select(self):
        with self.assertRaises(CollageError):
            _parse("FROM @alpha")


if __name__ == "__main__":
    unittest.main()
