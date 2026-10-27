"""
TokTracker - Traffic-, Bot-Session- und API-Call-Analytics.
"""

from datetime import datetime
from typing import Any, Dict, Optional

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


from shared.db._base import _get_period_cutoff, get_db
from shared.db.users import list_telegram_users


def record_page_view(
    path: str,
    visitor_hash: str,
    user_agent: str = "",
    device_type: str = "desktop",
    referrer: str = "",
    status_code: int = 200,
    response_time_ms: float = 0.0,
) -> None:
    """
    Speichert einen echten Seitenaufruf für die Web-Traffic-Analyse.
    Arbeitet extrem schnell (< 1ms) und blockiert keine Requests.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO page_views (
                path, visitor_hash, user_agent, device_type, referrer, status_code, response_time_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path[:250],
                visitor_hash[:64],
                user_agent[:500],
                device_type[:30],
                referrer[:500],
                int(status_code),
                round(float(response_time_ms), 2),
                now_str,
            ),
        )


def record_bot_session(
    session_type: str,
    telegram_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    client_ip_hash: str = "",
    status: str = "active",
    details_json: Optional[str] = None,
) -> None:
    """
    Protokolliert Interaktionen und Sessions mit dem Telegram-Bot und der Mini-App.
    Aktualisiert bestehende offene Sessions oder legt neue an.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        if telegram_id:
            row = conn.execute(
                """
                SELECT id FROM bot_sessions
                WHERE session_type = ? AND telegram_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (session_type, telegram_id),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE bot_sessions
                    SET last_active_at = ?,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        status = ?,
                        details_json = COALESCE(?, details_json)
                    WHERE id = ?
                    """,
                    (now_str, username, first_name, status, details_json, row["id"]),
                )
                return

        conn.execute(
            """
            INSERT INTO bot_sessions (
                session_type, telegram_id, username, first_name, client_ip_hash, status, details_json, created_at, last_active_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_type[:30],
                telegram_id,
                (username or "")[:190],
                (first_name or "")[:250],
                (client_ip_hash or "")[:64],
                (status or "active")[:30],
                details_json,
                now_str,
                now_str,
            ),
        )


def record_api_call(
    endpoint: str,
    method: str = "GET",
    status_code: int = 200,
    response_time_ms: float = 0.0,
    client_ip: str = "",
    ip_hash: str = "",
    user_agent: str = "",
    auth_type: str = "none",
    api_key_name: str = "",
    is_external: int = 1,
    query_params: str = "",
) -> None:
    """
    Protokolliert einen API-Aufruf (insbesondere externe API-Aufrufe) für Audits und Performance-Analysen.
    Arbeitet extrem schnell (< 1ms) und blockiert keine Requests.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO api_calls (
                endpoint, method, status_code, response_time_ms, client_ip, ip_hash,
                user_agent, auth_type, api_key_name, is_external, query_params, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (endpoint or "")[:191],
                (method or "GET").upper()[:16],
                int(status_code),
                round(float(response_time_ms), 2),
                (client_ip or "")[:64],
                (ip_hash or "")[:64],
                (user_agent or "")[:500],
                (auth_type or "none")[:32],
                (api_key_name or "")[:64],
                int(is_external),
                (query_params or "")[:500],
                now_str,
            ),
        )


