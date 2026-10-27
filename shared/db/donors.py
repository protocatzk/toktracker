"""
TokTracker - Spender-Radar, Whale-Tiers, Donor-CRM und Loyalty-Auswertungen.
"""

import copy
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import _get_period_cutoff, get_db

WHALE_TIER_WHALE = "whale"       # >= 10,000 Coins / Diamonds (~50 € Netto)


WHALE_TIER_SHARK = "shark"       # >= 2,500 Coins / Diamonds (~12.50 € Netto)


WHALE_TIER_DOLPHIN = "dolphin"   # >= 500 Coins / Diamonds (~2.50 € Netto)


def get_donor_tier(coins: int) -> str:
    """
    Klassifiziert einen Spender anhand der gespendeten Gesamtmünzen.
    - Whale (Wal): >= 10.000 Coins
    - Shark (Hai): >= 2.500 Coins
    - Dolphin (Delfin): >= 500 Coins
    """
    if coins >= 10000:
        return WHALE_TIER_WHALE
    elif coins >= 2500:
        return WHALE_TIER_SHARK
    elif coins >= 500:
        return WHALE_TIER_DOLPHIN
    return ""


def get_known_donor_tiers() -> Dict[str, str]:
    """
    Gibt ein schnelles Mapping {username_lower: tier} aller Spender zurück, die
    mindestens 500 Münzen (Dolphin, Shark oder Whale) gespendet haben.
    Wird vom StreamerWorker als In-Memory-Cache genutzt, um eingehende Chatnachrichten
    ohne Datenbankverzögerung sofort mit dem Spender-Tier zu kennzeichnen.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT LOWER(sender_username) AS uname, SUM(total_coins) AS coins
            FROM gift_events
            GROUP BY LOWER(sender_username)
            HAVING coins >= 500
            """
        ).fetchall()
        result: Dict[str, str] = {}
        for r in rows:
            u = str(r["uname"]).strip().lower()
            c = int(r["coins"] or 0)
            t = get_donor_tier(c)
            if t:
                result[u] = t
        return result


_radar_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


_radar_cache_lock = threading.Lock()


_RADAR_CACHE_TTL = 3.0


_loyalty_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


_loyalty_cache_lock = threading.Lock()


_LOYALTY_CACHE_TTL = 10.0


def invalidate_radar_cache() -> None:
    with _radar_cache_lock:
        _radar_cache.clear()
    with _loyalty_cache_lock:
        _loyalty_cache.clear()


