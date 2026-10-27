"""
TokTracker - Streamer-Stammdaten, Runtime-Status und Stream-Sessions.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import _get_period_cutoff, get_db
from shared.db.gifts import record_gift_event


def get_streamer_by_id_or_username(identifier: str | int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        if isinstance(identifier, int) or str(identifier).isdigit():
            row = conn.execute(
                "SELECT * FROM streamers WHERE id = ?", (int(identifier),)
            ).fetchone()
            if row:
                return dict(row)
        clean = str(identifier).strip().lstrip("@").lower()
        row = conn.execute(
            "SELECT * FROM streamers WHERE LOWER(username) = LOWER(?)", (clean,)
        ).fetchone()
        return dict(row) if row else None


def get_auto_monitor_streamers() -> List[Dict[str, Any]]:
    """
    Liefert alle Streamer zurück, die in der Datenbank für die automatische Aufzeichnung
    markiert sind (`auto_monitor = 1` oder `is_tracking = 1`).
    Synchronisiert dabei `auto_monitor = 1`, damit der Status konsistent bleibt.
    """
    with get_db() as conn:
        conn.execute(
            "UPDATE streamers SET auto_monitor = 1 WHERE is_tracking = 1 AND auto_monitor = 0"
        )
        rows = conn.execute(
            "SELECT * FROM streamers WHERE auto_monitor = 1 OR is_tracking = 1 ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_streamer(
    username: str,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    room_id: Optional[str] = None,
    follower_count: Optional[int] = None,
    is_live: Optional[bool] = None,
    auto_monitor: Optional[bool] = None,
) -> Dict[str, Any]:
    clean_username = username.strip().lstrip("@").lower()
    if not clean_username:
        raise ValueError("Username darf nicht leer sein.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM streamers WHERE LOWER(username) = LOWER(?)", (clean_username,)
        ).fetchone()

        if existing:
            new_display = display_name if display_name else existing["display_name"]
            new_avatar = avatar_url if avatar_url else existing["avatar_url"]
            new_room = room_id if room_id is not None else existing["room_id"]
            new_followers = (
                follower_count if follower_count is not None else existing["follower_count"]
            )
            new_live = int(is_live) if is_live is not None else existing["is_live"]
            new_auto = (
                int(auto_monitor) if auto_monitor is not None else existing["auto_monitor"]
            )
            conn.execute(
                """
                UPDATE streamers
                SET display_name = ?, avatar_url = ?, room_id = ?,
                    follower_count = ?, is_live = ?, auto_monitor = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (
                    new_display,
                    new_avatar,
                    new_room,
                    new_followers,
                    new_live,
                    new_auto,
                    now,
                    existing["id"],
                ),
            )
            streamer_id = existing["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO streamers (
                    username, display_name, avatar_url, room_id,
                    follower_count, is_live, auto_monitor, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_username,
                    display_name or clean_username,
                    avatar_url or "",
                    room_id or "",
                    follower_count or 0,
                    int(bool(is_live)),
                    int(bool(auto_monitor)),
                    now,
                    now,
                ),
            )
            streamer_id = cursor.lastrowid

        row = conn.execute(
            "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
        ).fetchone()
        return dict(row)


def update_streamer_runtime_state(
    username: str,
    is_live: Optional[bool] = None,
    is_tracking: Optional[bool] = None,
    auto_monitor: Optional[bool] = None,
    room_id: Optional[str] = None,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    follower_count: Optional[int] = None,
    current_viewers: Optional[int] = None,
    last_error: Optional[str] = None,
) -> None:
    clean_username = username.strip().lstrip("@").lower()
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamers WHERE LOWER(username) = LOWER(?)", (clean_username,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            """
            UPDATE streamers
            SET is_live = COALESCE(?, is_live),
                is_tracking = COALESCE(?, is_tracking),
                auto_monitor = COALESCE(?, auto_monitor),
                room_id = COALESCE(?, room_id),
                display_name = COALESCE(?, display_name),
                avatar_url = COALESCE(?, avatar_url),
                follower_count = COALESCE(?, follower_count),
                current_viewers = COALESCE(?, current_viewers),
                last_error = COALESCE(?, last_error),
                last_seen_at = ?
            WHERE id = ?
            """,
            (
                int(is_live) if is_live is not None else None,
                int(is_tracking) if is_tracking is not None else None,
                int(auto_monitor) if auto_monitor is not None else None,
                room_id,
                display_name,
                avatar_url,
                follower_count,
                current_viewers,
                last_error,
                now,
                row["id"],
            ),
        )


def start_stream_session(
    streamer_id: int, room_id: str = "", title: str = ""
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        active = conn.execute(
            """
            SELECT id, room_id FROM stream_sessions
            WHERE streamer_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
            """,
            (streamer_id,),
        ).fetchone()

        if active and (not room_id or active["room_id"] == room_id):
            if title:
                conn.execute(
                    "UPDATE stream_sessions SET title = ? WHERE id = ?",
                    (title, active["id"]),
                )
            return int(active["id"])

        conn.execute(
            """
            UPDATE stream_sessions
            SET status = 'ended', ended_at = ?
            WHERE streamer_id = ? AND status = 'active'
            """,
            (now, streamer_id),
        )

        cur = conn.execute(
            """
            INSERT INTO stream_sessions (
                streamer_id, room_id, title, started_at, status
            )
            VALUES (?, ?, ?, ?, 'active')
            """,
            (streamer_id, room_id or "", title or "", now),
        )
        return int(cur.lastrowid)


def update_stream_session_metrics(
    session_id: int,
    viewer_count: Optional[int] = None,
    room_fan_tickets: Optional[int] = None,
) -> None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT peak_viewers, last_fan_tickets FROM stream_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        new_peak = max(int(row["peak_viewers"] or 0), int(viewer_count or 0))
        new_tickets = max(int(row["last_fan_tickets"] or 0), int(room_fan_tickets or 0))
        conn.execute(
            """
            UPDATE stream_sessions
            SET peak_viewers = ?, last_fan_tickets = ?
            WHERE id = ?
            """,
            (new_peak, new_tickets, session_id),
        )


def end_stream_session(streamer_id: int, session_id: Optional[int] = None) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        if session_id:
            conn.execute(
                "UPDATE stream_sessions SET status = 'ended', ended_at = ? WHERE id = ?",
                (now, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE stream_sessions
                SET status = 'ended', ended_at = ?
                WHERE streamer_id = ? AND status = 'active'
                """,
                (now, streamer_id),
            )