def get_api_analytics_overview(
    period: str = "today",
    only_external: bool = True,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Aggregiert API-Aufrufe, externe Consumer, Statuscodes, Latenzen und Endpunkt-Verteilungen.
    """
    cutoff = _get_period_cutoff(period)
    ext_condition = "AND is_external = 1" if only_external else ""

    def _execute_queries(db_conn):
        # 1. KPIs
        row_kpi = db_conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_calls,
                COUNT(DISTINCT ip_hash) AS unique_callers,
                COALESCE(AVG(response_time_ms), 0.0) AS avg_latency,
                SUM(CASE WHEN status_code >= 200 AND status_code < 300 THEN 1 ELSE 0 END) AS status_2xx,
                SUM(CASE WHEN status_code >= 400 AND status_code < 500 THEN 1 ELSE 0 END) AS status_4xx,
                SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS status_5xx,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_calls,
                SUM(CASE WHEN auth_type = 'api_key' THEN 1 ELSE 0 END) AS auth_api_key,
                SUM(CASE WHEN auth_type = 'bearer' THEN 1 ELSE 0 END) AS auth_bearer,
                SUM(CASE WHEN auth_type = 'session' THEN 1 ELSE 0 END) AS auth_session,
                SUM(CASE WHEN auth_type = 'none' OR auth_type = '' THEN 1 ELSE 0 END) AS auth_none
            FROM api_calls
            WHERE (? IS NULL OR created_at >= ?) {ext_condition}
            """,
            (cutoff, cutoff),
        ).fetchone()

        total_calls = int(row_kpi["total_calls"] or 0) if row_kpi else 0
        unique_callers = int(row_kpi["unique_callers"] or 0) if row_kpi else 0
        avg_latency = round(float(row_kpi["avg_latency"] or 0.0), 1) if row_kpi else 0.0
        status_2xx = int(row_kpi["status_2xx"] or 0) if row_kpi else 0
        status_4xx = int(row_kpi["status_4xx"] or 0) if row_kpi else 0
        status_5xx = int(row_kpi["status_5xx"] or 0) if row_kpi else 0
        error_calls = int(row_kpi["error_calls"] or 0) if row_kpi else 0
        error_rate_pct = round((error_calls / total_calls * 100), 1) if total_calls > 0 else 0.0

        auth_breakdown = {
            "api_key": int(row_kpi["auth_api_key"] or 0) if row_kpi else 0,
            "bearer": int(row_kpi["auth_bearer"] or 0) if row_kpi else 0,
            "session": int(row_kpi["auth_session"] or 0) if row_kpi else 0,
            "none": int(row_kpi["auth_none"] or 0) if row_kpi else 0,
        }

        # 2. Timeline
        is_hourly = period in ("24h", "today")
        substr_len = 13 if is_hourly else 10
        timeline_rows = db_conn.execute(
            f"""
            SELECT
                SUBSTR(created_at, 1, {substr_len}) AS bucket,
                COUNT(*) AS calls,
                COUNT(DISTINCT ip_hash) AS callers,
                ROUND(AVG(response_time_ms), 1) AS avg_ms,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
            FROM api_calls
            WHERE (? IS NULL OR created_at >= ?) {ext_condition}
            GROUP BY SUBSTR(created_at, 1, {substr_len})
            ORDER BY bucket ASC
            """,
            (cutoff, cutoff),
        ).fetchall()

        timeline = []
        for tr in timeline_rows:
            b = tr["bucket"]
            c = int(tr["calls"] or 0)
            vis = int(tr["callers"] or 0)
            ms = float(tr["avg_ms"] or 0.0)
            errs = int(tr["errors"] or 0)

            if is_hourly:
                parts = b.replace("T", " ").split(" ")
                time_part = f"{parts[1]}:00" if len(parts) > 1 else b
                label = time_part if period == "today" else f"{parts[0][5:]} {time_part}"
            else:
                label = f"{b[8:10]}.{b[5:7]}." if len(b) >= 10 else b

            timeline.append({
                "bucket": b,
                "label": label,
                "calls": c,
                "callers": vis,
                "avg_ms": ms,
                "errors": errs,
            })

        # 3. Top Endpoints
        endpoint_rows = db_conn.execute(
            f"""
            SELECT
                endpoint,
                method,
                COUNT(*) AS count,
                COUNT(DISTINCT ip_hash) AS unique_callers,
                ROUND(AVG(response_time_ms), 1) AS avg_ms,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
            FROM api_calls
            WHERE (? IS NULL OR created_at >= ?) {ext_condition}
            GROUP BY endpoint, method
            ORDER BY count DESC
            LIMIT 25
            """,
            (cutoff, cutoff),
        ).fetchall()
        endpoints = [
            {
                "endpoint": r["endpoint"],
                "method": r["method"],
                "count": int(r["count"] or 0),
                "unique_callers": int(r["unique_callers"] or 0),
                "avg_ms": float(r["avg_ms"] or 0.0),
                "errors": int(r["errors"] or 0),
            }
            for r in endpoint_rows
        ]

        # 4. Top Consumers (by IP Hash / User-Agent)
        consumer_rows = db_conn.execute(
            f"""
            SELECT
                ip_hash,
                MAX(user_agent) AS user_agent,
                MAX(auth_type) AS auth_type,
                MAX(api_key_name) AS api_key_name,
                COUNT(*) AS call_count,
                MAX(created_at) AS last_seen,
                ROUND(AVG(response_time_ms), 1) AS avg_ms,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count
            FROM api_calls
            WHERE (? IS NULL OR created_at >= ?) {ext_condition}
            GROUP BY ip_hash
            ORDER BY call_count DESC
            LIMIT 20
            """,
            (cutoff, cutoff),
        ).fetchall()
        consumers = [
            {
                "ip_hash": r["ip_hash"],
                "user_agent": r["user_agent"] or "Unbekannt",
                "auth_type": r["auth_type"] or "none",
                "api_key_name": r["api_key_name"] or "-",
                "call_count": int(r["call_count"] or 0),
                "last_seen": r["last_seen"],
                "avg_ms": float(r["avg_ms"] or 0.0),
                "error_count": int(r["error_count"] or 0),
            }
            for r in consumer_rows
        ]

        # 5. Recent API Calls (Latest 50 calls)
        recent_call_rows = db_conn.execute(
            f"""
            SELECT
                id, endpoint, method, status_code, response_time_ms,
                client_ip, ip_hash, user_agent, auth_type, api_key_name,
                is_external, query_params, created_at
            FROM api_calls
            WHERE (? IS NULL OR created_at >= ?) {ext_condition}
            ORDER BY id DESC
            LIMIT 50
            """,
            (cutoff, cutoff),
        ).fetchall()
        recent_calls = []
        for r in recent_call_rows:
            ip = r["client_ip"] or ""
            if "." in ip:
                ip_parts = ip.split(".")
                masked_ip = f"{ip_parts[0]}.{ip_parts[1]}.***.***" if len(ip_parts) >= 2 else ip
            elif ":" in ip:
                ip_parts = ip.split(":")
                masked_ip = f"{ip_parts[0]}:{ip_parts[1]}:***" if len(ip_parts) >= 2 else ip
            else:
                masked_ip = ip or "-"

            recent_calls.append({
                "id": r["id"],
                "endpoint": r["endpoint"],
                "method": r["method"],
                "status_code": int(r["status_code"] or 200),
                "response_time_ms": float(r["response_time_ms"] or 0.0),
                "client_ip_masked": masked_ip,
                "ip_hash": r["ip_hash"],
                "user_agent": r["user_agent"] or "-",
                "auth_type": r["auth_type"] or "none",
                "api_key_name": r["api_key_name"] or "-",
                "is_external": int(r["is_external"] or 1),
                "query_params": r["query_params"] or "",
                "created_at": r["created_at"],
            })

        return {
            "period": period,
            "only_external": only_external,
            "kpis": {
                "total_calls": total_calls,
                "unique_callers": unique_callers,
                "avg_latency": avg_latency,
                "status_2xx": status_2xx,
                "status_4xx": status_4xx,
                "status_5xx": status_5xx,
                "error_calls": error_calls,
                "error_rate_pct": error_rate_pct,
                "auth_breakdown": auth_breakdown,
            },
            "timeline": timeline,
            "endpoints": endpoints,
            "consumers": consumers,
            "recent_calls": recent_calls,
        }

    if conn is not None:
        return _execute_queries(conn)
    with get_db() as c:
        return _execute_queries(c)


