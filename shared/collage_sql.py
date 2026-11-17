"""
SQL-inspirierte, sichere Query-Syntax für ``/collage``.

Die Eingabe wird ausschließlich auf die bestehenden ``CollageRequest``-
Strukturen abgebildet. Es wird **kein** SQL an die Datenbank übergeben.

Beispiele::

    SELECT verlauf, streamer, tageszeit, geschenke
    FROM @saaliimo
    WHERE 7d AND eur
    GRID 2x2
    TITLE 'SAALIIMO · 7T'

    SELECT verlauf AS 'TOP 1' FROM @alice WHERE 24h AND eur
    UNION ALL
    SELECT verlauf AS 'TOP 2' FROM @bob WHERE 7d AND coins
    GRID 2x1

``WHERE`` akzeptiert sowohl ``period=7d AND metric=eur`` als auch die kurze
Form ``7d AND eur``. ``FROM`` versteht ``@name``, ``STREAMER name``,
``GROUP "Team Name"`` und ``ALL``.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from shared.chart_collage import (
    MAX_COLLAGE_TILES,
    STREAMER_CARDS_VIEW,
    CollageError,
    CollageRequest,
    CollageTileRequest,
    _parse_layout,
    infer_grid,
    is_card_view,
    normalize_scope_ref,
    validate_grid,
)
from shared.chart_views import is_view_alias, normalize_view
from shared.widget_chart import (
    is_metric_alias,
    is_period_alias,
    normalize_metric,
    normalize_period,
)

_SQL_STOP = frozenset(
    {
        "from",
        "von",
        "where",
        "wo",
        "union",
        "grid",
        "layout",
        "raster",
        "title",
        "titel",
        "refresh",
        "neu",
        "aktualisieren",
    }
)

_SQL_GLOBAL = frozenset(
    {
        "grid",
        "layout",
        "raster",
        "title",
        "titel",
        "refresh",
        "neu",
        "aktualisieren",
    }
)

_PERIOD_KEYS = frozenset({"period", "zeitraum", "zeit"})
_METRIC_KEYS = frozenset({"metric", "metrik", "waehrung", "währung"})
_FROM_KEYWORDS = frozenset({"from", "von"})
_WHERE_KEYWORDS = frozenset({"where", "wo"})
_AND_WORDS = frozenset({"and", "und", "&"})
_SQL_PREFIXES = frozenset({"sql", "query"})


class _SqlCollageParser:
    """Kleiner Zustandsautomat für die SELECT-DSL."""

    def __init__(self, tokens: Sequence[str], max_tiles: int) -> None:
        self.tokens = [str(token).strip() for token in tokens if str(token).strip()]
        self.pos = 0
        self.limit = max_tiles
        self.scope = ""
        self.period = "24h"
        self.metric = "eur"
        self.tiles: List[CollageTileRequest] = []
        self.rows = 0
        self.cols = 0
        self.title = ""
        self.force_refresh = False

    def peek(self) -> str:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ""

    def consume(self, label: str = "Wert") -> str:
        token = self.peek()
        if not token:
            raise CollageError(f"SQL-Modus: {label} fehlt.")
        self.pos += 1
        return token

    def match(self, *words: str) -> bool:
        if self.peek().lower() in words:
            self.pos += 1
            return True
        return False

    @staticmethod
    def _is_stop(token: str) -> bool:
        return token.lower() in _SQL_STOP

    @staticmethod
    def _is_global_stop(token: str) -> bool:
        lowered = token.lower()
        return lowered in _SQL_GLOBAL or lowered == "union"

    def parse(self) -> CollageRequest:
        while True:
            self._parse_block()
            if self.match("union"):
                self.match("all")
                if self.peek().lower() != "select":
                    raise CollageError("SQL-Modus: Nach UNION ALL muss SELECT folgen.")
                continue
            break

        self._parse_global_tail()

        if self.pos < len(self.tokens):
            raise CollageError(f"SQL-Modus: Unerwartetes Token '{self.peek()}'.")
        if not self.tiles:
            raise CollageError("SQL-Modus: SELECT enthält keine Ansicht.")
        if len(self.tiles) > self.limit:
            raise CollageError(f"Maximal {self.limit} Kacheln pro Kollage.")
        if not self.rows or not self.cols:
            self.cols, self.rows = infer_grid(len(self.tiles))
        validate_grid(self.rows, self.cols, len(self.tiles))

        return CollageRequest(
            tiles=tuple(self.tiles),
            period=self.period,
            metric=self.metric,
            scope_ref=self.scope,
            rows=self.rows,
            cols=self.cols,
            title=self.title,
            force_refresh=self.force_refresh,
        )

    def _parse_block(self) -> None:
        if not self.match("select"):
            raise CollageError("SQL-Modus beginnt mit SELECT …")

        items: List[dict[str, str]] = []
        while self.peek() and not self._is_stop(self.peek()):
            token = self.consume()
            if token.lower() == "as":
                if not items:
                    raise CollageError("SQL-Modus: AS benötigt eine Ansicht davor.")
                items[-1]["label"] = self.consume("AS-Label").rstrip(",").strip()[:40]
                continue
            for part in token.split(","):
                part = part.strip()
                if not part:
                    continue
                if is_card_view(part):
                    items.append({"view": STREAMER_CARDS_VIEW, "label": ""})
                    continue
                if not is_view_alias(part):
                    raise CollageError(f"SQL-Modus: Unbekannte Ansicht '{part}'.")
                items.append({"view": normalize_view(part), "label": ""})

        if not items:
            raise CollageError("SQL-Modus: SELECT enthält keine Ansicht.")

        scope = self.scope
        period = self.period
        metric = self.metric

        if self.match(*_FROM_KEYWORDS):
            scope = self._parse_scope()
            if self.peek() and not self._is_stop(self.peek()):
                raise CollageError(
                    f"SQL-Modus: Unerwartetes Token '{self.peek()}' nach FROM."
                )

        if self.match(*_WHERE_KEYWORDS):
            period, metric = self._parse_where(period, metric)

        self.scope = scope
        self.period = period
        self.metric = metric

        for item in items:
            if len(self.tiles) >= self.limit:
                raise CollageError(f"Maximal {self.limit} Kacheln pro Kollage.")
            self.tiles.append(
                CollageTileRequest(
                    view=item["view"],
                    period=period,
                    metric=metric,
                    scope_ref=scope,
                    label=item["label"],
                )
            )

    def _parse_scope(self) -> str:
        token = self.consume("Scope")
        lowered = token.lower()

        if lowered in ("streamer", "kanal"):
            name = self.consume("Streamer-Name")
            return normalize_scope_ref("@" + name.lstrip("@"))

        if lowered in ("group", "gruppe"):
            parts = [self.consume("Gruppen-Name")]
            while self.peek() and not self._is_stop(self.peek()):
                parts.append(self.consume())
            return normalize_scope_ref("gruppe:" + " ".join(parts))

        return normalize_scope_ref(token)

    def _parse_where(self, period: str, metric: str) -> Tuple[str, str]:
        while self.peek() and not self._is_stop(self.peek()):
            token = self.consume()
            for part in token.split(","):
                part = part.strip()
                if not part:
                    continue
                lowered = part.lower()
                if lowered in _AND_WORDS:
                    continue

                if "=" in part:
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if not value:
                        value = self.consume("WHERE-Wert")
                    period, metric = self._apply_where(key, value, period, metric)
                    continue

                if lowered in _PERIOD_KEYS or lowered in _METRIC_KEYS:
                    if self.peek() == "=":
                        self.consume()
                    value = self.consume("WHERE-Wert")
                    period, metric = self._apply_where(
                        lowered, value, period, metric
                    )
                    continue

                if is_period_alias(lowered):
                    period = normalize_period(lowered)
                elif is_metric_alias(lowered):
                    metric = normalize_metric(lowered)
                else:
                    raise CollageError(
                        f"SQL-Modus: Unbekannte WHERE-Bedingung '{part}'."
                    )
        return period, metric

    @staticmethod
    def _apply_where(
        key: str,
        value: str,
        period: str,
        metric: str,
    ) -> Tuple[str, str]:
        key = key.strip().lower()
        if key in _PERIOD_KEYS:
            if not is_period_alias(value):
                raise CollageError(f"SQL-Modus: Unbekannter Zeitraum '{value}'.")
            return normalize_period(value), metric
        if key in _METRIC_KEYS:
            if not is_metric_alias(value):
                raise CollageError(f"SQL-Modus: Unbekannte Metrik '{value}'.")
            return period, normalize_metric(value)
        raise CollageError(f"SQL-Modus: Unbekannte WHERE-Option '{key}'.")

    def _parse_global_tail(self) -> None:
        while self.peek():
            token = self.consume()
            lowered = token.lower()

            if lowered in ("grid", "layout", "raster"):
                self.cols, self.rows = _parse_layout(self.consume("Raster"))
                continue

            if lowered in ("title", "titel"):
                parts: List[str] = []
                while self.peek() and not self._is_global_stop(self.peek()):
                    parts.append(self.consume())
                if not parts:
                    raise CollageError("SQL-Modus: TITLE benötigt einen Text.")
                self.title = " ".join(parts).rstrip(",").strip()[:80]
                continue

            if lowered in ("refresh", "neu", "aktualisieren"):
                self.force_refresh = True
                continue

            raise CollageError(f"SQL-Modus: Unbekannte Klausel '{token}'.")


def parse_collage_sql(
    args: Optional[Sequence[str]],
    max_tiles: int = MAX_COLLAGE_TILES,
) -> CollageRequest:
    """
    Parst die SQL-inspirierte ``/collage``-Syntax.

    ``/collage sql SELECT …`` wird ebenfalls akzeptiert; das Präfix ist rein
    zur Lesbarkeit erlaubt. Es wird kein SQL ausgeführt.
    """
    limit = min(MAX_COLLAGE_TILES, max(1, int(max_tiles or MAX_COLLAGE_TILES)))
    tokens = [str(token).strip() for token in args or () if str(token).strip()]

    if tokens and tokens[0].lower() in _SQL_PREFIXES:
        tokens = tokens[1:]

    if not tokens or tokens[0].lower() != "select":
        raise CollageError(
            "SQL-Modus: Beginne mit SELECT, z. B. "
            "SELECT verlauf, streamer FROM @name WHERE 7d AND eur GRID 2x2."
        )

    return _SqlCollageParser(tokens, limit).parse()
