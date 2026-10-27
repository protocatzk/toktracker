"""
Tests für die Geldspalten-Migration (DOUBLE -> DECIMAL) und die Typ-Normalisierung.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import inspect
import re
import unittest
from decimal import Decimal

import migrate_money_to_decimal as migration
from shared.db import schema
from shared.db._base import DBRow


class TestDecimalNormalization(unittest.TestCase):
    def test_dbrow_converts_decimal_to_float(self):
        row = DBRow({"usd_net": Decimal("1.2345"), "eur_net": Decimal("1.1400"), "name": "x"})
        self.assertIsInstance(row["usd_net"], float)
        self.assertAlmostEqual(row["usd_net"], 1.2345)
        self.assertAlmostEqual(row["eur_net"], 1.14)
        self.assertEqual(row["name"], "x")

    def test_dbrow_keeps_other_types(self):
        row = DBRow({"id": 7, "ok": True, "note": None})
        self.assertEqual(row["id"], 7)
        self.assertIs(row["ok"], True)
        self.assertIsNone(row["note"])

    def test_dbrow_supports_numeric_index_after_normalization(self):
        row = DBRow({"a": Decimal("2.5"), "b": 3})
        self.assertAlmostEqual(row[0], 2.5)
        self.assertEqual(row[1], 3)

    def test_dbrow_values_are_json_serializable(self):
        import json

        row = DBRow({"usd_net": Decimal("0.5000")})
        self.assertEqual(json.loads(json.dumps(dict(row))), {"usd_net": 0.5})


class TestSchemaTypes(unittest.TestCase):
    def test_mysql_money_columns_use_decimal(self):
        source = inspect.getsource(schema._init_mysql_schema)
        for column in ("usd_net", "eur_net", "usd_gross", "eur_gross"):
            with self.subTest(column=column):
                self.assertRegex(
                    source,
                    rf"{column}\s+DECIMAL\(14,4\)",
                    f"{column} sollte in MySQL DECIMAL(14,4) sein",
                )
                self.assertNotRegex(source, rf"{column}\s+DOUBLE")

    def test_sqlite_money_columns_remain_real(self):
        source = inspect.getsource(schema._init_sqlite_schema)
        for column in ("usd_net", "eur_net", "usd_gross", "eur_gross"):
            with self.subTest(column=column):
                self.assertRegex(source, rf"{column}\s+REAL")

    def test_migration_targets_exactly_the_schema_columns(self):
        mysql_source = inspect.getsource(schema._init_mysql_schema)
        for table, columns in migration.MONEY_COLUMNS.items():
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", mysql_source)
            for column in columns:
                with self.subTest(table=table, column=column):
                    self.assertRegex(mysql_source, rf"{column}\s+DECIMAL\(14,4\)")

    def test_migration_plan_is_empty_for_decimal_columns(self):
        types = {(table, col): "decimal" for table, cols in migration.MONEY_COLUMNS.items() for col in cols}
        self.assertEqual(migration._plan(types), [])

    def test_migration_plan_flags_double_columns(self):
        types = {(table, col): "double" for table, cols in migration.MONEY_COLUMNS.items() for col in cols}
        planned = migration._plan(types)
        self.assertEqual(len(planned), sum(len(c) for c in migration.MONEY_COLUMNS.values()))
        for table, column, ddl in planned:
            self.assertIn("DECIMAL(14,4)", ddl)
            self.assertRegex(f"{table}.{column}", r"^[a-z_]+\.[a-z_]+$")


if __name__ == "__main__":
    unittest.main()
