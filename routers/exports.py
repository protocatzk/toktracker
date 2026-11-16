"""
CSV-Exporte für Geschenke und Battles.

Aus ``app.py`` ausgelagert. Die Endpunkt-Pfade und Berechtigungen bleiben
unverändert; die DB-Abfragen laufen weiterhin über ``asyncio.to_thread``.
"""

import asyncio
import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from shared.api_deps import require_permission
from shared.database import get_db, get_group_streamer_ids, init_db
from shared.permissions import PERM_EXPORT_DOWNLOAD

router = APIRouter()


def _export_scope_clause(
    column: str, streamer_id: Optional[int], group_id: Optional[int]
) -> Tuple[str, Tuple[Any, ...]]:
    """Baut die optionale Scope-Bedingung für CSV-Exporte (Streamer oder Gruppe)."""
    if streamer_id:
        return f" WHERE {column} = ?", (int(streamer_id),)
    if group_id:
        ids = get_group_streamer_ids(int(group_id))
        if not ids:
            return " WHERE 1 = 0", ()
        placeholders = ",".join("?" for _ in ids)
        return f" WHERE {column} IN ({placeholders})", tuple(ids)
    return "", ()


def _fetch_gift_export_rows(
    streamer_id: Optional[int], group_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Synchroner DB-Zugriff für den CSV-Export (läuft via to_thread)."""
    scope_sql, scope_params = _export_scope_clause("g.streamer_id", streamer_id, group_id)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT g.*, s.username AS streamer_username
            FROM gift_events g
            JOIN streamers s ON s.id = g.streamer_id
            {scope_sql}
            ORDER BY g.created_at DESC
            """,
            scope_params,
        ).fetchall()
    return [dict(r) for r in rows]


def _fetch_battle_export_rows(
    streamer_id: Optional[int], group_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Synchroner DB-Zugriff für den Battle-CSV-Export (läuft via to_thread)."""
    scope_sql, scope_params = _export_scope_clause("b.streamer_id", streamer_id, group_id)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT b.*, s.username AS streamer_username
            FROM tiktok_battles b
            JOIN streamers s ON s.id = b.streamer_id
            {scope_sql}
            ORDER BY b.started_at DESC
            """,
            scope_params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/export/gifts.csv", tags=["Dashboard & Data"], dependencies=[Depends(require_permission(PERM_EXPORT_DOWNLOAD))])
async def api_export_gifts_csv(
    streamer_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None, description="Optionale Streamer-Gruppe als Scope"),
):
    init_db()
    rows = await asyncio.to_thread(_fetch_gift_export_rows, streamer_id, group_id)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "id",
            "created_at",
            "streamer_username",
            "session_id",
            "sender_username",
            "sender_nickname",
            "is_super_fan",
            "gift_id",
            "gift_name",
            "diamond_count",
            "repeat_count",
            "total_coins",
            "usd_net",
            "eur_net",
            "usd_gross",
            "eur_gross",
            "source",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["created_at"],
                r["streamer_username"],
                r["session_id"],
                r["sender_username"],
                r["sender_nickname"],
                r["is_super_fan"],
                r["gift_id"],
                r["gift_name"],
                r["diamond_count"],
                r["repeat_count"],
                r["total_coins"],
                r["usd_net"],
                r["eur_net"],
                r["usd_gross"],
                r["eur_gross"],
                r["source"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=toktracker_gifts_export.csv"},
    )


@router.get("/api/export/battles.csv", tags=["TikTok Battles"], dependencies=[Depends(require_permission(PERM_EXPORT_DOWNLOAD))])
async def api_export_battles_csv(
    streamer_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None, description="Optionale Streamer-Gruppe als Scope"),
):
    init_db()
    b_rows = await asyncio.to_thread(_fetch_battle_export_rows, streamer_id, group_id)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "id",
            "battle_id",
            "battle_mode",
            "streamer_username",
            "streamer_score",
            "teammate_username",
            "teammate_score",
            "opponent_username",
            "opponent_display_name",
            "opponent_score",
            "opponent2_username",
            "opponent2_score",
            "opponent3_username",
            "opponent3_score",
            "streamer_rank",
            "started_at",
            "ended_at",
            "duration_seconds",
            "result",
            "streamer_mvp_name",
            "streamer_mvp_score",
            "opponent_mvp_name",
            "opponent_mvp_score",
            "coins_earned",
            "eur_net",
            "usd_net",
            "status",
        ]
    )
    for r in b_rows:
        writer.writerow(
            [
                r["id"],
                r["battle_id"],
                r["battle_mode"] or "1v1",
                r["streamer_username"],
                r["streamer_score"],
                r["teammate_username"] or "",
                r["teammate_score"] or 0,
                r["opponent_username"],
                r["opponent_display_name"],
                r["opponent_score"],
                r["opponent2_username"] or "",
                r["opponent2_score"] or 0,
                r["opponent3_username"] or "",
                r["opponent3_score"] or 0,
                r["streamer_rank"] or 0,
                r["started_at"],
                r["ended_at"] or "",
                r["duration_seconds"],
                r["result"],
                r["streamer_mvp_name"] or "",
                r["streamer_mvp_score"] or 0,
                r["opponent_mvp_name"] or "",
                r["opponent_mvp_score"] or 0,
                r["coins_earned"] or 0,
                r["eur_net"] or 0.0,
                r["usd_net"] or 0.0,
                r["status"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=tiktok_battles_export.csv"},
    )
