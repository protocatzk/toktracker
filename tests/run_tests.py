#!/usr/bin/env python3
"""
Zentraler Test-Runner für TokTracker.
Führt alle Komponenten-Tests ressourcenschonend und ohne externe Quoten aus.
"""
import os
import sys
import time
import unittest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_all_tests():
    print("=" * 65)
    print("🚀 TokTracker Test-Suite: Ressourcensparende Komponenten-Tests")
    print("=" * 65)

    loader = unittest.TestLoader()
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(tests_dir, pattern="test_*.py", top_level_dir=tests_dir)

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print("\n" + "=" * 65)
    print(f"⏱  Gesamtdauer: {elapsed:.2f} Sekunden")
    print(f"📊 Ausgeführte Tests: {result.testsRun}")
    print(f"✅ Erfolgreich: {result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)}")
    print(f"⏭  Übersprungen: {len(result.skipped)}")
    print(f"❌ Fehlgeschlagen: {len(result.failures)}")
    print(f"💥 Fehler: {len(result.errors)}")
    print("=" * 65)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
