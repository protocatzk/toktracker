"""
Architektur-Guard: kein blockierender DB-Zugriff in ``async def``-Endpunkten.

FastAPI führt ``async def``-Handler direkt im Event-Loop aus. Ein synchroner
Datenbankzugriff dort blockiert den gesamten Worker – inklusive ``/api/health``.
Dieser Test erzwingt deshalb: Endpunkte mit DB-Bedarf sind entweder als
``def`` deklariert (FastAPI nutzt dann den Threadpool) oder kapseln den Zugriff
in ``asyncio.to_thread``.

Die Ausnahmen sind Middlewares und der Lifespan-Start: Sie müssen ``async``
bleiben, laufen aber nicht pro Request bzw. nur einmal beim Boot.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import ast
import pathlib
import unittest

APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

DB_MODULES = {"database", "shared.database", "shared.db"}

# Bewusst erlaubt: laufen nicht pro Request oder nur einmal beim Start.
ALLOWED_ASYNC_DB_ACCESS = {
    "lifespan": "Boot-Phase, blockiert keinen Request",
    "track_page_views_middleware": "Middleware, kein Endpunkt",
    "access_gate_middleware": "Middleware, kein Endpunkt",
}

# ``init_db`` ist nach dem ersten Aufruf ein No-op und daher unkritisch.
IGNORED_FUNCTIONS = {"init_db"}


def _db_function_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in DB_MODULES:
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _tothread_subtree_ids(node: ast.AST) -> set[int]:
    """IDs aller AST-Knoten, die als Argument an ``asyncio.to_thread`` gehen."""
    ids: set[int] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "to_thread"
        ):
            for arg in child.args:
                ids.update(id(inner) for inner in ast.walk(arg))
    return ids


def _blocking_db_usage(function: ast.AsyncFunctionDef, db_names: set[str]) -> list[str]:
    wrapped = _tothread_subtree_ids(function)
    findings: list[str] = []

    for node in ast.walk(function):
        if isinstance(node, ast.With):
            for item in node.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Name)
                    and expr.func.id == "get_db"
                ):
                    findings.append(f"Zeile {node.lineno}: 'with get_db()'")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in db_names
            and node.func.id not in IGNORED_FUNCTIONS
            and id(node) not in wrapped
        ):
            findings.append(f"Zeile {node.lineno}: direkter Aufruf '{node.func.id}()'")

    return findings


class TestAsyncDbGuard(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        self.db_names = _db_function_names(self.tree)

    def test_db_module_functions_detected(self):
        # Schutz gegen einen stillen Leerlauf des Guards.
        self.assertIn("get_db", self.db_names)
        self.assertIn("get_dashboard_overview", self.db_names)

    def test_async_endpoints_do_not_touch_db_directly(self):
        offenders: list[str] = []
        for node in self.tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name in ALLOWED_ASYNC_DB_ACCESS:
                continue
            findings = _blocking_db_usage(node, self.db_names)
            if findings:
                offenders.append(f"{node.name}() – " + ", ".join(findings))

        self.assertEqual(
            offenders,
            [],
            "Blockierender DB-Zugriff in async def. Entweder als 'def' deklarieren "
            "(Threadpool) oder in 'asyncio.to_thread' kapseln:\n- " + "\n- ".join(offenders),
        )


class TestGuardLogic(unittest.TestCase):
    """Prüft den Detektor selbst, damit der Guard nicht still leerläuft."""

    def _detect(self, source: str) -> dict[str, list[str]]:
        tree = ast.parse(source)
        names = _db_function_names(tree)
        return {
            node.name: _blocking_db_usage(node, names)
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }

    def test_detects_direct_calls_and_get_db(self):
        found = self._detect(
            """
from shared.db import get_dashboard_overview, get_db

async def broken_call():
    get_dashboard_overview()

async def broken_context():
    with get_db() as conn:
        pass

async def wrapped():
    await asyncio.to_thread(get_dashboard_overview)

def sync_is_fine():
    get_dashboard_overview()
"""
        )
        self.assertTrue(found["broken_call"])
        self.assertTrue(found["broken_context"])
        self.assertEqual(found["wrapped"], [])
        self.assertNotIn("sync_is_fine", found)


if __name__ == "__main__":
    unittest.main()
