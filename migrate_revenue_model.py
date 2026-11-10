#!/usr/bin/env python3
"""
TokTracker - einmalige Revenue-Modell-Migration.

Berechnet Gift-Events ab einem Cutoff mit den neuen Revenue-Profilen neu.
Events vor dem Cutoff bleiben unangetastet (Legacy-Snapshots).

Beispiele:
    python migrate_revenue_model.py
    python migrate_revenue_model.py --apply
    python migrate_revenue_model.py --cutoff 2026-11-01 --apply
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from typing import Any, Dict, List

from shared.database import (
    get_db,
    get_revenue_profile_for_streamer,
    init_db,
    invalidate_overview_cache,
    list_revenue_profiles,
)
from shared.revenue import compute_gift_revenue, normalize_profile

BATCH_SIZE = 500
GIFT_UPDATE_SQL = """
UPDATE gift_events
SET usd_net = ?,
    eur_net = ?,
    usd_gross = ?,
    eur_gross = ?,
    usd_net_low = ?,
    usd_net_high = ?,
    eur_net_low = ?,
    eur_net_high = ?,
    revenue_profile_id = ?,
    coin_price_usd = ?,
    creator_share_pct = ?,
    agency_share_pct = ?,
    payout_fee_pct = ?,
    tax_pct = ?,
    fx_rate = ?,
    revenue_model = 'v2-profile'
WHERE id = ?
"""


def _is_retryable(exc: Exception) -> bool:
    text = str(exc)
    return "(1020," in text or "(1213," in text or "deadlock" in text.lower()


def _run_batches(sql: str, rows: List[tuple], label: str) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        for attempt in range(1, 6):
            try:
                with get_db() as conn:
                    conn.executemany(sql, batch)
                break
            except Exception as exc:
                if attempt >= 5 or not _is_retryable(exc):
                    raise
                print(f"{label}: Retry {attempt}/5 nach DB-Konflikt: {exc}")
                time.sleep(0.5 * attempt)
        if start % (BATCH_SIZE * 10) == 0:
            print(f"{label}: {min(start + BATCH_SIZE, len(rows))}/{len(rows)}")


def migrate(cutoff: str, apply: bool) -> None:
    init_db()
    profiles = list_revenue_profiles()
    if not profiles:
        raise SystemExit("Keine Revenue-Profile vorhanden.")

    with get_db() as conn:
        old_row = conn.execute(
            "SELECT COALESCE(SUM(usd_net), 0) AS total FROM gift_events WHERE created_at >= ?",
            (cutoff,),
        ).fetchone()
        gift_rows = conn.execute(
            """
            SELECT id, streamer_id, total_coins
            FROM gift_events
            WHERE created_at >= ?
            ORDER BY id ASC
            """,
            (cutoff,),
        ).fetchall()
    old_total = float(old_row["total"] or 0.0) if old_row else 0.0

    profile_cache: Dict[int, Any] = {}
    new_total = 0.0
    updates: List[tuple] = []
    for row in gift_rows:
        streamer_id = int(row["streamer_id"])
        coins = int(row["total_coins"] or 0)
        profile = profile_cache.get(streamer_id)
        if profile is None:
            profile = get_revenue_profile_for_streamer(streamer_id)
            profile_cache[streamer_id] = profile
        revenue = compute_gift_revenue(coins, profile)
        snapshot = normalize_profile(profile)
        new_total += float(revenue["usd_net"])
        updates.append(
            (
                revenue["usd_net"],
                revenue["eur_net"],
                revenue["usd_gross"],
                revenue["eur_gross"],
                revenue["usd_net_low"],
                revenue["usd_net_high"],
                revenue["eur_net_low"],
                revenue["eur_net_high"],
                int(profile["id"]) if profile and profile.get("id") else None,
                snapshot["coin_price_usd"],
                snapshot["creator_share_pct"],
                snapshot["agency_share_pct"],
                snapshot["payout_fee_pct"],
                snapshot["tax_pct"],
                snapshot["fx_rate"],
                int(row["id"]),
            )
        )

    print(f"Cutoff:      {cutoff}")
    print(f"Gift-Events: {len(updates)}")
    print(f"Altes Netto (USD): {old_total:,.2f}")
    print(f"Neues Netto (USD): {new_total:,.2f}")
    print(f"Delta (USD):       {new_total - old_total:,.2f}")
    if not apply:
        print("Dry-Run – nichts geschrieben. Mit --apply ausführen.")
        return

    _run_batches(GIFT_UPDATE_SQL, updates, "Gift-Events")

    # Battles ab Cutoff ebenfalls mit dem Profil neu bewerten.
    with get_db() as conn:
        battle_rows = conn.execute(
            """
            SELECT id, streamer_id, coins_earned
            FROM tiktok_battles
            WHERE created_at >= ?
            """,
            (cutoff,),
        ).fetchall()
    battle_updates: List[tuple] = []
    for battle in battle_rows:
        streamer_id = int(battle["streamer_id"])
        profile = profile_cache.get(streamer_id)
        if profile is None:
            profile = get_revenue_profile_for_streamer(streamer_id)
            profile_cache[streamer_id] = profile
        revenue = compute_gift_revenue(int(battle["coins_earned"] or 0), profile)
        battle_updates.append(
            (
                round(revenue["usd_net"], 2),
                round(revenue["eur_net"], 2),
                round(revenue["usd_gross"], 2),
                round(revenue["eur_gross"], 2),
                int(battle["id"]),
            )
        )
    if battle_updates:
        _run_batches(
            """
            UPDATE tiktok_battles
            SET usd_net = ?, eur_net = ?, usd_gross = ?, eur_gross = ?
            WHERE id = ?
            """,
            battle_updates,
            "Battles",
        )

    invalidate_overview_cache()
    print("Migration abgeschlossen.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Revenue-Modell-Migration")
    parser.add_argument("--cutoff", default="2026-11-01", help="Cutoff-Datum (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Änderungen wirklich schreiben")
    args = parser.parse_args()
    datetime.strptime(args.cutoff, "%Y-%m-%d")
    migrate(args.cutoff, args.apply)


if __name__ == "__main__":
    main()
