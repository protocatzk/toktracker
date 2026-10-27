"""
TokTracker - Dashboard-, Streamer- und Gesamtanalytics (mit Kurzzeit-Cache).
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import _get_period_cutoff, get_db
from shared.db.settings import get_settings
from shared.db.users import list_telegram_users

_overview_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


_overview_cache_lock = threading.Lock()


_OVERVIEW_CACHE_TTL = 3.5  # 3.5s TTL verhindert Doppel-Berechnungen bei raschen/parallelen Polls


def invalidate_overview_cache() -> None:
    with _overview_cache_lock:
        _overview_cache.clear()


def get_dashboard_overview(period: str = "all", force_refresh: bool = False) -> Dict[str, Any]:
    now = time.monotonic()
    if not force_refresh:
        with _overview_cache_lock:
            cached = _overview_cache.get(period)
            if cached and (now - cached[0]) < _OVERVIEW_CACHE_TTL:
                return cached[1].copy()

    cutoff = _get_period_cutoff(period)
    cfg = get_settings()

    with get_db() as conn:
        if cutoff:
            streamer_rows = conn.execute(
                """
                SELECT
                    s.*,
                    COALESCE(SUM(g.total_coins), 0) AS total_coins,
                    COUNT(g.id) AS gift_events_count,
                    COALESCE(SUM(g.repeat_count), 0) AS total_gifts_sent,
                    COUNT(DISTINCT g.sender_username) AS unique_gifters
                FROM streamers s
                LEFT JOIN gift_events g
                    ON g.streamer_id = s.id AND g.created_at >= ?
                GROUP BY s.id
                ORDER BY total_coins DESC, s.username ASC
                """,
                (cutoff,),
            ).fetchall()
        else:
            streamer_rows = conn.execute(
                """
                SELECT
                    s.*,
                    COALESCE(SUM(g.total_coins), 0) AS total_coins,
                    COUNT(g.id) AS gift_events_count,
                    COALESCE(SUM(g.repeat_count), 0) AS total_gifts_sent,
                    COUNT(DISTINCT g.sender_username) AS unique_gifters
                FROM streamers s
                LEFT JOIN gift_events g
                    ON g.streamer_id = s.id
                GROUP BY s.id
                ORDER BY total_coins DESC, s.username ASC
                """
            ).fetchall()

        # Batch 1: Alle aktiven Sessions in einer einzigen Abfrage erfassen
        active_sess_rows = conn.execute(
            """
            SELECT id, streamer_id, room_id, started_at, peak_viewers, last_fan_tickets
            FROM stream_sessions
            WHERE status = 'active'
            ORDER BY id DESC
            """
        ).fetchall()
        active_sess_by_streamer: Dict[int, Dict[str, Any]] = {}
        for as_row in active_sess_rows:
            sid = as_row["streamer_id"]
            if sid not in active_sess_by_streamer:
                active_sess_by_streamer[sid] = dict(as_row)

        # Batch 2: Top-Gifts pro Streamer in einem aggregierten Durchlauf erfassen
        if cutoff:
            gift_sum_rows = conn.execute(
                """
                SELECT streamer_id, gift_name, SUM(total_coins) AS coins, SUM(repeat_count) AS count
                FROM gift_events
                WHERE created_at >= ?
                GROUP BY streamer_id, gift_name
                ORDER BY coins DESC
                """,
                (cutoff,),
            ).fetchall()
        else:
            gift_sum_rows = conn.execute(
                """
                SELECT streamer_id, gift_name, SUM(total_coins) AS coins, SUM(repeat_count) AS count
                FROM gift_events
                GROUP BY streamer_id, gift_name
                ORDER BY coins DESC
                """
            ).fetchall()

        top_gift_by_streamer: Dict[int, Dict[str, Any]] = {}
        for grow in gift_sum_rows:
            sid = grow["streamer_id"]
            if sid not in top_gift_by_streamer:
                top_gift_by_streamer[sid] = {
                    "gift_name": grow["gift_name"],
                    "coins": int(grow["coins"] or 0),
                    "count": int(grow["count"] or 0),
                }

        # Batch 3: Top-Gifter pro Streamer in einem aggregierten Durchlauf erfassen
        if cutoff:
            gifter_sum_rows = conn.execute(
                """
                SELECT streamer_id, sender_username, MAX(sender_nickname) AS sender_nickname, SUM(total_coins) AS coins
                FROM gift_events
                WHERE created_at >= ?
                GROUP BY streamer_id, sender_username
                ORDER BY coins DESC
                """,
                (cutoff,),
            ).fetchall()
        else:
            gifter_sum_rows = conn.execute(
                """
                SELECT streamer_id, sender_username, MAX(sender_nickname) AS sender_nickname, SUM(total_coins) AS coins
                FROM gift_events
                GROUP BY streamer_id, sender_username
                ORDER BY coins DESC
                """
            ).fetchall()

        top_gifter_by_streamer: Dict[int, Dict[str, Any]] = {}
        for grow in gifter_sum_rows:
            sid = grow["streamer_id"]
            if sid not in top_gifter_by_streamer:
                top_gifter_by_streamer[sid] = {
                    "sender_username": grow["sender_username"],
                    "sender_nickname": grow["sender_nickname"] or grow["sender_username"],
                    "coins": int(grow["coins"] or 0),
                }

        streamers: List[Dict[str, Any]] = []
        totals = {
            "streamer_count": len(streamer_rows),
            "live_count": 0,
            "tracking_count": 0,
            "total_coins": 0,
            "usd_net": 0.0,
            "eur_net": 0.0,
            "usd_gross": 0.0,
            "eur_gross": 0.0,
            "total_gifts_sent": 0,
            "gift_events_count": 0,
        }

        for r in streamer_rows:
            d = dict(r)
            coins = int(d["total_coins"] or 0)
            d["usd_net"] = round(coins * cfg["usd_per_diamond"], 2)
            d["eur_net"] = round(d["usd_net"] * cfg["usd_to_eur_rate"], 2)
            d["usd_gross"] = round(coins * cfg["gross_usd_per_coin"], 2)
            d["eur_gross"] = round(d["usd_gross"] * cfg["usd_to_eur_rate"], 2)

            sid = d["id"]
            d["top_gift"] = top_gift_by_streamer.get(sid)
            d["top_gifter"] = top_gifter_by_streamer.get(sid)
            d["active_session"] = active_sess_by_streamer.get(sid)

            streamers.append(d)

            totals["live_count"] += int(bool(d["is_live"]))
            totals["tracking_count"] += int(bool(d["is_tracking"]))
            totals["total_coins"] += coins
            totals["usd_net"] = round(totals["usd_net"] + d["usd_net"], 2)
            totals["eur_net"] = round(totals["eur_net"] + d["eur_net"], 2)
            totals["usd_gross"] = round(totals["usd_gross"] + d["usd_gross"], 2)
            totals["eur_gross"] = round(totals["eur_gross"] + d["eur_gross"], 2)
            totals["total_gifts_sent"] += int(d["total_gifts_sent"] or 0)
            totals["gift_events_count"] += int(d["gift_events_count"] or 0)

        if cutoff:
            recent_rows = conn.execute(
                """
                SELECT g.*, s.username AS streamer_username, s.display_name AS streamer_display_name
                FROM gift_events g
                JOIN streamers s ON s.id = g.streamer_id
                WHERE g.created_at >= ?
                ORDER BY g.created_at DESC, g.id DESC
                LIMIT 50
                """,
                (cutoff,),
            ).fetchall()
        else:
            recent_rows = conn.execute(
                """
                SELECT g.*, s.username AS streamer_username, s.display_name AS streamer_display_name
                FROM gift_events g
                JOIN streamers s ON s.id = g.streamer_id
                ORDER BY g.created_at DESC, g.id DESC
                LIMIT 50
                """
            ).fetchall()

        recent_gifts = []
        for r in recent_rows:
            gd = dict(r)
            coins = int(gd["total_coins"] or 0)
            gd["usd_net"] = round(coins * cfg["usd_per_diamond"], 2)
            gd["eur_net"] = round(gd["usd_net"] * cfg["usd_to_eur_rate"], 2)
            recent_gifts.append(gd)

    res = {
        "settings": cfg,
        "period": period,
        "totals": totals,
        "streamers": streamers,
        "recent_gifts": recent_gifts,
        "telegram_users": list_telegram_users(),
    }
    with _overview_cache_lock:
        _overview_cache[period] = (now, res)
    return res


def get_streamer_detail(streamer_id: int, period: str = "all") -> Optional[Dict[str, Any]]:
    cutoff = _get_period_cutoff(period)
    cfg = get_settings()

    with get_db() as conn:
        streamer = conn.execute(
            "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
        ).fetchone()
        if not streamer:
            return None

        s_dict = dict(streamer)

        gift_breakdown = conn.execute(
            """
            SELECT
                MAX(gift_id) AS gift_id,
                gift_name,
                diamond_count,
                SUM(repeat_count) AS total_quantity,
                SUM(total_coins) AS total_coins,
                COUNT(id) AS events_count
            FROM gift_events
            WHERE streamer_id = ? AND (? IS NULL OR created_at >= ?)
            GROUP BY gift_name, diamond_count
            ORDER BY total_coins DESC
            """,
            (streamer_id, cutoff, cutoff),
        ).fetchall()

        gifts_list = []
        total_coins = 0
        for g in gift_breakdown:
            gd = dict(g)
            c = int(gd["total_coins"] or 0)
            total_coins += c
            gd["usd_net"] = round(c * cfg["usd_per_diamond"], 2)
            gd["eur_net"] = round(gd["usd_net"] * cfg["usd_to_eur_rate"], 2)
            gifts_list.append(gd)

        top_gifters_rows = conn.execute(
            """
            SELECT
                sender_username,
                MAX(sender_nickname) AS sender_nickname,
                MAX(is_super_fan) AS is_super_fan,
                SUM(total_coins) AS total_coins,
                SUM(repeat_count) AS gifts_sent,
                COUNT(id) AS transactions
            FROM gift_events
            WHERE streamer_id = ? AND (? IS NULL OR created_at >= ?)
            GROUP BY sender_username
            ORDER BY total_coins DESC
            LIMIT 15
            """,
            (streamer_id, cutoff, cutoff),
        ).fetchall()

        top_gifters = []
        for tg in top_gifters_rows:
            tgd = dict(tg)
            c = int(tgd["total_coins"] or 0)
            tgd["usd_net"] = round(c * cfg["usd_per_diamond"], 2)
            tgd["eur_net"] = round(tgd["usd_net"] * cfg["usd_to_eur_rate"], 2)
            top_gifters.append(tgd)

        sessions_rows = conn.execute(
            """
            SELECT
                ss.*,
                COALESCE(SUM(g.total_coins), 0) AS session_coins,
                COUNT(g.id) AS gift_events
            FROM stream_sessions ss
            LEFT JOIN gift_events g ON g.session_id = ss.id
            WHERE ss.streamer_id = ?
            GROUP BY ss.id
            ORDER BY ss.id DESC
            LIMIT 20
            """,
            (streamer_id,),
        ).fetchall()

        sessions = []
        for sr in sessions_rows:
            sd = dict(sr)
            c = int(sd["session_coins"] or 0)
            sd["usd_net"] = round(c * cfg["usd_per_diamond"], 2)
            sd["eur_net"] = round(sd["usd_net"] * cfg["usd_to_eur_rate"], 2)
            sessions.append(sd)

        recent_rows = conn.execute(
            """
            SELECT *
            FROM gift_events
            WHERE streamer_id = ? AND (? IS NULL OR created_at >= ?)
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """,
            (streamer_id, cutoff, cutoff),
        ).fetchall()

        recent_events = []
        for r in recent_rows:
            rd = dict(r)
            c = int(rd["total_coins"] or 0)
            rd["usd_net"] = round(c * cfg["usd_per_diamond"], 2)
            rd["eur_net"] = round(rd["usd_net"] * cfg["usd_to_eur_rate"], 2)
            recent_events.append(rd)

        usd_net = round(total_coins * cfg["usd_per_diamond"], 2)
        eur_net = round(usd_net * cfg["usd_to_eur_rate"], 2)
        usd_gross = round(total_coins * cfg["gross_usd_per_coin"], 2)
        eur_gross = round(usd_gross * cfg["usd_to_eur_rate"], 2)

        return {
            "streamer": s_dict,
            "summary": {
                "total_coins": total_coins,
                "usd_net": usd_net,
                "eur_net": eur_net,
                "usd_gross": usd_gross,
                "eur_gross": eur_gross,
            },
            "gift_breakdown": gifts_list,
            "top_gifters": top_gifters,
            "sessions": sessions,
            "recent_events": recent_events,
        }


def get_analytics_data(streamer_id: Optional[int] = None, period: str = "all") -> Dict[str, Any]:
    """
    Liefert detaillierte Analytics und aggregierte Kennzahlen für Charts:
    - Gesamt-KPIs (Netto/Brutto, Coins, Gifts, Unique Gifters, Averages)
    - Whale-Konzentrationsmetriken (Top 1, Top 3, Top 5 Spenderanteil)
    - Chronologischer Einnahmen-Verlauf (stündlich bei 24h/today, täglich bei 7d/30d/all)
    - Multi-Streamer-Timeline-Vergleich für Top-Streamer (wenn kein Einzelstreamer gewählt)
    - Tageszeit-Aktivitätsmuster (00:00 - 23:00 Uhr)
    - Top Geschenke Verteilung (Doughnut/Pie & Tabelle)
    - Top Spender & Supporter Ranking (Bar-Chart & Tabelle)
    - Streamer-Vergleich (Ranking & Einnahmenverteilung)
    - Stream-Sessions Historie mit berechneter Dauer und Hourly Run-Rate (Coins/h)
    """
    cutoff = _get_period_cutoff(period)
    cfg = get_settings()

    with get_db() as conn:
        # 1. Streamer-Details, falls ein spezifischer Streamer gewählt wurde
        selected_streamer = None
        if streamer_id:
            s_row = conn.execute(
                "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
            ).fetchone()
            if s_row:
                selected_streamer = dict(s_row)
            else:
                streamer_id = None

        # 2. Aggregierte Gesamt-Metriken im gewählten Zeitraum & Scope
        agg_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_coins), 0) AS total_coins,
                COALESCE(SUM(repeat_count), 0) AS total_gifts_sent,
                COUNT(id) AS gift_events_count,
                COUNT(DISTINCT sender_username) AS unique_gifters
            FROM gift_events
            WHERE (? IS NULL OR streamer_id = ?)
              AND (? IS NULL OR created_at >= ?)
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchone()

        total_coins = int(agg_row["total_coins"] or 0)
        total_gifts = int(agg_row["total_gifts_sent"] or 0)
        gift_events_cnt = int(agg_row["gift_events_count"] or 0)
        unique_gifters = int(agg_row["unique_gifters"] or 0)

        usd_net = round(total_coins * cfg["usd_per_diamond"], 2)
        eur_net = round(usd_net * cfg["usd_to_eur_rate"], 2)
        usd_gross = round(total_coins * cfg["gross_usd_per_coin"], 2)
        eur_gross = round(usd_gross * cfg["usd_to_eur_rate"], 2)

        avg_coins_per_gift = round(total_coins / total_gifts, 1) if total_gifts > 0 else 0.0
        avg_coins_per_gifter = round(total_coins / unique_gifters, 1) if unique_gifters > 0 else 0.0
        avg_eur_per_gifter = round(eur_net / unique_gifters, 2) if unique_gifters > 0 else 0.0

        # 3. Top Spender & Supporter-Ranking sowie Whale-Konzentration
        top_gifters_rows = conn.execute(
            """
            SELECT
                sender_username,
                MAX(sender_nickname) AS sender_nickname,
                MAX(is_super_fan) AS is_super_fan,
                SUM(total_coins) AS total_coins,
                SUM(repeat_count) AS gifts_sent,
                COUNT(id) AS transactions
            FROM gift_events
            WHERE (? IS NULL OR streamer_id = ?)
              AND (? IS NULL OR created_at >= ?)
            GROUP BY sender_username
            ORDER BY total_coins DESC
            LIMIT 25
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchall()

        top_gifters = []
        top1_coins = 0
        top3_coins = 0
        top5_coins = 0
        for idx, tg in enumerate(top_gifters_rows):
            c = int(tg["total_coins"] or 0)
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
            pct = round((c / total_coins * 100), 1) if total_coins > 0 else 0.0
            if idx == 0:
                top1_coins += c
            if idx < 3:
                top3_coins += c
            if idx < 5:
                top5_coins += c
            top_gifters.append({
                "rank": idx + 1,
                "sender_username": tg["sender_username"],
                "sender_nickname": tg["sender_nickname"] or tg["sender_username"],
                "is_super_fan": bool(tg["is_super_fan"]),
                "total_coins": c,
                "usd_net": u_net,
                "eur_net": e_net,
                "gifts_sent": int(tg["gifts_sent"] or 0),
                "transactions": int(tg["transactions"] or 0),
                "pct_of_total": pct,
            })

        whale_share_top1 = round((top1_coins / total_coins * 100), 1) if total_coins > 0 else 0.0
        whale_share_top3 = round((top3_coins / total_coins * 100), 1) if total_coins > 0 else 0.0
        whale_share_top5 = round((top5_coins / total_coins * 100), 1) if total_coins > 0 else 0.0

        # 4. Top Geschenke-Aufschlüsselung
        top_gifts_rows = conn.execute(
            """
            SELECT
                MAX(gift_id) AS gift_id,
                gift_name,
                diamond_count,
                SUM(repeat_count) AS total_quantity,
                SUM(total_coins) AS total_coins,
                COUNT(id) AS events_count
            FROM gift_events
            WHERE (? IS NULL OR streamer_id = ?)
              AND (? IS NULL OR created_at >= ?)
            GROUP BY gift_name, diamond_count
            ORDER BY total_coins DESC
            LIMIT 20
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchall()

        top_gifts = []
        for g in top_gifts_rows:
            c = int(g["total_coins"] or 0)
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
            pct = round((c / total_coins * 100), 1) if total_coins > 0 else 0.0
            top_gifts.append({
                "gift_id": g["gift_id"],
                "gift_name": g["gift_name"],
                "diamond_count": int(g["diamond_count"] or 0),
                "total_quantity": int(g["total_quantity"] or 0),
                "total_coins": c,
                "usd_net": u_net,
                "eur_net": e_net,
                "events_count": int(g["events_count"] or 0),
                "pct_of_total": pct,
            })

        # 5. Tageszeit-Aktivitätsmuster (00:00 - 23:00 Uhr)
        tod_rows = conn.execute(
            """
            SELECT
                CAST(SUBSTR(created_at, 12, 2) AS INTEGER) AS hour_of_day,
                SUM(total_coins) AS coins,
                COUNT(id) AS events_count
            FROM gift_events
            WHERE (? IS NULL OR streamer_id = ?)
              AND (? IS NULL OR created_at >= ?)
            GROUP BY CAST(SUBSTR(created_at, 12, 2) AS INTEGER)
            ORDER BY hour_of_day ASC
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchall()

        tod_map = {int(r["hour_of_day"]): (int(r["coins"] or 0), int(r["events_count"] or 0)) for r in tod_rows}
        time_of_day = []
        for h in range(24):
            c, ev = tod_map.get(h, (0, 0))
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
            time_of_day.append({
                "hour": h,
                "label": f"{h:02d}:00",
                "coins": c,
                "eur_net": e_net,
                "events_count": ev,
            })

        # 6. Chronologischer Einnahmen-Verlauf (Timeline)
        is_hourly = period in ("24h", "today")
        substr_len = 13 if is_hourly else 10

        timeline_rows = conn.execute(
            f"""
            SELECT
                SUBSTR(created_at, 1, {substr_len}) AS bucket,
                COALESCE(SUM(total_coins), 0) AS coins,
                COUNT(id) AS events_count,
                COUNT(DISTINCT sender_username) AS unique_gifters
            FROM gift_events
            WHERE (? IS NULL OR streamer_id = ?)
              AND (? IS NULL OR created_at >= ?)
            GROUP BY SUBSTR(created_at, 1, {substr_len})
            ORDER BY bucket ASC
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchall()

        timeline = []
        for tr in timeline_rows:
            b = tr["bucket"]
            c = int(tr["coins"] or 0)
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
            u_gross = round(c * cfg["gross_usd_per_coin"], 2)
            e_gross = round(u_gross * cfg["usd_to_eur_rate"], 2)
            ev = int(tr["events_count"] or 0)
            ug = int(tr["unique_gifters"] or 0)
            avg_coins = round(c / ev, 1) if ev > 0 else 0.0
            avg_eur = round(e_net / ug, 2) if ug > 0 else 0.0

            if is_hourly:
                parts = b.replace("T", " ").split(" ")
                time_part = f"{parts[1]}:00" if len(parts) > 1 else b
                label = time_part if period == "today" else f"{parts[0][5:]} {time_part}"
            else:
                label = f"{b[8:10]}.{b[5:7]}." if len(b) >= 10 else b

            timeline.append({
                "bucket": b,
                "label": label,
                "coins": c,
                "eur_net": e_net,
                "usd_net": u_net,
                "eur_gross": e_gross,
                "usd_gross": u_gross,
                "events_count": ev,
                "unique_gifters": ug,
                "avg_coins_per_gift": avg_coins,
                "avg_eur_per_gifter": avg_eur,
            })

        # 7. Streamer Ranking & Vergleich
        streamer_ranking_rows = conn.execute(
            """
            SELECT
                s.id,
                s.username,
                s.display_name,
                s.avatar_url,
                s.follower_count,
                s.current_viewers,
                s.is_live,
                s.is_tracking,
                COALESCE(SUM(g.total_coins), 0) AS total_coins,
                COUNT(g.id) AS gift_events_count,
                COALESCE(SUM(g.repeat_count), 0) AS total_gifts_sent,
                COUNT(DISTINCT g.sender_username) AS unique_gifters
            FROM streamers s
            LEFT JOIN gift_events g
                ON g.streamer_id = s.id AND (? IS NULL OR g.created_at >= ?)
            GROUP BY s.id
            ORDER BY total_coins DESC, s.username ASC
            """,
            (cutoff, cutoff),
        ).fetchall()

        streamers_ranking: List[Dict[str, Any]] = []
        top_streamer_ids: List[int] = []
        for sr in streamer_ranking_rows:
            c = int(sr["total_coins"] or 0)
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
            pct = round((c / total_coins * 100), 1) if (total_coins > 0 and not streamer_id) else (100.0 if c > 0 else 0.0)
            streamers_ranking.append({
                "id": sr["id"],
                "username": sr["username"],
                "display_name": sr["display_name"] or sr["username"],
                "avatar_url": sr["avatar_url"] or "",
                "follower_count": int(sr["follower_count"] or 0),
                "current_viewers": int(sr["current_viewers"] or 0),
                "is_live": bool(sr["is_live"]),
                "is_tracking": bool(sr["is_tracking"]),
                "total_coins": c,
                "eur_net": e_net,
                "usd_net": u_net,
                "gift_events_count": int(sr["gift_events_count"] or 0),
                "total_gifts_sent": int(sr["total_gifts_sent"] or 0),
                "unique_gifters": int(sr["unique_gifters"] or 0),
                "pct_of_total": pct,
            })
            if c > 0 and len(top_streamer_ids) < 5:
                top_streamer_ids.append(sr["id"])

        # 8. Multi-Streamer-Timeline-Vergleich für die Top 5 Streamer (wenn Gesamtansicht)
        multi_streamer_datasets = []
        if not streamer_id and top_streamer_ids and timeline:
            buckets = [t["bucket"] for t in timeline]
            for sid in top_streamer_ids:
                s_meta = next((s for s in streamers_ranking if s["id"] == sid), None)
                if not s_meta:
                    continue
                s_rows = conn.execute(
                    f"""
                    SELECT
                        SUBSTR(created_at, 1, {substr_len}) AS bucket,
                        COALESCE(SUM(total_coins), 0) AS coins
                    FROM gift_events
                    WHERE streamer_id = ? AND (? IS NULL OR created_at >= ?)
                    GROUP BY SUBSTR(created_at, 1, {substr_len})
                    """,
                    (sid, cutoff, cutoff),
                ).fetchall()
                s_map = {r["bucket"]: int(r["coins"] or 0) for r in s_rows}
                series_data = [s_map.get(b, 0) for b in buckets]
                multi_streamer_datasets.append({
                    "streamer_id": sid,
                    "username": s_meta["username"],
                    "display_name": s_meta["display_name"],
                    "data": series_data,
                })

        # 9. Aufgezeichnete Sessions & Hourly Run-Rates
        sessions_rows = conn.execute(
            """
            SELECT
                ss.*,
                s.username AS streamer_username,
                s.display_name AS streamer_display_name,
                COALESCE(SUM(g.total_coins), 0) AS session_coins,
                COUNT(g.id) AS session_gifts
            FROM stream_sessions ss
            JOIN streamers s ON s.id = ss.streamer_id
            LEFT JOIN gift_events g ON g.session_id = ss.id
            WHERE (? IS NULL OR ss.streamer_id = ?)
              AND (? IS NULL OR ss.started_at >= ?)
            GROUP BY ss.id
            ORDER BY ss.started_at DESC, ss.id DESC
            LIMIT 25
            """,
            (streamer_id, streamer_id, cutoff, cutoff),
        ).fetchall()

        now_dt = datetime.now()
        sessions = []
        total_session_minutes = 0
        for sr in sessions_rows:
            c = int(sr["session_coins"] or 0)
            u_net = round(c * cfg["usd_per_diamond"], 2)
            e_net = round(u_net * cfg["usd_to_eur_rate"], 2)

            start_str = sr["started_at"]
            end_str = sr["ended_at"]
            duration_mins = 0
            try:
                s_dt = datetime.fromisoformat(start_str)
                e_dt = datetime.fromisoformat(end_str) if end_str else now_dt
                duration_mins = max(1, int(round((e_dt - s_dt).total_seconds() / 60)))
            except Exception:
                duration_mins = 0

            total_session_minutes += duration_mins
            coins_per_hour = round(c / (duration_mins / 60)) if duration_mins > 0 else c

            sessions.append({
                "id": sr["id"],
                "streamer_id": sr["streamer_id"],
                "streamer_username": sr["streamer_username"],
                "streamer_display_name": sr["streamer_display_name"] or sr["streamer_username"],
                "room_id": sr["room_id"],
                "title": sr["title"],
                "started_at": sr["started_at"],
                "ended_at": sr["ended_at"],
                "duration_minutes": duration_mins,
                "peak_viewers": int(sr["peak_viewers"] or 0),
                "status": sr["status"],
                "session_coins": c,
                "eur_net": e_net,
                "usd_net": u_net,
                "session_gifts": int(sr["session_gifts"] or 0),
                "coins_per_hour": coins_per_hour,
            })

    return {
        "period": period,
        "selected_streamer_id": streamer_id,
        "selected_streamer": selected_streamer,
        "totals": {
            "total_coins": total_coins,
            "eur_net": eur_net,
            "usd_net": usd_net,
            "eur_gross": eur_gross,
            "usd_gross": usd_gross,
            "total_gifts_sent": total_gifts,
            "gift_events_count": gift_events_cnt,
            "unique_gifters": unique_gifters,
            "avg_coins_per_gift": avg_coins_per_gift,
            "avg_coins_per_gifter": avg_coins_per_gifter,
            "avg_eur_per_gifter": avg_eur_per_gifter,
            "whale_share_top1_pct": whale_share_top1,
            "whale_share_top3_pct": whale_share_top3,
            "whale_share_top5_pct": whale_share_top5,
            "sessions_count": len(sessions),
            "total_stream_minutes": total_session_minutes,
        },
        "timeline": timeline,
        "multi_streamer_datasets": multi_streamer_datasets,
        "time_of_day": time_of_day,
        "top_gifts": top_gifts,
        "top_gifters": top_gifters,
        "streamers_ranking": streamers_ranking,
        "sessions": sessions,
    }


def build_streamer_bot_report(
    streamer_row: Dict[str, Any],
    hours: int = 24,
    is_tracking_active: bool = False,
    worker_state: str = "stopped",
) -> Dict[str, Any]:
    cfg = get_settings()
    cutoff = (datetime.now() - timedelta(hours=max(1, hours))).isoformat(timespec="seconds")
    sid = int(streamer_row["id"])

    with get_db() as conn:
        period_agg = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_coins), 0) AS coins,
                COALESCE(SUM(repeat_count), 0) AS gifts_sent,
                COUNT(id) AS gift_events,
                COUNT(DISTINCT sender_username) AS unique_gifters
            FROM gift_events
            WHERE streamer_id = ? AND created_at >= ?
            """,
            (sid, cutoff),
        ).fetchone()

        alltime_agg = conn.execute(
            """
            SELECT COALESCE(SUM(total_coins), 0) AS coins
            FROM gift_events
            WHERE streamer_id = ?
            """,
            (sid,),
        ).fetchone()

        sess_agg = conn.execute(
            """
            SELECT
                COUNT(id) AS sessions_count,
                COALESCE(MAX(peak_viewers), 0) AS max_peak_viewers
            FROM stream_sessions
            WHERE streamer_id = ? AND (started_at >= ? OR status = 'active')
            """,
            (sid, cutoff),
        ).fetchone()

        top_gifts_rows = conn.execute(
            """
            SELECT
                gift_name,
                diamond_count,
                SUM(repeat_count) AS total_quantity,
                SUM(total_coins) AS total_coins,
                COUNT(id) AS events_count
            FROM gift_events
            WHERE streamer_id = ? AND created_at >= ?
            GROUP BY gift_name, diamond_count
            ORDER BY total_coins DESC
            LIMIT 5
            """,
            (sid, cutoff),
        ).fetchall()

        top_gifters_rows = conn.execute(
            """
            SELECT
                sender_username,
                MAX(sender_nickname) AS sender_nickname,
                MAX(is_super_fan) AS is_super_fan,
                SUM(total_coins) AS total_coins,
                SUM(repeat_count) AS gifts_sent,
                COUNT(id) AS transactions
            FROM gift_events
            WHERE streamer_id = ? AND created_at >= ?
            GROUP BY sender_username
            ORDER BY total_coins DESC
            LIMIT 5
            """,
            (sid, cutoff),
        ).fetchall()

    p_coins = int(period_agg["coins"] or 0)
    p_usd_net = round(p_coins * cfg["usd_per_diamond"], 2)
    p_eur_net = round(p_usd_net * cfg["usd_to_eur_rate"], 2)
    p_usd_gross = round(p_coins * cfg["gross_usd_per_coin"], 2)
    p_eur_gross = round(p_usd_gross * cfg["usd_to_eur_rate"], 2)

    all_coins = int(alltime_agg["coins"] or 0)
    all_usd_net = round(all_coins * cfg["usd_per_diamond"], 2)
    all_eur_net = round(all_usd_net * cfg["usd_to_eur_rate"], 2)

    top_gifts = []
    for g in top_gifts_rows:
        c = int(g["total_coins"] or 0)
        u_net = round(c * cfg["usd_per_diamond"], 2)
        e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
        top_gifts.append(
            {
                "gift_name": g["gift_name"],
                "diamond_count": int(g["diamond_count"] or 0),
                "total_quantity": int(g["total_quantity"] or 0),
                "total_coins": c,
                "events_count": int(g["events_count"] or 0),
                "usd_net": u_net,
                "eur_net": e_net,
            }
        )

    top_gifters = []
    for tg in top_gifters_rows:
        c = int(tg["total_coins"] or 0)
        u_net = round(c * cfg["usd_per_diamond"], 2)
        e_net = round(u_net * cfg["usd_to_eur_rate"], 2)
        top_gifters.append(
            {
                "sender_username": tg["sender_username"],
                "sender_nickname": tg["sender_nickname"] or tg["sender_username"],
                "is_super_fan": bool(tg["is_super_fan"]),
                "total_coins": c,
                "gifts_sent": int(tg["gifts_sent"] or 0),
                "transactions": int(tg["transactions"] or 0),
                "usd_net": u_net,
                "eur_net": e_net,
            }
        )

    uname = streamer_row["username"]
    dname = streamer_row["display_name"] or uname
    live_icon = "🟢 LIVE" if streamer_row.get("is_live") else "⚪ Offline"
    top_gift_str = (
        f"{top_gifts[0]['gift_name']} ({top_gifts[0]['total_coins']:,} Coins)"
        if top_gifts
        else "Keine"
    )
    top_gifter_str = (
        f"@{top_gifters[0]['sender_username']} ({top_gifters[0]['total_coins']:,} Coins)"
        if top_gifters
        else "Keine"
    )

    telegram_text = (
        f"📊 *{dname}* (@{uname}) [{live_icon}]\n"
        f"• Zeitraum ({hours}h): *{p_eur_net:,.2f} €* (${p_usd_net:,.2f}) | *{p_coins:,} Coins*\n"
        f"• Brutto-Kaufwert ({hours}h): {p_eur_gross:,.2f} € | Gifts: {int(period_agg['gifts_sent'] or 0)} ({int(period_agg['unique_gifters'] or 0)} Gifter)\n"
        f"• Top Gift: {top_gift_str}\n"
        f"• Top Spender: {top_gifter_str}\n"
        f"• Gesamt (All-Time): {all_eur_net:,.2f} € ({all_coins:,} Coins)"
    )

    return {
        "streamer_id": sid,
        "username": uname,
        "display_name": dname,
        "is_live": bool(streamer_row.get("is_live")),
        "is_tracking_active": is_tracking_active,
        "worker_state": worker_state,
        "current_viewers": int(streamer_row.get("current_viewers") or 0),
        "follower_count": int(streamer_row.get("follower_count") or 0),
        "period_hours": hours,
        "period_coins": p_coins,
        "period_gifts_sent": int(period_agg["gifts_sent"] or 0),
        "period_gift_events": int(period_agg["gift_events"] or 0),
        "period_unique_gifters": int(period_agg["unique_gifters"] or 0),
        "period_usd_net": p_usd_net,
        "period_eur_net": p_eur_net,
        "period_usd_gross": p_usd_gross,
        "period_eur_gross": p_eur_gross,
        "period_sessions_count": int(sess_agg["sessions_count"] or 0),
        "period_peak_viewers": max(
            int(sess_agg["max_peak_viewers"] or 0),
            int(streamer_row.get("current_viewers") or 0),
        ),
        "alltime_coins": all_coins,
        "alltime_usd_net": all_usd_net,
        "alltime_eur_net": all_eur_net,
        "top_gifts": top_gifts,
        "top_gifters": top_gifters,
        "telegram_text": telegram_text,
    }
