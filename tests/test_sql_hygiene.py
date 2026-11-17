"""
SQL-Hygiene für die MariaDB-Engine.

MariaDB/MySQL ist die einzige Datenbank-Engine (Dev, Tests, Produktion). Diese
Tests verhindern, dass SQLite-Dialekt oder ein zweiter Übersetzungspfad
zurückkehrt und dass die Testsuite wieder von der Produktions-Engine abweicht.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import glob
import inspect
import os
import re
import unittest

from shared.database import MariaDBConnection

_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "shared", "db")

# Konstrukte, die es nur in SQLite gibt bzw. die den entfernten Dialekt-Übersetzer
# gebraucht hätten. Query-Code muss natives MariaDB-SQL enthalten.
FORBIDDEN_PATTERNS = {
    "INSERT OR IGNORE": re.compile(r"INSERT\s+OR\s+IGNORE", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"INSERT\s+OR\s+REPLACE", re.IGNORECASE),
    "REPLACE INTO": re.compile(r"\bREPLACE\s+INTO\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "sqlite3": re.compile(r"\bsqlite3\b", re.IGNORECASE),
    "MAX(a, b)": re.compile(r"\bMAX\s*\(\s*last_fan_tickets\s*,", re.IGNORECASE),
}


class TestMariaDBOnly(unittest.TestCase):
    def test_no_sqlite_constructs_in_db_modules(self):
        offenders = []
        for path in sorted(glob.glob(os.path.join(_DB_DIR, "*.py"))):
            if os.path.basename(path) == "__init__.py":
                continue
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            # Kommentare (z.B. "# pragma: no cover") ignorieren, damit nur
            # echtes SQL geprüft wird.
            source = re.sub(r"#[^\n]*", "", source)
            for label, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(source):
                    offenders.append(f"{os.path.basename(path)}: {label}")
        self.assertEqual(
            offenders,
            [],
            "SQLite-Dialekt in shared/db gefunden: " + ", ".join(offenders),
        )

    def test_no_sqlite_runtime_modules_remain(self):
        self.assertFalse(os.path.exists(os.path.join(_DB_DIR, "sqlite_import.py")))

    def test_placeholder_binding_is_mechanical(self):
        sql = "SELECT * FROM gift_events WHERE streamer_id = ? AND created_at >= ?"
        self.assertEqual(
            MariaDBConnection._bind_params(sql),
            "SELECT * FROM gift_events WHERE streamer_id = %s AND created_at >= %s",
        )
        # Literale Prozentzeichen werden nicht angefasst (kein LIKE-Umschreiben).
        self.assertEqual(
            MariaDBConnection._bind_params("SELECT '100%' AS p WHERE 'a' LIKE 'a%'"),
            "SELECT '100%' AS p WHERE 'a' LIKE 'a%'",
        )

    def test_no_semantic_translation_layer(self):
        # Der Wrapper darf die Semantik nicht mehr ändern.
        self.assertFalse(hasattr(MariaDBConnection, "_translate_sql"))

    def test_fan_ticket_upsert_uses_greatest(self):
        from shared.db import gifts

        source = inspect.getsource(gifts)
        self.assertIn("GREATEST(last_fan_tickets", source)

    def test_settings_upsert_uses_on_duplicate_key(self):
        from shared.db import settings as settings_module

        source = inspect.getsource(settings_module)
        self.assertIn("ON DUPLICATE KEY UPDATE", source)


class TestSchemaIsMariaDBOnly(unittest.TestCase):
    def test_schema_module_has_no_sqlite_branch(self):
        from shared.db import schema

        source = inspect.getsource(schema)
        self.assertNotIn("_init_sqlite_schema", source)
        self.assertNotIn("PRAGMA", source)

    def test_init_db_uses_single_schema(self):
        from shared.db import schema

        source = inspect.getsource(schema.init_db)
        self.assertIn("_init_schema()", source)
        self.assertNotIn("_init_sqlite_schema", source)


if __name__ == "__main__":
    unittest.main()
