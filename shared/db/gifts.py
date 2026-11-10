"""
TokTracker - Erfassung einzelner Geschenk-Events inkl. Währungsumrechnung.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import get_db
from shared.db.revenue import get_revenue_profile_for_streamer
from shared.revenue import compute_gift_revenue, normalize_profile


def record_gift_event(
    streamer_id: int,
    sender_username: str,
    gift_name: str,
    diamond_count: int,
    repeat_count: int = 1,
    sender_nickname: Optional[str] = None,
    sender_user_id: str = "",
    is_super_fan: bool = False,
    gift_id: int = 0,
    gift_icon_url: str = "",
    combo_count: int = 1,
    group_id: str = "",
    room_fan_tickets: int = 0,
    event_uid: Optional[str] = None,
    session_id: Optional[int] = None,
    source: str = "tiktoklive",
    created_at: Optional[str] = None,
    revenue_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    diamond_count = max(0, int(diamond_count))
    repeat_count = max(1, int(repeat_count))
    total_coins = diamond_count * repeat_count

    profile = revenue_profile or get_revenue_profile_for_streamer(streamer_id)
    revenue = compute_gift_revenue(total_coins, profile)
    snapshot = normalize_profile(profile)
    profile_id = int(profile["id"]) if profile and profile.get("id") else None
    usd_net = revenue["usd_net"]
    eur_net = revenue["eur_net"]
    usd_gross = revenue["usd_gross"]
    eur_gross = revenue["eur_gross"]

    ts = created_at or datetime.now().isoformat(timespec="seconds")

    with get_db() as conn:
        if event_uid:
            existing = conn.execute(
                "SELECT id FROM gift_events WHERE event_uid = ?", (event_uid,)
            ).fetchone()
            if existing:
                return None, False

        cur = conn.execute(
            """
            INSERT INTO gift_events (
                streamer_id, session_id, event_uid,
                sender_user_id, sender_username, sender_nickname, is_super_fan,
                gift_id, gift_name, gift_icon_url,
                diamond_count, repeat_count, combo_count, group_id, room_fan_tickets,
                total_coins, usd_net, eur_net, usd_gross, eur_gross,
                revenue_profile_id, revenue_model, coin_price_usd,
                creator_share_pct, agency_share_pct, payout_fee_pct, tax_pct,
                fx_rate, usd_net_low, usd_net_high, eur_net_low, eur_net_high,
                source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                streamer_id,
                session_id,
                event_uid,
                str(sender_user_id or ""),
                sender_username,
                sender_nickname or sender_username,
                int(bool(is_super_fan)),
                gift_id,
                gift_name,
                gift_icon_url,
                diamond_count,
                repeat_count,
                combo_count,
                str(group_id or ""),
                int(room_fan_tickets or 0),
                total_coins,
                usd_net,
                eur_net,
                usd_gross,
                eur_gross,
                profile_id,
                "v2-profile" if profile_id else "legacy-settings",
                snapshot["coin_price_usd"],
                snapshot["creator_share_pct"],
                snapshot["agency_share_pct"],
                snapshot["payout_fee_pct"],
                snapshot["tax_pct"],
                snapshot["fx_rate"],
                revenue["usd_net_low"],
                revenue["usd_net_high"],
                revenue["eur_net_low"],
                revenue["eur_net_high"],
                source,
                ts,
            ),
        )
        conn.execute(
            "UPDATE streamers SET last_seen_at = ? WHERE id = ?",
            (ts, streamer_id),
        )
        if session_id and room_fan_tickets > 0:
            conn.execute(
                """
                UPDATE stream_sessions
                SET last_fan_tickets = MAX(last_fan_tickets, ?)
                WHERE id = ?
                """,
                (int(room_fan_tickets), session_id),
            )

        row = conn.execute(
            """
            SELECT g.*, s.username AS streamer_username, s.display_name AS streamer_display_name
            FROM gift_events g
            JOIN streamers s ON s.id = g.streamer_id
            WHERE g.id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
        return (dict(row) if row else None), True