def get_donor_radar_data(
    period: str = "all",
    min_tier: Optional[str] = None,
    streamer_id: Optional[int] = None,
    cross_streamer_only: bool = False,
    vip_only: bool = False,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Aggregiert Spender und Wale über alle getrackten Streamer.
    Liefert KPI-Karten, Cross-Streamer-Erkennung und Top-Spender-Rangliste inkl. VIP/CRM-Status.
    """
    cache_key = f"{period}:{min_tier}:{streamer_id}:{cross_streamer_only}:{vip_only}:{search}:{limit}:{offset}"
    now = time.monotonic()
    with _radar_cache_lock:
        cached = _radar_cache.get(cache_key)
        if cached and (now - cached[0]) < _RADAR_CACHE_TTL:
            return copy.deepcopy(cached[1])

    cutoff = _get_period_cutoff(period)

    where_clauses = ["1=1"]
    params: List[Any] = []

    if cutoff:
        where_clauses.append("g.created_at >= ?")
        params.append(cutoff)

    if streamer_id:
        where_clauses.append("g.streamer_id = ?")
        params.append(streamer_id)

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        where_clauses.append("(LOWER(g.sender_username) LIKE ? OR LOWER(g.sender_nickname) LIKE ?)")
        params.extend([search_pattern, search_pattern])

    where_sql = " AND ".join(where_clauses)

    having_clauses = []
    if min_tier == "whale":
        having_clauses.append("SUM(g.total_coins) >= 10000")
    elif min_tier == "shark":
        having_clauses.append("SUM(g.total_coins) >= 2500")
    elif min_tier == "dolphin":
        having_clauses.append("SUM(g.total_coins) >= 500")

    if cross_streamer_only:
        having_clauses.append("COUNT(DISTINCT g.streamer_id) >= 2")

    if vip_only:
        having_clauses.append("COALESCE(MAX(c.is_vip), 0) = 1")

    having_sql = f"HAVING {' AND '.join(having_clauses)}" if having_clauses else ""

    query = f"""
    SELECT
        LOWER(g.sender_username) AS uname_key,
        MAX(g.sender_username) AS username,
        MAX(g.sender_nickname) AS display_name,
        SUM(g.total_coins) AS total_coins,
        SUM(g.eur_net) AS total_eur_net,
        SUM(g.usd_net) AS total_usd_net,
        SUM(g.eur_gross) AS total_eur_gross,
        SUM(g.usd_gross) AS total_usd_gross,
        COUNT(g.id) AS total_gifts,
        COUNT(DISTINCT g.streamer_id) AS streamer_count,
        MIN(g.created_at) AS first_seen,
        MAX(g.created_at) AS last_seen,
        COALESCE(MAX(c.is_vip), 0) AS is_vip,
        MAX(c.tags) AS tags,
        MAX(c.notes) AS notes
    FROM gift_events g
    LEFT JOIN donor_crm c ON LOWER(c.username) = LOWER(g.sender_username)
    WHERE {where_sql}
    GROUP BY LOWER(g.sender_username)
    {having_sql}
    ORDER BY total_coins DESC
    LIMIT ? OFFSET ?
    """
    exec_params = list(params) + [max(1, min(limit, 500)), max(0, offset)]

    with get_db() as conn:
        rows = conn.execute(query, exec_params).fetchall()
        donors = []
        for r in rows:
            d = dict(r)
            coins = int(d["total_coins"] or 0)
            d["tier"] = get_donor_tier(coins)
            d["is_cross_streamer"] = int(d["streamer_count"] or 0) >= 2
            d["total_eur_net"] = round(float(d["total_eur_net"] or 0.0), 2)
            d["total_usd_net"] = round(float(d["total_usd_net"] or 0.0), 2)
            d["total_eur_gross"] = round(float(d["total_eur_gross"] or 0.0), 2)
            d["total_usd_gross"] = round(float(d["total_usd_gross"] or 0.0), 2)
            d["is_vip"] = bool(d.get("is_vip"))
            raw_tags = d.get("tags") or ""
            d["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
            d["notes"] = d.get("notes") or ""
            d["has_notes"] = bool(d["notes"].strip())
            donors.append(d)

        # KPIs über alle Spender im Zeitraum
        kpis_query = f"""
        SELECT
            COUNT(DISTINCT uname) as all_donors,
            SUM(CASE WHEN coins >= 10000 THEN 1 ELSE 0 END) as count_whales,
            SUM(CASE WHEN coins >= 2500 AND coins < 10000 THEN 1 ELSE 0 END) as count_sharks,
            SUM(CASE WHEN coins >= 500 AND coins < 2500 THEN 1 ELSE 0 END) as count_dolphins,
            SUM(CASE WHEN s_count >= 2 AND coins >= 500 THEN 1 ELSE 0 END) as count_cross,
            SUM(CASE WHEN coins >= 500 THEN coins ELSE 0 END) as sum_whale_coins,
            SUM(CASE WHEN coins >= 500 THEN eur_net ELSE 0 END) as sum_whale_eur_net
        FROM (
            SELECT
                LOWER(g.sender_username) as uname,
                SUM(g.total_coins) as coins,
                SUM(g.eur_net) as eur_net,
                COUNT(DISTINCT g.streamer_id) as s_count
            FROM gift_events g
            WHERE {where_sql}
            GROUP BY LOWER(g.sender_username)
        ) sub
        """
        kpi_row = conn.execute(kpis_query, params).fetchone()

        chat_count_row = conn.execute(
            "SELECT COUNT(*) as total_chat FROM chat_messages"
        ).fetchone()
        total_chat = int(chat_count_row["total_chat"] or 0) if chat_count_row else 0

        vip_cnt_row = conn.execute(
            "SELECT COUNT(*) as total_vips FROM donor_crm WHERE is_vip = 1"
        ).fetchone()
        total_vips = int(vip_cnt_row["total_vips"] or 0) if vip_cnt_row else 0

        w_count = int(kpi_row["count_whales"] or 0) if kpi_row else 0
        s_count = int(kpi_row["count_sharks"] or 0) if kpi_row else 0
        d_count = int(kpi_row["count_dolphins"] or 0) if kpi_row else 0

        kpis = {
            "whales": w_count,
            "sharks": s_count,
            "dolphins": d_count,
            "cross_streamer_whales": int(kpi_row["count_cross"] or 0) if kpi_row else 0,
            "total_tracked_whales": w_count + s_count + d_count,
            "whale_coins": int(kpi_row["sum_whale_coins"] or 0) if kpi_row else 0,
            "whale_eur_net": round(float(kpi_row["sum_whale_eur_net"] or 0.0), 2) if kpi_row else 0.0,
            "total_chat_messages": total_chat,
            "vip_donors": total_vips,
        }

        streamers = conn.execute(
            "SELECT id, username, display_name, avatar_url, is_live FROM streamers ORDER BY display_name ASC"
        ).fetchall()

        result = {
            "period": period,
            "kpis": kpis,
            "donors": donors,
            "streamers": [dict(s) for s in streamers],
        }
        with _radar_cache_lock:
            _radar_cache[cache_key] = (now, result)
        return copy.deepcopy(result)


def get_donor_details(username: str) -> Optional[Dict[str, Any]]:
    """
    Liefert ein umfassendes Spender-Dossier:
    - Gesamtausgaben (Coins, EUR/USD Netto & Brutto, Geschenke-Anzahl)
    - Verteilung über alle beschenkten Streamer
    - Top Lieblingsgeschenke
    - Letzte Chat-Nachrichten über alle Kanäle
    """
    clean_uname = username.strip().lstrip("@").lower()
    with get_db() as conn:
        main_row = conn.execute(
            """
            SELECT
                MAX(sender_username) as username,
                MAX(sender_nickname) as display_name,
                SUM(total_coins) as total_coins,
                SUM(eur_net) as total_eur_net,
                SUM(usd_net) as total_usd_net,
                SUM(eur_gross) as total_eur_gross,
                SUM(usd_gross) as total_usd_gross,
                COUNT(id) as total_gifts,
                COUNT(DISTINCT streamer_id) as streamer_count,
                MIN(created_at) as first_seen,
                MAX(created_at) as last_seen
            FROM gift_events
            WHERE LOWER(sender_username) = ?
            """,
            (clean_uname,),
        ).fetchone()

        if not main_row or not main_row["total_coins"]:
            chat_user_row = conn.execute(
                "SELECT username, nickname, avatar_url FROM chat_messages WHERE LOWER(username) = ? LIMIT 1",
                (clean_uname,),
            ).fetchone()
            if not chat_user_row:
                return None
            profile = {
                "username": chat_user_row["username"],
                "display_name": chat_user_row["nickname"] or chat_user_row["username"],
                "avatar_url": chat_user_row["avatar_url"],
                "total_coins": 0,
                "total_eur_net": 0.0,
                "total_usd_net": 0.0,
                "total_eur_gross": 0.0,
                "total_usd_gross": 0.0,
                "total_gifts": 0,
                "streamer_count": 0,
                "first_seen": "-",
                "last_seen": "-",
                "tier": "",
                "is_cross_streamer": False,
            }
        else:
            coins = int(main_row["total_coins"] or 0)
            avatar_row = conn.execute(
                "SELECT avatar_url FROM chat_messages WHERE LOWER(username) = ? AND avatar_url != '' ORDER BY id DESC LIMIT 1",
                (clean_uname,),
            ).fetchone()
            avatar_url = avatar_row["avatar_url"] if avatar_row else ""
            profile = {
                "username": main_row["username"],
                "display_name": main_row["display_name"] or main_row["username"],
                "avatar_url": avatar_url,
                "total_coins": coins,
                "total_eur_net": round(float(main_row["total_eur_net"] or 0.0), 2),
                "total_usd_net": round(float(main_row["total_usd_net"] or 0.0), 2),
                "total_eur_gross": round(float(main_row["total_eur_gross"] or 0.0), 2),
                "total_usd_gross": round(float(main_row["total_usd_gross"] or 0.0), 2),
                "total_gifts": int(main_row["total_gifts"] or 0),
                "streamer_count": int(main_row["streamer_count"] or 0),
                "first_seen": main_row["first_seen"],
                "last_seen": main_row["last_seen"],
                "tier": get_donor_tier(coins),
                "is_cross_streamer": int(main_row["streamer_count"] or 0) >= 2,
            }

        # Streamer Breakdown
        streamer_rows = conn.execute(
            """
            SELECT
                g.streamer_id,
                s.username as streamer_username,
                s.display_name as streamer_display_name,
                s.avatar_url as streamer_avatar_url,
                SUM(g.total_coins) as coins_given,
                SUM(g.eur_net) as eur_net,
                COUNT(g.id) as gift_count,
                MAX(g.created_at) as last_gift_at
            FROM gift_events g
            JOIN streamers s ON s.id = g.streamer_id
            WHERE LOWER(g.sender_username) = ?
            GROUP BY g.streamer_id, s.username, s.display_name, s.avatar_url
            ORDER BY coins_given DESC
            """,
            (clean_uname,),
        ).fetchall()
        streamers_breakdown = []
        for sr in streamer_rows:
            sd = dict(sr)
            sd["eur_net"] = round(float(sd["eur_net"] or 0.0), 2)
            streamers_breakdown.append(sd)

        # Top 6 Lieblingsgeschenke
        gift_rows = conn.execute(
            """
            SELECT
                gift_name,
                gift_icon_url,
                SUM(repeat_count) as total_sent,
                SUM(total_coins) as total_coins
            FROM gift_events
            WHERE LOWER(sender_username) = ?
            GROUP BY gift_name, gift_icon_url
            ORDER BY total_coins DESC
            LIMIT 6
            """,
            (clean_uname,),
        ).fetchall()
        top_gifts = [dict(gr) for gr in gift_rows]

        # Letzte 25 Chatnachrichten
        chat_rows = conn.execute(
            """
            SELECT
                c.id, c.streamer_id, c.comment, c.created_at,
                s.username as streamer_username, s.display_name as streamer_display_name
            FROM chat_messages c
            JOIN streamers s ON s.id = c.streamer_id
            WHERE LOWER(c.username) = ?
            ORDER BY c.id DESC
            LIMIT 25
            """,
            (clean_uname,),
        ).fetchall()
        recent_chats = [dict(cr) for cr in chat_rows]

        crm = get_donor_crm(clean_uname)
        profile["is_vip"] = crm["is_vip"]
        profile["tags"] = crm["tags"]
        profile["notes"] = crm["notes"]

        # Loyalitäts-Berechnung (Konzentration auf Hauptstreamer)
        total_spent_coins = sum(int(s.get("coins_given") or 0) for s in streamers_breakdown)
        if total_spent_coins > 0 and streamers_breakdown:
            top_streamer = streamers_breakdown[0]
            top_coins = int(top_streamer.get("coins_given") or 0)
            loyalty_score = round((top_coins / total_spent_coins) * 100, 1)

            if loyalty_score >= 85:
                loyalty_tier = "diehard"
                loyalty_label = "Eingeschworener Stamm-Supporter"
                loyalty_badge = f"💎 {loyalty_score}% Treue"
                loyalty_color = "#38bdf8"
            elif loyalty_score >= 60:
                loyalty_tier = "focused"
                loyalty_label = "Fokussierter Fan"
                loyalty_badge = f"🎯 {loyalty_score}% Fokus"
                loyalty_color = "#34d399"
            elif loyalty_score >= 40:
                loyalty_tier = "multi"
                loyalty_label = "Multi-Streamer Supporter"
                loyalty_badge = f"⚖️ {loyalty_score}% Geteilt"
                loyalty_color = "#fbbf24"
            else:
                loyalty_tier = "hopper"
                loyalty_label = "Wander-Wal / Hopper"
                loyalty_badge = f"🌪️ {loyalty_score}% Sprunghaft"
                loyalty_color = "#f472b6"

            loyalty = {
                "score": loyalty_score,
                "tier": loyalty_tier,
                "label": loyalty_label,
                "badge": loyalty_badge,
                "color": loyalty_color,
                "primary_streamer": top_streamer.get("streamer_username"),
                "primary_streamer_display": top_streamer.get("streamer_display_name") or top_streamer.get("streamer_username"),
                "primary_coins": top_coins,
                "streamer_count": len(streamers_breakdown),
            }
        else:
            loyalty = {
                "score": 0.0,
                "tier": "unknown",
                "label": "Keine Daten",
                "badge": "-",
                "color": "#94a3b8",
                "primary_streamer": "",
                "primary_streamer_display": "",
                "primary_coins": 0,
                "streamer_count": 0,
            }

        # Frontenwechsler-Check (Historisch vs. Letzte 14 Tage)
        cutoff_14d = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        period_rows = conn.execute(
            """
            SELECT
                g.streamer_id,
                s.username as streamer_username,
                s.display_name as streamer_display_name,
                CASE WHEN g.created_at < ? THEN 'old' ELSE 'recent' END as period_slot,
                SUM(g.total_coins) as coins
            FROM gift_events g
            JOIN streamers s ON s.id = g.streamer_id
            WHERE LOWER(g.sender_username) = ?
            GROUP BY g.streamer_id, period_slot
            """,
            (cutoff_14d, clean_uname),
        ).fetchall()

        old_streamers: Dict[int, Tuple[str, int]] = {}
        recent_streamers: Dict[int, Tuple[str, int]] = {}
        for pr in period_rows:
            slot = pr["period_slot"]
            s_name = pr["streamer_display_name"] or pr["streamer_username"]
            coins = int(pr["coins"] or 0)
            if slot == "old":
                old_streamers[pr["streamer_id"]] = (s_name, coins)
            else:
                recent_streamers[pr["streamer_id"]] = (s_name, coins)

        frontenwechsel = {
            "is_shifted": False,
            "status_label": "Konstant loyal",
            "description": "Bisher kein Frontenwechsel erkannt.",
            "from_streamer": "",
            "to_streamer": "",
        }

        if old_streamers and recent_streamers:
            top_old_id = max(old_streamers, key=lambda k: old_streamers[k][1])
            top_recent_id = max(recent_streamers, key=lambda k: recent_streamers[k][1])
            if top_old_id != top_recent_id and recent_streamers[top_recent_id][1] >= 200:
                s_from = old_streamers[top_old_id][0]
                s_to = recent_streamers[top_recent_id][0]
                frontenwechsel = {
                    "is_shifted": True,
                    "status_label": "⚠️ Frontenwechsler",
                    "description": f"Früher Hauptunterstützer von {s_from}, schenkt in den letzten 14 Tagen vorrangig an {s_to}!",
                    "from_streamer": s_from,
                    "to_streamer": s_to,
                }
        elif recent_streamers and not old_streamers:
            frontenwechsel["status_label"] = "Neuerscheinung"
            frontenwechsel["description"] = "Erst in den letzten 14 Tagen aktiv geworden."

        return {
            "profile": profile,
            "streamers": streamers_breakdown,
            "top_gifts": top_gifts,
            "recent_chats": recent_chats,
            "crm": crm,
            "loyalty": loyalty,
            "frontenwechsel": frontenwechsel,
        }


def get_donor_crm(username: str) -> Dict[str, Any]:
    """
    Liefert die CRM-Daten (VIP-Status, Tags, interne Notizen) eines Spenders.
    """
    clean_uname = username.strip().lstrip("@").lower()
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id, username, is_vip, tags, notes, created_at, updated_at
            FROM donor_crm
            WHERE LOWER(username) = ?
            """,
            (clean_uname,),
        ).fetchone()

        if not row:
            return {
                "id": None,
                "username": clean_uname,
                "is_vip": False,
                "tags": [],
                "notes": "",
                "created_at": None,
                "updated_at": None,
            }

        raw_tags = row["tags"] or ""
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        return {
            "id": row["id"],
            "username": row["username"],
            "is_vip": bool(row["is_vip"]),
            "tags": tags_list,
            "notes": row["notes"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def save_donor_crm(
    username: str,
    is_vip: Optional[bool] = None,
    tags: Optional[Union[List[str], str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Speichert oder aktualisiert VIP-Status, Tags und Notizen eines Spenders.
    Vollständig portabel für SQLite und MySQL.
    """
    clean_uname = username.strip().lstrip("@").lower()
    now = datetime.now(timezone.utc).isoformat()

    tags_str: Optional[str] = None
    if tags is not None:
        if isinstance(tags, list):
            tags_str = ",".join([t.strip().replace(",", "") for t in tags if t.strip()])
        else:
            tags_str = str(tags).strip()

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, is_vip, tags, notes FROM donor_crm WHERE LOWER(username) = ?",
            (clean_uname,),
        ).fetchone()

        if existing:
            new_vip = int(is_vip) if is_vip is not None else int(existing["is_vip"] or 0)
            new_tags = tags_str if tags_str is not None else (existing["tags"] or "")
            new_notes = notes if notes is not None else (existing["notes"] or "")
            conn.execute(
                """
                UPDATE donor_crm
                SET is_vip = ?, tags = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_vip, new_tags, new_notes, now, existing["id"]),
            )
        else:
            new_vip = int(is_vip) if is_vip is not None else 0
            new_tags = tags_str if tags_str is not None else ""
            new_notes = notes if notes is not None else ""
            conn.execute(
                """
                INSERT INTO donor_crm (username, is_vip, tags, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_uname, new_vip, new_tags, new_notes, now, now),
            )

    invalidate_radar_cache()
    return get_donor_crm(clean_uname)


def toggle_donor_vip(username: str) -> Dict[str, Any]:
    """
    Schaltet den VIP-Watchlist-Status eines Spenders um.
    """
    current = get_donor_crm(username)
    return save_donor_crm(username, is_vip=not current["is_vip"])


def get_recent_whale_gifts(
    min_coins: int = 1000,
    after_id: Optional[int] = None,
    limit: int = 20,
    streamer_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Liefert aktuelle Großspenden (Whale- & Shark-Events) für den Live-Ticker und Audio-Alerts.
    Optional gefiltert nach Mindest-Coins und/oder streamer_id.
    """
    query = """
    SELECT
        g.id, g.streamer_id, g.gift_name, g.gift_icon_url, g.diamond_count,
        g.repeat_count, g.total_coins, g.eur_net, g.usd_net, g.eur_gross, g.usd_gross,
        g.sender_username, g.sender_nickname, g.created_at,
        s.username as streamer_username, s.display_name as streamer_display_name, s.avatar_url as streamer_avatar_url,
        COALESCE(c.is_vip, 0) as is_vip,
        COALESCE(c.tags, '') as tags
    FROM gift_events g
    JOIN streamers s ON s.id = g.streamer_id
    LEFT JOIN donor_crm c ON LOWER(c.username) = LOWER(g.sender_username)
    WHERE g.total_coins >= ?
    """
    params: List[Any] = [min_coins]
    if streamer_id is not None:
        query += " AND g.streamer_id = ?"
        params.append(streamer_id)
    if after_id is not None:
        query += " AND g.id > ? ORDER BY g.id ASC LIMIT ?"
        params.extend([after_id, max(1, min(limit, 100))])
    else:
        query += " ORDER BY g.id DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        alerts = []
        for r in rows:
            d = dict(r)
            coins = int(d["total_coins"] or 0)
            d["is_vip"] = bool(d.get("is_vip"))
            d["tier"] = get_donor_tier(coins)
            d["eur_net"] = round(float(d["eur_net"] or 0.0), 2)
            d["usd_net"] = round(float(d["usd_net"] or 0.0), 2)
            d["eur_gross"] = round(float(d["eur_gross"] or 0.0), 2)
            d["usd_gross"] = round(float(d["usd_gross"] or 0.0), 2)
            raw_tags = d.get("tags") or ""
            d["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
            alerts.append(d)
        return alerts


def get_network_loyalty_and_overlap(
    min_coins: int = 100,
    days_recent: int = 14,
) -> Dict[str, Any]:
    """
    Netzwerkweite Auswertung für den Loyalitäts- & Frontenwechsler-Hub:
    1. Frontenwechsler: Großspender, die ihren primären Streamer gewechselt haben.
    2. Overlap-Matrix: Paare von Streamern, die sich dieselben Großspender teilen.
    """
    cache_key = f"{min_coins}:{days_recent}"
    now = time.monotonic()
    with _loyalty_cache_lock:
        cached = _loyalty_cache.get(cache_key)
        if cached and (now - cached[0]) < _LOYALTY_CACHE_TTL:
            return copy.deepcopy(cached[1])

    with get_db() as conn:
        now_dt = datetime.now(timezone.utc)
        # Zeitspanne der vorhandenen Events prüfen für adaptive Fenster-Teilung
        span_row = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM gift_events").fetchone()
        if span_row and span_row[0] and span_row[1]:
            try:
                min_ts = datetime.fromisoformat(span_row[0].replace("Z", "+00:00"))
                max_ts = datetime.fromisoformat(span_row[1].replace("Z", "+00:00"))
                total_hours = (max_ts - min_ts).total_seconds() / 3600.0
                if total_hours < (days_recent * 24):
                    # Bei kurzer Datenhistorie (< gewählter Zeitraum): Teilung in der Daten-Mitte
                    cutoff_dt = min_ts + (max_ts - min_ts) / 2
                else:
                    cutoff_dt = now_dt - timedelta(days=days_recent / 2)
            except Exception:
                cutoff_dt = now_dt - timedelta(days=days_recent / 2)
        else:
            cutoff_dt = now_dt - timedelta(days=days_recent / 2)

        cutoff = cutoff_dt.isoformat()

        # 1. Frontenwechsler ermitteln
        history_query = """
        SELECT
            LOWER(g.sender_username) as uname,
            MAX(g.sender_username) as username,
            MAX(g.sender_nickname) as display_name,
            g.streamer_id,
            s.username as streamer_username,
            s.display_name as streamer_display_name,
            s.avatar_url as streamer_avatar_url,
            CASE WHEN g.created_at < ? THEN 'old' ELSE 'recent' END as period_slot,
            SUM(g.total_coins) as coins,
            SUM(g.eur_net) as eur_net,
            COALESCE(MAX(c.is_vip), 0) as is_vip,
            COALESCE(MAX(c.tags), '') as tags
        FROM gift_events g
        JOIN streamers s ON s.id = g.streamer_id
        LEFT JOIN donor_crm c ON LOWER(c.username) = LOWER(g.sender_username)
        GROUP BY LOWER(g.sender_username), g.streamer_id, period_slot
        HAVING SUM(g.total_coins) >= 1
        """
        h_rows = conn.execute(history_query, (cutoff,)).fetchall()

        donors_data: Dict[str, Dict[str, Any]] = {}
        for r in h_rows:
            uname = r["uname"]
            if uname not in donors_data:
                donors_data[uname] = {
                    "username": r["username"],
                    "display_name": r["display_name"] or r["username"],
                    "is_vip": bool(r["is_vip"]),
                    "tags": [t.strip() for t in (r["tags"] or "").split(",") if t.strip()],
                    "old_streamers": {},
                    "recent_streamers": {},
                    "total_coins": 0,
                    "total_eur_net": 0.0,
                }
            coins = int(r["coins"] or 0)
            eur = float(r["eur_net"] or 0.0)
            donors_data[uname]["total_coins"] += coins
            donors_data[uname]["total_eur_net"] += eur
            streamer_info = {
                "id": r["streamer_id"],
                "username": r["streamer_username"],
                "display_name": r["streamer_display_name"] or r["streamer_username"],
                "avatar_url": r["streamer_avatar_url"],
                "coins": coins,
                "eur_net": eur,
            }
            if r["period_slot"] == "old":
                donors_data[uname]["old_streamers"][r["streamer_id"]] = streamer_info
            else:
                donors_data[uname]["recent_streamers"][r["streamer_id"]] = streamer_info

        frontenwechsler = []
        for uname, d in donors_data.items():
            if not d["old_streamers"] or not d["recent_streamers"]:
                continue
            old_top_id = max(d["old_streamers"], key=lambda sid: d["old_streamers"][sid]["coins"])
            recent_top_id = max(d["recent_streamers"], key=lambda sid: d["recent_streamers"][sid]["coins"])

            if old_top_id != recent_top_id:
                old_s = d["old_streamers"][old_top_id]
                recent_s = d["recent_streamers"][recent_top_id]
                old_coins = old_s["coins"]
                recent_coins = recent_s["coins"]

                if (old_coins + recent_coins) >= min_coins:
                    total_recent_coins = sum(s["coins"] for s in d["recent_streamers"].values())
                    recent_share = round((recent_coins / total_recent_coins) * 100, 1) if total_recent_coins > 0 else 0.0
                    shift_ratio = round((recent_coins / (old_coins + recent_coins)), 2) if (old_coins + recent_coins) > 0 else 0.5

                    # Loyalität ermitteln
                    donor_total = d["total_coins"]
                    all_streamer_coins: Dict[int, int] = {}
                    for sid, sinfo in d["old_streamers"].items():
                        all_streamer_coins[sid] = all_streamer_coins.get(sid, 0) + sinfo["coins"]
                    for sid, sinfo in d["recent_streamers"].items():
                        all_streamer_coins[sid] = all_streamer_coins.get(sid, 0) + sinfo["coins"]
                    top_streamer_coins = max(all_streamer_coins.values()) if all_streamer_coins else 0
                    loyalty_ratio = top_streamer_coins / donor_total if donor_total > 0 else 1.0
                    loyalty_score = int(round(loyalty_ratio * 100))

                    if loyalty_score >= 85:
                        classification, label, color = "diehard", "Diehard-Stammspender", "#22c55e"
                    elif loyalty_score >= 65:
                        classification, label, color = "focused", "Fokussierter Spender", "#38bdf8"
                    elif loyalty_score >= 40:
                        classification, label, color = "multi", "Multi-Streamer Spender", "#eab308"
                    else:
                        classification, label, color = "hopper", "Streamer-Hopper", "#ec4899"

                    donor_avatar = None
                    chat_av_row = conn.execute(
                        "SELECT avatar_url FROM chat_messages WHERE LOWER(username) = ? AND avatar_url IS NOT NULL AND avatar_url != '' LIMIT 1",
                        (uname,),
                    ).fetchone()
                    if chat_av_row and chat_av_row[0]:
                        donor_avatar = chat_av_row[0]

                    frontenwechsler.append({
                        "username": d["username"],
                        "display_name": d["display_name"],
                        "avatar_url": donor_avatar,
                        "is_vip": d["is_vip"],
                        "tier": get_donor_tier(d["total_coins"]),
                        "tags": d["tags"],
                        "total_coins": d["total_coins"],
                        "total_net_eur": round(d["total_eur_net"], 2),
                        "loyalty_score": loyalty_score,
                        "classification": classification,
                        "label": label,
                        "color": color,
                        "crm": {
                            "is_vip": d["is_vip"],
                            "tags": d["tags"],
                        },
                        "frontenwechsel": {
                            "shifted": True,
                            "old_streamer": old_s["username"],
                            "old_streamer_display": old_s["display_name"],
                            "old_streamer_avatar": old_s.get("avatar_url") or "",
                            "new_streamer": recent_s["username"],
                            "new_streamer_display": recent_s["display_name"],
                            "new_streamer_avatar": recent_s.get("avatar_url") or "",
                            "old_coins": old_coins,
                            "new_coins": recent_coins,
                            "shift_ratio": shift_ratio,
                        },
                        "from_streamer": {
                            "id": old_s["id"],
                            "username": old_s["username"],
                            "display_name": old_s["display_name"],
                            "avatar_url": old_s.get("avatar_url") or "",
                            "coins": old_coins,
                        },
                        "to_streamer": {
                            "id": recent_s["id"],
                            "username": recent_s["username"],
                            "display_name": recent_s["display_name"],
                            "avatar_url": recent_s.get("avatar_url") or "",
                            "coins": recent_coins,
                            "eur_net": round(recent_s["eur_net"], 2),
                        },
                        "recent_share_percent": recent_share,
                        "shift_volume_coins": recent_coins,
                        "shift_volume_eur": round(recent_s["eur_net"], 2),
                        "migration_type": "Kompletter Wechsel" if old_top_id not in d["recent_streamers"] else "Schwerpunkt-Verlagerung",
                    })

        frontenwechsler.sort(key=lambda x: x["shift_volume_coins"], reverse=True)

        # 2. Streamer Overlap Matrix (Gemeinsame Großspender)
        overlap_query = """
        SELECT
            d1.streamer_id as s1_id,
            s1.username as s1_username,
            s1.display_name as s1_display_name,
            s1.avatar_url as s1_avatar,
            d2.streamer_id as s2_id,
            s2.username as s2_username,
            s2.display_name as s2_display_name,
            s2.avatar_url as s2_avatar,
            COUNT(d1.uname) as shared_donors_count,
            SUM(d1.coins) as total_coins_a,
            SUM(d2.coins) as total_coins_b,
            SUM(d1.coins + d2.coins) as total_shared_coins,
            SUM(d1.eur_net + d2.eur_net) as shared_volume_eur
        FROM (
            SELECT LOWER(sender_username) as uname, streamer_id, SUM(total_coins) as coins, SUM(eur_net) as eur_net
            FROM gift_events
            GROUP BY LOWER(sender_username), streamer_id
            HAVING SUM(total_coins) >= 1
        ) d1
        JOIN (
            SELECT LOWER(sender_username) as uname, streamer_id, SUM(total_coins) as coins, SUM(eur_net) as eur_net
            FROM gift_events
            GROUP BY LOWER(sender_username), streamer_id
            HAVING SUM(total_coins) >= 1
        ) d2 ON d1.uname = d2.uname AND d1.streamer_id < d2.streamer_id
        JOIN streamers s1 ON s1.id = d1.streamer_id
        JOIN streamers s2 ON s2.id = d2.streamer_id
        GROUP BY d1.streamer_id, d2.streamer_id
        HAVING shared_donors_count >= 1
        ORDER BY total_shared_coins DESC
        LIMIT 25
        """
        pair_rows = conn.execute(overlap_query).fetchall()
        overlap_matrix = []
        for pr in pair_rows:
            p_dict = dict(pr)
            s1_id = p_dict["s1_id"]
            s2_id = p_dict["s2_id"]
            coins_a = int(p_dict.get("total_coins_a") or 0)
            coins_b = int(p_dict.get("total_coins_b") or 0)
            total_coins = int(p_dict.get("total_shared_coins") or (coins_a + coins_b))
            pct_a = round((coins_a / total_coins) * 100, 1) if total_coins > 0 else 50.0
            pct_b = round(100.0 - pct_a, 1)

            # Beide Feldnamens-Standards bedienen
            p_dict["streamer_a_id"] = s1_id
            p_dict["streamer_a_username"] = p_dict["s1_username"]
            p_dict["streamer_a_display_name"] = p_dict["s1_display_name"] or p_dict["s1_username"]
            p_dict["streamer_a_avatar"] = p_dict["s1_avatar"]
            p_dict["streamer_b_id"] = s2_id
            p_dict["streamer_b_username"] = p_dict["s2_username"]
            p_dict["streamer_b_display_name"] = p_dict["s2_display_name"] or p_dict["s2_username"]
            p_dict["streamer_b_avatar"] = p_dict["s2_avatar"]
            p_dict["total_coins_a"] = coins_a
            p_dict["total_coins_b"] = coins_b
            p_dict["total_shared_coins"] = total_coins
            p_dict["shared_volume_coins"] = total_coins
            p_dict["streamer_a_pct"] = pct_a
            p_dict["streamer_b_pct"] = pct_b

            shared_top_rows = conn.execute(
                """
                SELECT
                    LOWER(g.sender_username) as uname,
                    MAX(g.sender_username) as username,
                    MAX(g.sender_nickname) as display_name,
                    SUM(g.total_coins) as total_coins,
                    COALESCE(MAX(c.is_vip), 0) as is_vip
                FROM gift_events g
                LEFT JOIN donor_crm c ON LOWER(c.username) = LOWER(g.sender_username)
                WHERE g.streamer_id IN (?, ?)
                GROUP BY LOWER(g.sender_username)
                HAVING COUNT(DISTINCT g.streamer_id) = 2
                ORDER BY total_coins DESC
                LIMIT 5
                """,
                (s1_id, s2_id),
            ).fetchall()

            top_shared = []
            for sr in shared_top_rows:
                c_val = int(sr["total_coins"] or 0)
                top_shared.append({
                    "username": sr["username"],
                    "display_name": sr["display_name"] or sr["username"],
                    "total_coins": c_val,
                    "coins": c_val,
                    "is_vip": bool(sr["is_vip"]),
                    "tier": get_donor_tier(c_val),
                })

            p_dict["top_donors"] = top_shared
            p_dict["top_shared_donors"] = top_shared
            p_dict["shared_volume_eur"] = round(float(p_dict.get("shared_volume_eur") or 0.0), 2)
            overlap_matrix.append(p_dict)

        result = {
            "frontenwechsler": frontenwechsler,
            "overlap_matrix": overlap_matrix,
            "days_recent": days_recent,
            "summary": {
                "total_shifters": len(frontenwechsler),
                "total_overlap_pairs": len(overlap_matrix),
            },
        }
        with _loyalty_cache_lock:
            _loyalty_cache[cache_key] = (now, result)
        return copy.deepcopy(result)
