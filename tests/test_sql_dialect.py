"""
Tests für die SQL-Dialekt-Übersetzung (SQLite -> MySQL) und die Schema-Symmetrie.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import inspect
import re
import unittest

from shared import database
from shared.database import MySQLConnectionWrapper


class TestSqlTranslation(unittest.TestCase):
    def test_placeholders(self):
        sql = "SELECT * FROM gift_events WHERE streamer_id = ? AND created_at >= ?"
        self.assertEqual(
            MySQLConnectionWrapper._translate_sql(sql),
            "SELECT * FROM gift_events WHERE streamer_id = %s AND created_at >= %s",
        )

    def test_insert_or_ignore(self):
        sql = "INSERT OR IGNORE INTO settings (`key`, `value`) VALUES (?, ?)"
        self.assertEqual(
            MySQLConnectionWrapper._translate_sql(sql),
            "INSERT IGNORE INTO settings (`key`, `value`) VALUES (%s, %s)",
        )

    def test_insert_or_replace(self):
        sql = "insert or replace into settings (`key`, `value`) VALUES (?, ?)"
        self.assertEqual(
            MySQLConnectionWrapper._translate_sql(sql),
            "REPLACE INTO settings (`key`, `value`) VALUES (%s, %s)",
        )

    def test_max_becomes_greatest(self):
        sql = "UPDATE stream_sessions SET last_fan_tickets = MAX(last_fan_tickets, ?) WHERE id = ?"
        self.assertEqual(
            MySQLConnectionWrapper._translate_sql(sql),
            "UPDATE stream_sessions SET last_fan_tickets = GREATEST(last_fan_tickets, %s) WHERE id = %s",
        )

    def test_unrelated_max_is_untouched(self):
        sql = "SELECT MAX(created_at) FROM gift_events WHERE id = ?"
        self.assertEqual(
            MySQLConnectionWrapper._translate_sql(sql),
            "SELECT MAX(created_at) FROM gift_events WHERE id = %s",
        )


class TestSchemaSymmetry(unittest.TestCase):
    @staticmethod
    def _tables(function) -> set:
        source = inspect.getsource(function)
        return set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+`?(\w+)`?", source))

    def test_both_engines_define_the_same_tables(self):
        mysql_tables = self._tables(database._init_mysql_schema)
        sqlite_tables = self._tables(database._init_sqlite_schema)
        self.assertTrue(mysql_tables)
        self.assertEqual(mysql_tables, sqlite_tables)


if __name__ == "__main__":
    unittest.main()
