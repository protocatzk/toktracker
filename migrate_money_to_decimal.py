#!/usr/bin/env python3
"""
Migration: Geldspalten von DOUBLE auf DECIMAL(14,4) umstellen.

Hintergrund:
    Geldbeträge in `DOUBLE` unterliegen Binär-Rundungsfehlern. `DECIMAL(14,4)`
    speichert exakt vier Nachkommastellen. Da `DBRow` Decimal beim Lesen zentral
    auf float normalisiert, bleibt das Anwendungsverhalten identisch.

Geltungsbereich:
    Nur MySQL/MariaDB. SQLite kennt kein echtes DECIMAL (REAL bleibt dort bestehen);
    das Skript beendet sich in diesem Fall ohne Änderung.

Nutzung:
    python migrate_money_to_decimal.py            # Dry-Run (zeigt geplante Änderungen)
    python migrate_money_to_decimal.py --apply    # Migration ausführen

Sicherheit:
    - Idempotent: bereits migrierte Spalten werden übersprungen.
    - Vor dem Umbau wird eine Prüfsumme (SUM) der betroffenen Spalten erhoben und
      nach der Migration erneut verglichen.
    - Rollback (manuell): ALTER TABLE ... MODIFY COLUMN ... DOUBLE.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Tuple

from shared.config import config
from shared.db import get_db

# Spaltentypen für den Zielzustand (NOT NULL wie im Schema).
MONEY_COLUMNS: Dict[str, Dict[str, str]] = {
    "gift_events": {
        "usd_net": "DECIMAL(14,4) NOT NULL",
        "eur_net": "DECIMAL(14,4) NOT NULL",
        "usd_gross": "DECIMAL(14,4) NOT NULL",
        "eur_gross": "DECIMAL(14,4) NOT NULL",
    },
    "tiktok_battles": {
        "usd_net": "DECIMAL(14,4) DEFAULT 0.0000",
        "eur_net": "DECIMAL(14,4) DEFAULT 0.0000",
        "usd_gross": "DECIMAL(14,4) DEFAULT 0.0000",
        "eur_gross": "DECIMAL(14,4) DEFAULT 0.0000",
    },
}


def _current_types(conn) -> Dict[Tuple[str, str], str]:
    tables = tuple(MONEY_COLUMNS.keys())
    rows = conn.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN (?, ?)
          AND COLUMN_NAME IN ('usd_net', 'eur_net', 'usd_gross', 'eur_gross')
        """,
        (tables[0], tables[1]),
    ).fetchall()
    return {(str(r["TABLE_NAME"]), str(r["COLUMN_NAME"])): str(r["DATA_TYPE"]).lower() for r in rows}


def _checksums(conn) -> Dict[str, float]:
    sums: Dict[str, float] = {}
    for table, columns in MONEY_COLUMNS.items():
        expr = ", ".join(f"COALESCE(SUM(`{col}`), 0)" for col in columns)
        row = conn.execute(f"SELECT {expr} FROM `{table}`").fetchone()
        for idx, col in enumerate(columns):
            sums[f"{table}.{col}"] = float(row[idx] or 0)
    return sums


def _plan(types: Dict[Tuple[str, str], str]) -> List[Tuple[str, str, str]]:
    planned: List[Tuple[str, str, str]] = []
    for table, columns in MONEY_COLUMNS.items():
        for column, ddl in columns.items():
            if types.get((table, column)) != "decimal":
                planned.append((table, column, ddl))
    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description="Geldspalten auf DECIMAL(14,4) migrieren")
    parser.add_argument("--apply", action="store_true", help="Migration ausführen (Default: Dry-Run)")
    args = parser.parse_args()

    if not config.is_mysql:
        print("DB_ENGINE ist nicht mysql – nichts zu tun (SQLite speichert REAL).")
        return 0

    with get_db() as conn:
        types = _current_types(conn)
        if not types:
            print("Keine Geldspalten gefunden – bitte zuerst die Tabellen initialisieren (init_db).")
            return 1

        planned = _plan(types)
        if not planned:
            print("Alle Geldspalten sind bereits DECIMAL – nichts zu tun.")
            return 0

        print(f"Geplante Änderungen ({len(planned)}):")
        for table, column, ddl in planned:
            print(f"  {table}.{column}: {types.get((table, column), '?')} -> {ddl}")

        if not args.apply:
            print("\nDry-Run. Migration mit '--apply' ausführen.")
            return 0

        before = _checksums(conn)
        print("\nPrüfsummen vor der Migration:")
        for key, value in before.items():
            print(f"  {key}: {value:.4f}")

        for table, column, ddl in planned:
            conn.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {ddl}")
            print(f"  migriert: {table}.{column}")

    # Neue Verbindung: ALTER TABLE committet implizit, danach frisch lesen.
    with get_db() as conn:
        after = _checksums(conn)
        types_after = _current_types(conn)

    print("\nPrüfsummen nach der Migration:")
    mismatches = []
    for key, value in after.items():
        delta = abs(value - before[key])
        status = "OK" if delta <= 0.01 else "ABWEICHUNG"
        if status != "OK":
            mismatches.append(key)
        print(f"  {key}: {value:.4f} (Delta {delta:.4f}) {status}")

    remaining = [f"{t}.{c}" for t, c, _ in _plan(types_after)]
    if remaining:
        print(f"\nNicht migriert: {', '.join(remaining)}")
        return 1
    if mismatches:
        print(f"\nWARNUNG: Prüfsummen weichen ab: {', '.join(mismatches)}")
        return 2

    print("\nMigration erfolgreich abgeschlossen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
