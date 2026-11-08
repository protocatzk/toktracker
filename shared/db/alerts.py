"""
TokTracker - Live-Alert-Abonnements für Telegram-Chats.

Ein Eintrag verbindet einen Streamer mit einem Telegram-Chat (Gruppe oder
Privatchat). Der Bot verschickt beim Wechsel des Streamers auf "live" eine
Nachricht an alle abonnierten Chats.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.db._base import get_db


def add_streamer_alert(
    streamer_id: int,
    chat_id: int,
    chat_title: str = "",
    created_by_telegram_id: Optional[int] = None,
    created_by_username: str = "",
) -> Dict[str, Any]:
    """Legt ein Alert-Abo an oder aktualisiert ein bestehendes."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM streamer_alerts WHERE streamer_id = ? AND chat_id = ?",
            (int(streamer_id), int(chat_id)),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE streamer_alerts
                SET chat_title = ?,
                    created_by_telegram_id = ?,
                    created_by_username = ?,
                    enabled = 1
                WHERE id = ?
                """,
                (
                    chat_title or existing["chat_title"] or "",
                    created_by_telegram_id,
                    created_by_username or existing["created_by_username"] or "",
                    existing["id"],
                ),
            )
            row_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO streamer_alerts (
                    streamer_id, chat_id, chat_title, created_by_telegram_id,
                    created_by_username, enabled, created_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    int(streamer_id),
                    int(chat_id),
                    chat_title or "",
                    created_by_telegram_id,
                    created_by_username or "",
                    now,
                ),
            )
            row_id = cur.lastrowid

        row = conn.execute(
            "SELECT * FROM streamer_alerts WHERE id = ?", (row_id,)
        ).fetchone()
        return dict(row)


def remove_streamer_alert(streamer_id: int, chat_id: int) -> bool:
    """Entfernt das Alert-Abo eines Streamers für einen Chat."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM streamer_alerts WHERE streamer_id = ? AND chat_id = ?",
            (int(streamer_id), int(chat_id)),
        )
        return cur.rowcount > 0


def list_streamer_alert_subscriptions(
    streamer_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    enabled_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Liefert Alert-Abos inkl. Streamer-Metadaten.

    Ohne Filter werden alle Abos zurückgegeben (z.B. für Diagnose). Mit
    `streamer_id` erhält der Bot alle Ziel-Chats für ein Live-Event.
    """
    where = []
    params: List[Any] = []
    if streamer_id is not None:
        where.append("a.streamer_id = ?")
        params.append(int(streamer_id))
    if chat_id is not None:
        where.append("a.chat_id = ?")
        params.append(int(chat_id))
    if enabled_only:
        where.append("a.enabled = 1")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.*,
                s.username AS streamer_username,
                s.display_name AS streamer_display_name,
                s.avatar_url AS streamer_avatar_url,
                s.is_live AS streamer_is_live
            FROM streamer_alerts a
            JOIN streamers s ON s.id = a.streamer_id
            {where_sql}
            ORDER BY s.username ASC, a.chat_id ASC
            """,
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_streamer_alert_notified(alert_id: int, session_id: int) -> bool:
    """
    Markiert eine Session als für dieses Abo benachrichtigt.

    Gibt True zurück, wenn die Session neu war. So werden doppelte Alerts
    bei Reconnects oder mehrfach zugestellten Events vermieden.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE streamer_alerts
            SET last_notified_session_id = ?, last_notified_at = ?
            WHERE id = ?
              AND (last_notified_session_id IS NULL OR last_notified_session_id != ?)
            """,
            (int(session_id), now, int(alert_id), int(session_id)),
        )
        return cur.rowcount > 0
