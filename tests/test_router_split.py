"""
Guard für den Router-Split: Pfade bleiben registriert, nichts wird doppelt.

Die Endpunkte aus ``routers/*`` werden in ``app.py`` per ``include_router``
eingebunden. Ein vergessener ``include_router`` würde hier auffallen, bevor es
Tests gibt, die den jeweiligen Pfad zufällig abdecken.

Hinweis: FastAPI 0.162 legt eingebundene Router als ``_IncludedRouter``-Marker
ab und löst sie erst beim ersten Request auf. Deshalb werden die effektiven
Routen hier explizit über ``effective_route_contexts()`` eingesammelt.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

from app import app

EXTRACTED_ROUTES = {
    ("GET", "/api/revenue/profiles"),
    ("POST", "/api/revenue/profiles/{profile_id}"),
    ("POST", "/api/revenue/assign"),
    ("GET", "/api/export/gifts.csv"),
    ("GET", "/api/export/battles.csv"),
    ("GET", "/api/settings"),
    ("POST", "/api/settings"),
    ("POST", "/api/demo/seed"),
    ("POST", "/api/demo/clear"),
    ("GET", "/api/telegram/users"),
    ("GET", "/api/v1/telegram/users"),
    ("POST", "/api/telegram/users"),
    ("POST", "/api/v1/telegram/users"),
    ("GET", "/api/telegram/users/{record_id}/permissions"),
    ("PUT", "/api/v1/telegram/users/{record_id}/permissions"),
    ("DELETE", "/api/telegram/users/{record_id}"),
    ("DELETE", "/api/v1/telegram/users/{record_id}"),
}


def _iter_route_pairs():
    """Liefert (Methode, Pfad) für direkte Routen und eingebundene Router."""
    for route in app.router.routes:
        resolver = getattr(route, "effective_route_contexts", None)
        if resolver is not None:
            for context in resolver():
                path = getattr(context, "path", None)
                for method in getattr(context, "methods", None) or set():
                    yield method, path
            continue

        path = getattr(route, "path", None)
        for method in getattr(route, "methods", None) or set():
            yield method, path


class TestRouterSplit(unittest.TestCase):
    def setUp(self):
        self.pairs = {
            (method, path)
            for method, path in _iter_route_pairs()
            if path is not None and method not in {"HEAD", "OPTIONS"}
        }

    def test_extracted_routes_are_registered(self):
        missing = EXTRACTED_ROUTES - self.pairs
        self.assertEqual(missing, set(), f"Router nicht eingebunden: {missing}")

    def test_no_duplicate_routes(self):
        seen: set[tuple[str, str]] = set()
        duplicates: list[tuple[str, str]] = []
        for pair in _iter_route_pairs():
            method, path = pair
            if path is None or method in {"HEAD", "OPTIONS"}:
                continue
            if pair in seen:
                duplicates.append(pair)
            seen.add(pair)
        self.assertEqual(duplicates, [], f"Doppelt registrierte Routen: {duplicates}")


if __name__ == "__main__":
    unittest.main()