def delete_streamer(streamer_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM streamers WHERE id = ?", (streamer_id,))
        return cur.rowcount > 0


def seed_demo_data() -> None:
    demo_streamers: List[Dict[str, Any]] = [
        {"username": "montanablack", "display_name": "MontanaBlack", "follower_count": 2950000},
        {"username": "eliasn97", "display_name": "EliasN97", "follower_count": 1850000},
        {"username": "papaplatte", "display_name": "Papaplatte", "follower_count": 1420000},
    ]
    now = datetime.now()
    streamer_ids = {}
    for s in demo_streamers:
        row = upsert_streamer(
            username=s["username"],
            display_name=s["display_name"],
            follower_count=s["follower_count"],
        )
        streamer_ids[s["username"]] = row["id"]

    sample_gifts = [
        ("montanablack", "king_donator99", "KingDonator", "TikTok Universe", 44999, 1, 1),
        ("montanablack", "lukas_hh", "Lukas HH", "Lion", 29999, 1, 2),
        ("montanablack", "max_power", "MaxPower", "Galaxy", 1000, 12, 6),
        ("eliasn97", "fokus_fan1", "FOKUS Ultra", "Lion", 29999, 1, 2),
        ("eliasn97", "berlin_boy", "BerlinBoy", "Sports Car", 7000, 3, 5),
        ("papaplatte", "domo_enjoyer", "DomoEnjoyer", "Falcon", 10999, 2, 12),
    ]
    for idx, (uname, sender, nick, gname, diamonds, repeat, hours_ago) in enumerate(sample_gifts):
        ts = (now - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        record_gift_event(
            streamer_id=streamer_ids[uname],
            sender_username=sender,
            sender_nickname=nick,
            gift_name=gname,
            diamond_count=diamonds,
            repeat_count=repeat,
            event_uid=f"demo-{uname}-{idx}",
            source="demo",
            created_at=ts,
        )


def clear_demo_data() -> int:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM gift_events WHERE source = 'demo'")
        return cur.rowcount


def get_stream_sessions(
    streamer_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Liefert eine sortierte Liste aller erfassten Stream-Sessions mit Streamer-Details
    und der Anzahl zugeordneter Chatnachrichten für das Sessions-Dropdown.
    """
    where_clauses = ["1=1"]
    params: List[Any] = []

    if streamer_id:
        where_clauses.append("ss.streamer_id = ?")
        params.append(streamer_id)

    if status:
        where_clauses.append("ss.status = ?")
        params.append(status)

    where_sql = " AND ".join(where_clauses)
    query = f"""
    SELECT
        ss.id, ss.streamer_id, ss.room_id, ss.title, ss.started_at, ss.ended_at,
        ss.peak_viewers, ss.last_fan_tickets, ss.status,
        s.username AS streamer_username, s.display_name AS streamer_display_name,
        s.avatar_url AS streamer_avatar_url
    FROM stream_sessions ss
    JOIN streamers s ON s.id = ss.streamer_id
    WHERE {where_sql}
    ORDER BY ss.id DESC
    LIMIT ? OFFSET ?
    """
    params.extend([max(1, min(limit, 300)), max(0, offset)])

    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        if not rows:
            return []

        session_ids = [r["id"] for r in rows if r.get("id")]
        chat_counts = {}
        if session_ids:
            placeholders = ", ".join(["?"] * len(session_ids))
            count_sql = f"""
            SELECT session_id, COUNT(*) AS cnt
            FROM chat_messages
            WHERE session_id IN ({placeholders})
            GROUP BY session_id
            """
            for crow in conn.execute(count_sql, session_ids).fetchall():
                try:
                    chat_counts[crow["session_id"]] = int(crow["cnt"])
                except Exception:
                    pass

        for r in rows:
            r["chat_count"] = chat_counts.get(r["id"], 0)

        return rows


def get_all_streamers_summary() -> List[Dict[str, Any]]:
    """
    Liefert alle registrierten Streamer sortiert nach Live-Status und heutigem Umsatz.
    """
    cutoff = _get_period_cutoff("today")
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.username, s.display_name, s.avatar_url, s.is_live,
                s.is_tracking, s.current_viewers, s.last_seen_at,
                COALESCE(SUM(g.total_coins), 0) as today_coins,
                COALESCE(SUM(g.eur_net), 0.0) as today_eur_net
            FROM streamers s
            LEFT JOIN gift_events g ON g.streamer_id = s.id AND (? IS NULL OR g.created_at >= ?)
            GROUP BY s.id
            ORDER BY s.is_live DESC, today_coins DESC, s.username ASC
            """,
            (cutoff, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]