def get_site_analytics_overview(period: str = "today") -> Dict[str, Any]:
    """
    Aggregiert Web-Traffic, Seitenbesucher, Latenz und Bot-Sessions für das Analyse-Dashboard.
    """
    cutoff = _get_period_cutoff(period)
    with get_db() as conn:
        # 1. KPIs
        row_kpi = conn.execute(
            """
            SELECT
                COUNT(*) AS total_views,
                COUNT(DISTINCT visitor_hash) AS unique_visitors,
                COALESCE(AVG(response_time_ms), 0.0) AS avg_latency,
                SUM(CASE WHEN device_type = 'mobile' THEN 1 ELSE 0 END) AS mobile_views,
                SUM(CASE WHEN device_type = 'desktop' THEN 1 ELSE 0 END) AS desktop_views,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_views
            FROM page_views
            WHERE (? IS NULL OR created_at >= ?)
            """,
            (cutoff, cutoff),
        ).fetchone()

        total_views = int(row_kpi["total_views"] or 0) if row_kpi else 0
        unique_visitors = int(row_kpi["unique_visitors"] or 0) if row_kpi else 0
        avg_latency = round(float(row_kpi["avg_latency"] or 0.0), 1) if row_kpi else 0.0
        mobile_views = int(row_kpi["mobile_views"] or 0) if row_kpi else 0
        desktop_views = int(row_kpi["desktop_views"] or 0) if row_kpi else 0
        error_views = int(row_kpi["error_views"] or 0) if row_kpi else 0

        # 2. Timeline
        is_hourly = period in ("24h", "today")
        substr_len = 13 if is_hourly else 10
        timeline_rows = conn.execute(
            f"""
            SELECT
                SUBSTR(created_at, 1, {substr_len}) AS bucket,
                COUNT(*) AS views,
                COUNT(DISTINCT visitor_hash) AS visitors,
                ROUND(AVG(response_time_ms), 1) AS avg_ms
            FROM page_views
            WHERE (? IS NULL OR created_at >= ?)
            GROUP BY SUBSTR(created_at, 1, {substr_len})
            ORDER BY bucket ASC
            """,
            (cutoff, cutoff),
        ).fetchall()

        timeline = []
        for tr in timeline_rows:
            b = tr["bucket"]
            v = int(tr["views"] or 0)
            vis = int(tr["visitors"] or 0)
            ms = float(tr["avg_ms"] or 0.0)

            if is_hourly:
                parts = b.replace("T", " ").split(" ")
                time_part = f"{parts[1]}:00" if len(parts) > 1 else b
                label = time_part if period == "today" else f"{parts[0][5:]} {time_part}"
            else:
                label = f"{b[8:10]}.{b[5:7]}." if len(b) >= 10 else b

            timeline.append({
                "bucket": b,
                "label": label,
                "views": v,
                "visitors": vis,
                "avg_ms": ms,
            })

        # 3. Top Paths
        paths_rows = conn.execute(
            """
            SELECT
                path,
                COUNT(*) AS views,
                COUNT(DISTINCT visitor_hash) AS visitors,
                ROUND(AVG(response_time_ms), 1) AS avg_ms
            FROM page_views
            WHERE (? IS NULL OR created_at >= ?)
            GROUP BY path
            ORDER BY views DESC
            LIMIT 20
            """,
            (cutoff, cutoff),
        ).fetchall()
        paths = [
            {
                "path": r["path"],
                "views": int(r["views"] or 0),
                "visitors": int(r["visitors"] or 0),
                "avg_ms": float(r["avg_ms"] or 0.0),
            }
            for r in paths_rows
        ]

        # 4. Devices
        device_rows = conn.execute(
            """
            SELECT
                device_type,
                COUNT(*) AS count,
                COUNT(DISTINCT visitor_hash) AS visitors
            FROM page_views
            WHERE (? IS NULL OR created_at >= ?)
            GROUP BY device_type
            ORDER BY count DESC
            """,
            (cutoff, cutoff),
        ).fetchall()
        devices = [
            {"device": r["device_type"], "count": int(r["count"] or 0), "visitors": int(r["visitors"] or 0)}
            for r in device_rows
        ]

        # 5. Top Referrers
        referrer_rows = conn.execute(
            """
            SELECT
                referrer,
                COUNT(*) AS count
            FROM page_views
            WHERE (? IS NULL OR created_at >= ?)
              AND referrer != ''
            GROUP BY referrer
            ORDER BY count DESC
            LIMIT 15
            """,
            (cutoff, cutoff),
        ).fetchall()
        referrers = [{"referrer": r["referrer"], "count": int(r["count"] or 0)} for r in referrer_rows]

        # 6. Recent Views (latest 50)
        recent_rows = conn.execute(
            """
            SELECT id, path, visitor_hash, device_type, referrer, status_code, response_time_ms, created_at
            FROM page_views
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()
        recent_views = [
            {
                "id": r["id"],
                "path": r["path"],
                "visitor_hash": r["visitor_hash"],
                "device_type": r["device_type"],
                "referrer": r["referrer"] or "-",
                "status_code": int(r["status_code"] or 200),
                "response_time_ms": float(r["response_time_ms"] or 0.0),
                "created_at": r["created_at"],
            }
            for r in recent_rows
        ]

        # 7. Bot Sessions (recent 50)
        bot_session_rows = conn.execute(
            """
            SELECT * FROM bot_sessions
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()
        bot_sessions = [dict(r) for r in bot_session_rows]

        # 8. Telegram Users Overview
        tg_users = list_telegram_users()

        # 9. Externe API-Statistiken
        api_analytics = get_api_analytics_overview(period=period, only_external=True, conn=conn)

        return {
            "period": period,
            "kpis": {
                "total_views": total_views,
                "unique_visitors": unique_visitors,
                "avg_latency": avg_latency,
                "mobile_views": mobile_views,
                "desktop_views": desktop_views,
                "error_views": error_views,
            },
            "timeline": timeline,
            "paths": paths,
            "devices": devices,
            "referrers": referrers,
            "recent_views": recent_views,
            "bot_sessions": bot_sessions,
            "telegram_users": tg_users,
            "api_analytics": api_analytics,
        }
