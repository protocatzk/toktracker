"""
TokTracker - Analyse und Import einer bestehenden SQLite-Datenbank.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import get_db


def inspect_sqlite_database(sqlite_file_path: str) -> Dict[str, Any]:
    """
    Untersucht eine SQLite-Datei und liefert Informationen über Tabellen,
    Zeilenzahlen und Datengröße zurück.
    """
    if not os.path.exists(sqlite_file_path):
        raise FileNotFoundError(f"SQLite-Datei nicht gefunden: {sqlite_file_path}")

    file_size_bytes = os.path.getsize(sqlite_file_path)
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    src = sqlite3.connect(sqlite_file_path)
    src.row_factory = sqlite3.Row
    try:
        cur = src.cursor()
        existing_tables = [
            r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]

        table_counts: Dict[str, int] = {}
        for tbl in ["settings", "streamers", "stream_sessions", "gift_events", "telegram_users", "tiktok_battles"]:
            if tbl in existing_tables:
                try:
                    c = cur.execute(f"SELECT COUNT(*) FROM `{tbl}`").fetchone()[0]
                    table_counts[tbl] = int(c)
                except Exception:
                    table_counts[tbl] = 0
            else:
                table_counts[tbl] = 0

        # Ermittle gefundene Streamer
        streamer_names: List[str] = []
        if "streamers" in existing_tables:
            try:
                s_rows = cur.execute("SELECT username FROM streamers ORDER BY username ASC LIMIT 30").fetchall()
                streamer_names = [r["username"] for r in s_rows]
            except Exception:
                pass

        return {
            "file_path": sqlite_file_path,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": file_size_mb,
            "tables": existing_tables,
            "table_counts": table_counts,
            "streamer_samples": streamer_names,
            "total_records": sum(table_counts.values()),
        }
    finally:
        src.close()


def import_from_sqlite_database(
    sqlite_file_path: str,
    import_tables: Optional[List[str]] = None,
    mode: str = "merge",  # "merge" (REPLACE/INSERT IGNORE) oder "clean" (vorher leeren)
) -> Dict[str, Any]:
    """
    Liest Daten aus einer SQLite-Datei aus und schreibt sie in die aktuell aktive
    Ziel-Datenbank (egal ob SQLite oder MySQL / MariaDB).
    """
    if not os.path.exists(sqlite_file_path):
        raise FileNotFoundError(f"SQLite-Datei nicht gefunden: {sqlite_file_path}")

    all_supported = ["settings", "streamers", "stream_sessions", "gift_events", "telegram_users", "tiktok_battles"]
    target_tables = [t for t in (import_tables or all_supported) if t in all_supported]

    src = sqlite3.connect(sqlite_file_path)
    src.row_factory = sqlite3.Row

    imported_stats: Dict[str, int] = {t: 0 for t in target_tables}
    errors: List[str] = []

    try:
        cur_src = src.cursor()

        with get_db() as dst:
            # 1. Falls "clean", bereinige die gewählten Tabellen (in umgekehrter Fremdschlüssel-Reihenfolge)
            if mode == "clean":
                clean_order = ["gift_events", "tiktok_battles", "stream_sessions", "streamers", "telegram_users", "settings"]
                for tbl in clean_order:
                    if tbl in target_tables:
                        try:
                            dst.execute(f"DELETE FROM `{tbl}`")
                        except Exception as e:
                            errors.append(f"Fehler beim Leeren von `{tbl}`: {e}")

            # 2. SETTINGS
            if "settings" in target_tables:
                try:
                    s_rows = cur_src.execute("SELECT `key`, `value` FROM settings").fetchall()
                    for r in s_rows:
                        dst.execute(
                            "INSERT OR REPLACE INTO settings (`key`, `value`) VALUES (?, ?)",
                            (r["key"], r["value"]),
                        )
                    imported_stats["settings"] = len(s_rows)
                except Exception as e:
                    errors.append(f"Settings Import: {e}")

            # 3. STREAMERS
            if "streamers" in target_tables:
                try:
                    streamer_rows = cur_src.execute("SELECT * FROM streamers ORDER BY id ASC").fetchall()
                    for r in streamer_rows:
                        d = dict(r)
                        dst.execute(
                            """
                            INSERT OR REPLACE INTO streamers (
                                id, username, display_name, avatar_url, room_id,
                                follower_count, is_live, is_tracking, auto_monitor,
                                current_viewers, last_error, created_at, last_seen_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                d["id"],
                                d["username"],
                                d.get("display_name") or d["username"],
                                d.get("avatar_url") or "",
                                d.get("room_id") or "",
                                int(d.get("follower_count") or 0),
                                int(d.get("is_live") or 0),
                                int(d.get("is_tracking") or 0),
                                int(d.get("auto_monitor") or 0),
                                int(d.get("current_viewers") or 0),
                                d.get("last_error") or "",
                                d["created_at"],
                                d.get("last_seen_at") or d["created_at"],
                            ),
                        )
                    imported_stats["streamers"] = len(streamer_rows)
                except Exception as e:
                    errors.append(f"Streamers Import: {e}")

            # 4. STREAM SESSIONS
            if "stream_sessions" in target_tables:
                try:
                    session_rows = cur_src.execute("SELECT * FROM stream_sessions ORDER BY id ASC").fetchall()
                    for r in session_rows:
                        d = dict(r)
                        dst.execute(
                            """
                            INSERT OR REPLACE INTO stream_sessions (
                                id, streamer_id, room_id, title, started_at,
                                ended_at, peak_viewers, last_fan_tickets, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                d["id"],
                                d["streamer_id"],
                                d.get("room_id") or "",
                                d.get("title") or "",
                                d["started_at"],
                                d.get("ended_at"),
                                int(d.get("peak_viewers") or 0),
                                int(d.get("last_fan_tickets") or 0),
                                d.get("status") or "ended",
                            ),
                        )
                    imported_stats["stream_sessions"] = len(session_rows)
                except Exception as e:
                    errors.append(f"Sessions Import: {e}")

            # 5. GIFT EVENTS
            if "gift_events" in target_tables:
                try:
                    gift_rows = cur_src.execute("SELECT * FROM gift_events ORDER BY id ASC").fetchall()
                    for r in gift_rows:
                        d = dict(r)
                        dst.execute(
                            """
                            INSERT OR IGNORE INTO gift_events (
                                id, streamer_id, session_id, event_uid,
                                sender_user_id, sender_username, sender_nickname, is_super_fan,
                                gift_id, gift_name, gift_icon_url,
                                diamond_count, repeat_count, combo_count, group_id, room_fan_tickets,
                                total_coins, usd_net, eur_net, usd_gross, eur_gross,
                                source, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                d["id"],
                                d["streamer_id"],
                                d.get("session_id"),
                                d.get("event_uid"),
                                d.get("sender_user_id") or "",
                                d["sender_username"],
                                d.get("sender_nickname") or d["sender_username"],
                                int(d.get("is_super_fan") or 0),
                                int(d.get("gift_id") or 0),
                                d["gift_name"],
                                d.get("gift_icon_url") or "",
                                int(d["diamond_count"]),
                                int(d["repeat_count"]),
                                int(d.get("combo_count") or 1),
                                d.get("group_id") or "",
                                int(d.get("room_fan_tickets") or 0),
                                int(d["total_coins"]),
                                float(d["usd_net"]),
                                float(d["eur_net"]),
                                float(d["usd_gross"]),
                                float(d["eur_gross"]),
                                d.get("source") or "tiktoklive",
                                d["created_at"],
                            ),
                        )
                    imported_stats["gift_events"] = len(gift_rows)
                except Exception as e:
                    errors.append(f"Gifts Import: {e}")

            # 6. TELEGRAM USERS
            if "telegram_users" in target_tables:
                try:
                    tg_rows = cur_src.execute("SELECT * FROM telegram_users ORDER BY id ASC").fetchall()
                    for r in tg_rows:
                        d = dict(r)
                        dst.execute(
                            """
                            INSERT OR REPLACE INTO telegram_users (
                                id, telegram_id, username, first_name,
                                role, is_allowed, note, created_at, last_seen_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                d["id"],
                                d.get("telegram_id"),
                                d.get("username") or "",
                                d.get("first_name") or "",
                                d.get("role") or "user",
                                int(d.get("is_allowed") or 0),
                                d.get("note") or "",
                                d["created_at"],
                                d.get("last_seen_at") or d["created_at"],
                            ),
                        )
                    imported_stats["telegram_users"] = len(tg_rows)
                except Exception as e:
                    errors.append(f"Telegram Users Import: {e}")

            # 7. TIKTOK BATTLES
            if "tiktok_battles" in target_tables:
                try:
                    has_battles_table = cur_src.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tiktok_battles'"
                    ).fetchone()[0] > 0
                    if has_battles_table:
                        battle_rows = cur_src.execute("SELECT * FROM tiktok_battles ORDER BY id ASC").fetchall()
                        for r in battle_rows:
                            d = dict(r)
                            dst.execute(
                                """
                                INSERT OR REPLACE INTO tiktok_battles (
                                    id, streamer_id, session_id, battle_id,
                                    opponent_user_id, opponent_username, opponent_display_name, opponent_avatar_url,
                                    started_at, ended_at, duration_seconds,
                                    streamer_score, opponent_score, result,
                                    streamer_mvp_name, streamer_mvp_score, streamer_mvp_avatar,
                                    opponent_mvp_name, opponent_mvp_score, opponent_mvp_avatar,
                                    coins_earned, usd_net, eur_net, usd_gross, eur_gross,
                                    status, raw_data_json, created_at,
                                    battle_mode,
                                    teammate_user_id, teammate_username, teammate_display_name, teammate_avatar_url, teammate_score,
                                    opponent2_user_id, opponent2_username, opponent2_display_name, opponent2_avatar_url, opponent2_score,
                                    opponent3_user_id, opponent3_username, opponent3_display_name, opponent3_avatar_url, opponent3_score,
                                    streamer_rank
                                ) VALUES (
                                    ?, ?, ?, ?,
                                    ?, ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?, ?, ?,
                                    ?, ?, ?,
                                    ?,
                                    ?, ?, ?, ?, ?,
                                    ?, ?, ?, ?, ?,
                                    ?, ?, ?, ?, ?,
                                    ?
                                )
                                """,
                                (
                                    d["id"],
                                    d["streamer_id"],
                                    d.get("session_id"),
                                    d.get("battle_id") or "",
                                    d.get("opponent_user_id") or "",
                                    d.get("opponent_username") or "",
                                    d.get("opponent_display_name") or "",
                                    d.get("opponent_avatar_url") or "",
                                    d["started_at"],
                                    d.get("ended_at"),
                                    int(d.get("duration_seconds") or 300),
                                    int(d.get("streamer_score") or 0),
                                    int(d.get("opponent_score") or 0),
                                    d.get("result") or "ONGOING",
                                    d.get("streamer_mvp_name") or "",
                                    int(d.get("streamer_mvp_score") or 0),
                                    d.get("streamer_mvp_avatar") or "",
                                    d.get("opponent_mvp_name") or "",
                                    int(d.get("opponent_mvp_score") or 0),
                                    d.get("opponent_mvp_avatar") or "",
                                    int(d.get("coins_earned") or 0),
                                    float(d.get("usd_net") or 0.0),
                                    float(d.get("eur_net") or 0.0),
                                    float(d.get("usd_gross") or 0.0),
                                    float(d.get("eur_gross") or 0.0),
                                    d.get("status") or "active",
                                    d.get("raw_data_json") or "",
                                    d["created_at"],
                                    d.get("battle_mode") or "1v1",
                                    d.get("teammate_user_id") or "",
                                    d.get("teammate_username") or "",
                                    d.get("teammate_display_name") or "",
                                    d.get("teammate_avatar_url") or "",
                                    int(d.get("teammate_score") or 0),
                                    d.get("opponent2_user_id") or "",
                                    d.get("opponent2_username") or "",
                                    d.get("opponent2_display_name") or "",
                                    d.get("opponent2_avatar_url") or "",
                                    int(d.get("opponent2_score") or 0),
                                    d.get("opponent3_user_id") or "",
                                    d.get("opponent3_username") or "",
                                    d.get("opponent3_display_name") or "",
                                    d.get("opponent3_avatar_url") or "",
                                    int(d.get("opponent3_score") or 0),
                                    int(d.get("streamer_rank") or 0),
                                ),
                            )
                        imported_stats["tiktok_battles"] = len(battle_rows)
                except Exception as e:
                    errors.append(f"Battles Import: {e}")

        return {
            "ok": len(errors) == 0,
            "mode": mode,
            "source_file": sqlite_file_path,
            "imported_counts": imported_stats,
            "total_imported": sum(imported_stats.values()),
            "errors": errors,
        }
    finally:
        src.close()
