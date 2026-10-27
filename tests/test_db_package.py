"""
Struktur-Guard für das Datenbank-Paket.

Sichert ab, dass der Split von `shared/database.py` nach `shared/db/*` die
historische, flache API nicht beschädigt und dass `database.py` Fassade bleibt.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import ast
import glob
import importlib
import os
import unittest

import shared.database as facade
import shared.db as db_pkg

CRITICAL_SYMBOLS = (
    "get_db",
    "init_db",
    "get_settings",
    "update_settings",
    "upsert_streamer",
    "record_gift_event",
    "record_battle_start",
    "get_dashboard_overview",
    "get_analytics_data",
    "get_donor_radar_data",
    "get_chat_analysis",
    "record_api_call",
    "import_from_sqlite_database",
    "MySQLConnectionWrapper",
    "DBRow",
    "DEFAULT_SETTINGS",
    "_init_mysql_schema",
    "_init_sqlite_schema",
)


class TestDatabaseFacade(unittest.TestCase):
    def test_package_and_facade_export_the_same_names(self):
        self.assertEqual(sorted(db_pkg.__all__), sorted(facade.__all__))

    def test_critical_symbols_are_reachable_via_facade(self):
        for name in CRITICAL_SYMBOLS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(facade, name), f"{name} fehlt in shared.database")

    def test_private_helpers_stay_reachable(self):
        # Wird z.B. von Tests und Migrationsskripten genutzt.
        self.assertTrue(callable(facade._init_mysql_schema))
        self.assertIsNotNone(facade._get_period_cutoff("24h"))
        self.assertIsNotNone(facade._ensure_column_sqlite)

    def test_facade_is_thin(self):
        path = os.path.join(os.path.dirname(__file__), "..", "shared", "database.py")
        with open(path, encoding="utf-8") as handle:
            lines = [ln for ln in handle.read().splitlines() if ln.strip()]
        self.assertLess(len(lines), 30, "shared/database.py soll nur eine Re-Export-Fassade bleiben")

    def test_every_public_db_function_is_reexported(self):
        """Neue DB-Funktionen müssen in shared/db/__init__.py auftauchen."""
        missing = []
        for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "shared", "db", "*.py"))):
            module_name = os.path.basename(path)[:-3]
            if module_name == "__init__":
                continue
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in tree.body:
                is_definition = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                if is_definition and not node.name.startswith("__") and node.name not in db_pkg.__all__:
                    missing.append(f"{module_name}.{node.name}")
        self.assertEqual(missing, [], "Nicht re-exportiert: " + ", ".join(missing))

    def test_modules_import_independently(self):
        for name in ("_base", "settings", "schema", "users", "streamers", "gifts",
                     "battles", "donors", "analytics", "chat", "web_analytics", "sqlite_import"):
            with self.subTest(module=name):
                module = importlib.import_module(f"shared.db.{name}")
                self.assertTrue(module.__doc__)


if __name__ == "__main__":
    unittest.main()
