"""
TokTracker - TikTok-Battles: Start, Scores, Abschluss und Auswertungen.
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
from shared.db.settings import get_settings


def record_battle_start(
    streamer_id: int,
    battle_id: str,
    opponent_username: str = "",
    opponent_display_name: str = "",
    opponent_avatar_url: str = "",
    opponent_user_id: str = "",
    session_id: Optional[int] = None,
    duration_seconds: int = 300,
    started_at: Optional[str] = None,
    battle_mode: str = "1v1",
    teammate_user_id: str = "",
    teammate_username: str = "",
    teammate_display_name: str = "",
    teammate_avatar_url: str = "",
    opponent2_user_id: str = "",
    opponent2_username: str = "",
    opponent2_display_name: str = "",
    opponent2_avatar_url: str = "",
    opponent3_user_id: str = "",
    opponent3_username: str = "",
    opponent3_display_name: str = "",
    opponent3_avatar_url: str = "",
    streamer_rank: int = 0,
) -> int:
    """
    Registriert den Start eines TikTok Battles (1v1, 2v2, 1v1v1 Dreier oder 1v1v1v1 4er-Einzel) in der Datenbank.
    Gibt die lokale Datenbank-ID (id) des Battle-Eintrags zurück.
    """
    started_at = started_at or datetime.now().isoformat(timespec="seconds")
    created_at = started_at

    with get_db() as conn:
        # Falls battle_id leer oder nur ein Zeitstempel ist: Prüfen, ob der getrackte Gegner bereits ein aktives Battle gestartet hat
        if opponent_username and (not battle_id or len(str(battle_id)) < 8):
            my_row = conn.execute("SELECT username FROM streamers WHERE id = ?", (streamer_id,)).fetchone()
            if my_row:
                my_uname = str(my_row["username"] or "").lower()
                partner_active = conn.execute(
                    """
                    SELECT battle_id FROM tiktok_battles
                    WHERE LOWER(opponent_username) = ? AND status = 'active'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (my_uname,),
                ).fetchone()
                if partner_active and partner_active["battle_id"]:
                    battle_id = partner_active["battle_id"]

        existing = conn.execute(
            """
            SELECT id, status, battle_mode, opponent_username, teammate_username, opponent2_username, opponent3_username FROM tiktok_battles
            WHERE streamer_id = ? AND battle_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (streamer_id, str(battle_id)),
        ).fetchone()
        if existing:
            # Wenn bereits beendet, nur fehlende Metadaten nachtragen, aber Status nicht zurücksetzen
            if existing["status"] == "finished":
                conn.execute(
                    """
                    UPDATE tiktok_battles
                    SET battle_mode = CASE WHEN (battle_mode IS NULL OR battle_mode = '1v1') AND ? != '1v1' THEN ? ELSE battle_mode END,
                        opponent_username = CASE WHEN (opponent_username IS NULL OR opponent_username = '') THEN ? ELSE opponent_username END,
                        opponent_display_name = CASE WHEN (opponent_display_name IS NULL OR opponent_display_name = '') THEN ? ELSE opponent_display_name END,
                        opponent_avatar_url = CASE WHEN (opponent_avatar_url IS NULL OR opponent_avatar_url = '') THEN ? ELSE opponent_avatar_url END,
                        opponent2_username = CASE WHEN (opponent2_username IS NULL OR opponent2_username = '') THEN ? ELSE opponent2_username END,
                        opponent2_display_name = CASE WHEN (opponent2_display_name IS NULL OR opponent2_display_name = '') THEN ? ELSE opponent2_display_name END,
                        opponent2_avatar_url = CASE WHEN (opponent2_avatar_url IS NULL OR opponent2_avatar_url = '') THEN ? ELSE opponent2_avatar_url END,
                        opponent3_username = CASE WHEN (opponent3_username IS NULL OR opponent3_username = '') THEN ? ELSE opponent3_username END,
                        opponent3_display_name = CASE WHEN (opponent3_display_name IS NULL OR opponent3_display_name = '') THEN ? ELSE opponent3_display_name END,
                        opponent3_avatar_url = CASE WHEN (opponent3_avatar_url IS NULL OR opponent3_avatar_url = '') THEN ? ELSE opponent3_avatar_url END
                    WHERE id = ?
                    """,
                    (
                        battle_mode, battle_mode,
                        str(opponent_username or ""), str(opponent_display_name or opponent_username or ""), str(opponent_avatar_url or ""),
                        str(opponent2_username or ""), str(opponent2_display_name or opponent2_username or ""), str(opponent2_avatar_url or ""),
                        str(opponent3_username or ""), str(opponent3_display_name or opponent3_username or ""), str(opponent3_avatar_url or ""),
                        int(existing["id"]),
                    ),
                )
                return int(existing["id"])

            # Nachträgliche Aktualisierung für noch aktives Battle
            conn.execute(
                """
                UPDATE tiktok_battles
                SET battle_mode = CASE WHEN (battle_mode IS NULL OR battle_mode = '1v1') AND ? != '1v1' THEN ? ELSE battle_mode END,
                    opponent_username = CASE WHEN (opponent_username IS NULL OR opponent_username = '') THEN ? ELSE opponent_username END,
                    opponent_display_name = CASE WHEN (opponent_display_name IS NULL OR opponent_display_name = '') THEN ? ELSE opponent_display_name END,
                    opponent_avatar_url = CASE WHEN (opponent_avatar_url IS NULL OR opponent_avatar_url = '') THEN ? ELSE opponent_avatar_url END,
                    opponent_user_id = CASE WHEN (opponent_user_id IS NULL OR opponent_user_id = '') THEN ? ELSE opponent_user_id END,
                    teammate_username = CASE WHEN (teammate_username IS NULL OR teammate_username = '') THEN ? ELSE teammate_username END,
                    teammate_display_name = CASE WHEN (teammate_display_name IS NULL OR teammate_display_name = '') THEN ? ELSE teammate_display_name END,
                    teammate_avatar_url = CASE WHEN (teammate_avatar_url IS NULL OR teammate_avatar_url = '') THEN ? ELSE teammate_avatar_url END,
                    teammate_user_id = CASE WHEN (teammate_user_id IS NULL OR teammate_user_id = '') THEN ? ELSE teammate_user_id END,
                    opponent2_username = CASE WHEN (opponent2_username IS NULL OR opponent2_username = '') THEN ? ELSE opponent2_username END,
                    opponent2_display_name = CASE WHEN (opponent2_display_name IS NULL OR opponent2_display_name = '') THEN ? ELSE opponent2_display_name END,
                    opponent2_avatar_url = CASE WHEN (opponent2_avatar_url IS NULL OR opponent2_avatar_url = '') THEN ? ELSE opponent2_avatar_url END,
                    opponent2_user_id = CASE WHEN (opponent2_user_id IS NULL OR opponent2_user_id = '') THEN ? ELSE opponent2_user_id END,
                    opponent3_username = CASE WHEN (opponent3_username IS NULL OR opponent3_username = '') THEN ? ELSE opponent3_username END,
                    opponent3_display_name = CASE WHEN (opponent3_display_name IS NULL OR opponent3_display_name = '') THEN ? ELSE opponent3_display_name END,
                    opponent3_avatar_url = CASE WHEN (opponent3_avatar_url IS NULL OR opponent3_avatar_url = '') THEN ? ELSE opponent3_avatar_url END,
                    opponent3_user_id = CASE WHEN (opponent3_user_id IS NULL OR opponent3_user_id = '') THEN ? ELSE opponent3_user_id END,
                    streamer_rank = CASE WHEN (streamer_rank IS NULL OR streamer_rank = 0) AND ? > 0 THEN ? ELSE streamer_rank END
                WHERE id = ?
                """,
                (
                    battle_mode, battle_mode,
                    str(opponent_username or ""), str(opponent_display_name or opponent_username or ""),
                    str(opponent_avatar_url or ""), str(opponent_user_id or ""),
                    str(teammate_username or ""), str(teammate_display_name or teammate_username or ""),
                    str(teammate_avatar_url or ""), str(teammate_user_id or ""),
                    str(opponent2_username or ""), str(opponent2_display_name or opponent2_username or ""),
                    str(opponent2_avatar_url or ""), str(opponent2_user_id or ""),
                    str(opponent3_username or ""), str(opponent3_display_name or opponent3_username or ""),
                    str(opponent3_avatar_url or ""), str(opponent3_user_id or ""),
                    int(streamer_rank or 0), int(streamer_rank or 0),
                    int(existing["id"]),
                ),
            )
            return int(existing["id"])

        cursor = conn.execute(
            """
            INSERT INTO tiktok_battles (
                streamer_id, session_id, battle_id, opponent_user_id,
                opponent_username, opponent_display_name, opponent_avatar_url,
                started_at, duration_seconds, streamer_score, opponent_score,
                result, status, created_at,
                battle_mode, teammate_user_id, teammate_username, teammate_display_name,
                teammate_avatar_url, teammate_score, opponent2_user_id, opponent2_username,
                opponent2_display_name, opponent2_avatar_url, opponent2_score,
                opponent3_user_id, opponent3_username, opponent3_display_name,
                opponent3_avatar_url, opponent3_score, streamer_rank
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, 0, 0,
                'ONGOING', 'active', ?,
                ?, ?, ?, ?,
                ?, 0, ?, ?,
                ?, ?, 0,
                ?, ?, ?,
                ?, 0, ?
            )
            """,
            (
                streamer_id,
                session_id,
                str(battle_id),
                str(opponent_user_id or ""),
                str(opponent_username or ""),
                str(opponent_display_name or opponent_username or ""),
                str(opponent_avatar_url or ""),
                started_at,
                int(duration_seconds or 300),
                created_at,
                str(battle_mode or "1v1"),
                str(teammate_user_id or ""),
                str(teammate_username or ""),
                str(teammate_display_name or teammate_username or ""),
                str(teammate_avatar_url or ""),
                str(opponent2_user_id or ""),
                str(opponent2_username or ""),
                str(opponent2_display_name or opponent2_username or ""),
                str(opponent2_avatar_url or ""),
                str(opponent3_user_id or ""),
                str(opponent3_username or ""),
                str(opponent3_display_name or opponent3_username or ""),
                str(opponent3_avatar_url or ""),
                int(streamer_rank or 0),
            ),
        )
        return int(cursor.lastrowid)


def update_battle_scores(
    battle_db_id: int,
    streamer_score: int,
    opponent_score: int,
    streamer_mvp_name: Optional[str] = None,
    streamer_mvp_score: Optional[int] = None,
    streamer_mvp_avatar: Optional[str] = None,
    opponent_mvp_name: Optional[str] = None,
    opponent_mvp_score: Optional[int] = None,
    opponent_mvp_avatar: Optional[str] = None,
    teammate_score: Optional[int] = None,
    opponent2_score: Optional[int] = None,
    opponent3_score: Optional[int] = None,
    streamer_rank: Optional[int] = None,
    battle_mode: Optional[str] = None,
    raw_data_json: Optional[str] = None,
) -> None:
    """
    Aktualisiert fortlaufende Zwischenstände und MVP-Spender während eines aktiven Battles (1v1, 2v2, 1v1v1 oder 1v1v1v1).
    """
    with get_db() as conn:
        conn.execute(
            """
            UPDATE tiktok_battles
            SET streamer_score = ?,
                opponent_score = ?,
                teammate_score = COALESCE(?, teammate_score),
                opponent2_score = COALESCE(?, opponent2_score),
                opponent3_score = COALESCE(?, opponent3_score),
                streamer_rank = COALESCE(?, streamer_rank),
                battle_mode = COALESCE(?, battle_mode),
                streamer_mvp_name = COALESCE(?, streamer_mvp_name),
                streamer_mvp_score = COALESCE(?, streamer_mvp_score),
                streamer_mvp_avatar = COALESCE(?, streamer_mvp_avatar),
                opponent_mvp_name = COALESCE(?, opponent_mvp_name),
                opponent_mvp_score = COALESCE(?, opponent_mvp_score),
                opponent_mvp_avatar = COALESCE(?, opponent_mvp_avatar),
                raw_data_json = COALESCE(?, raw_data_json)
            WHERE id = ?
            """,
            (
                int(streamer_score),
                int(opponent_score),
                teammate_score,
                opponent2_score,
                opponent3_score,
                streamer_rank,
                battle_mode,
                streamer_mvp_name,
                streamer_mvp_score,
                streamer_mvp_avatar,
                opponent_mvp_name,
                opponent_mvp_score,
                opponent_mvp_avatar,
                raw_data_json,
                battle_db_id,
            ),
        )


def record_battle_finish(
    battle_db_id: int,
    streamer_score: int,
    opponent_score: int,
    result: Optional[str] = None,
    streamer_mvp_name: str = "",
    streamer_mvp_score: int = 0,
    streamer_mvp_avatar: str = "",
    opponent_mvp_name: str = "",
    opponent_mvp_score: int = 0,
    opponent_mvp_avatar: str = "",
    teammate_score: Optional[int] = None,
    opponent2_score: Optional[int] = None,
    opponent3_score: Optional[int] = None,
    streamer_rank: Optional[int] = None,
    battle_mode: Optional[str] = None,
    raw_data_json: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Schließt ein Battle ab (1v1, 2v2, 1v1v1 oder 1v1v1v1), ermittelt Sieger/Verlierer/Platzierung,
    aggregiert während des Duells generierte Geschenke/Coins/EUR und speichert den Endstand.
    """
    ended_at = ended_at or datetime.now().isoformat(timespec="seconds")
    cfg = get_settings()

    # Platzierungs- und Ergebnisermittlung für Free-for-all Modi (1v1v1 und 1v1v1v1)
    if battle_mode in ("1v1v1", "1v1v1v1"):
        scores = [("streamer", streamer_score), ("opp1", opponent_score), ("opp2", opponent2_score or 0)]
        if battle_mode == "1v1v1v1":
            scores.append(("opp3", opponent3_score or 0))
        scores_sorted = sorted(scores, key=lambda x: x[1], reverse=True)
        computed_rank = 1
        for idx, (who, _) in enumerate(scores_sorted):
            if who == "streamer":
                computed_rank = idx + 1
                break
        streamer_rank = streamer_rank or computed_rank

        if not result or result == "ONGOING":
            if streamer_rank == 1:
                # Prüfen auf Gleichstand mit Platz 2
                if len(scores_sorted) > 1 and scores_sorted[0][1] == scores_sorted[1][1] and scores_sorted[0][1] > 0:
                    result = "DRAW"
                else:
                    result = "WIN"
            else:
                result = "LOSE"
    elif not result or result == "ONGOING":
        if streamer_score > opponent_score:
            result = "WIN"
        elif streamer_score < opponent_score:
            result = "LOSE"
        else:
            result = "DRAW"

    with get_db() as conn:
        b_row = conn.execute(
            "SELECT * FROM tiktok_battles WHERE id = ?", (battle_db_id,)
        ).fetchone()
        if not b_row:
            return {}

        streamer_id = b_row["streamer_id"]
        started_at = b_row["started_at"]

        # Gifts während des Duell-Fensters aufsummieren
        gift_agg = conn.execute(
            """
            SELECT COALESCE(SUM(total_coins), 0) AS coins
            FROM gift_events
            WHERE streamer_id = ? AND created_at >= ? AND created_at <= ?
            """,
            (streamer_id, started_at, ended_at),
        ).fetchone()

        coins_earned = int(gift_agg["coins"] or 0) if gift_agg else 0
        usd_net = round(coins_earned * cfg["usd_per_diamond"], 2)
        eur_net = round(usd_net * cfg["usd_to_eur_rate"], 2)
        usd_gross = round(coins_earned * cfg["gross_usd_per_coin"], 2)
        eur_gross = round(usd_gross * cfg["usd_to_eur_rate"], 2)

        duration_sec = b_row["duration_seconds"] or 300
        try:
            s_dt = datetime.fromisoformat(started_at)
            e_dt = datetime.fromisoformat(ended_at)
            duration_sec = max(1, int(round((e_dt - s_dt).total_seconds())))
        except Exception:
            pass

        conn.execute(
            """
            UPDATE tiktok_battles
            SET streamer_score = ?,
                opponent_score = ?,
                teammate_score = COALESCE(?, teammate_score),
                opponent2_score = COALESCE(?, opponent2_score),
                opponent3_score = COALESCE(?, opponent3_score),
                streamer_rank = COALESCE(?, streamer_rank),
                battle_mode = COALESCE(?, battle_mode),
                result = ?,
                streamer_mvp_name = ?,
                streamer_mvp_score = ?,
                streamer_mvp_avatar = ?,
                opponent_mvp_name = ?,
                opponent_mvp_score = ?,
                opponent_mvp_avatar = ?,
                coins_earned = ?,
                usd_net = ?,
                eur_net = ?,
                usd_gross = ?,
                eur_gross = ?,
                duration_seconds = ?,
                ended_at = ?,
                status = 'finished',
                raw_data_json = COALESCE(?, raw_data_json)
            WHERE id = ?
            """,
            (
                int(streamer_score),
                int(opponent_score),
                teammate_score,
                opponent2_score,
                opponent3_score,
                streamer_rank,
                battle_mode,
                result,
                streamer_mvp_name or b_row["streamer_mvp_name"] or "",
                int(streamer_mvp_score or b_row["streamer_mvp_score"] or 0),
                streamer_mvp_avatar or b_row["streamer_mvp_avatar"] or "",
                opponent_mvp_name or b_row["opponent_mvp_name"] or "",
                int(opponent_mvp_score or b_row["opponent_mvp_score"] or 0),
                opponent_mvp_avatar or b_row["opponent_mvp_avatar"] or "",
                coins_earned,
                usd_net,
                eur_net,
                usd_gross,
                eur_gross,
                duration_sec,
                ended_at,
                raw_data_json,
                battle_db_id,
            ),
        )

        updated_row = conn.execute(
            "SELECT * FROM tiktok_battles WHERE id = ?", (battle_db_id,)
        ).fetchone()
        return dict(updated_row) if updated_row else {}


def get_battles_list(
    streamer_id: Optional[int] = None,
    period: str = "all",
    result_filter: Optional[str] = None,
    mode_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Liefert paginierte Liste aller erfassten Battles mit Streamer- und Gegnerdetails.
    Unterstützt 1v1, 2v2, 1v1v1 und 1v1v1v1 Matches und gezielte Filterung nach Modus.
    Erkennt interne Duelle zwischen zwei getrackten Streamern und konsolidiert diese ohne Doppelung.
    """
    cutoff = _get_period_cutoff(period)
    where_clauses: List[str] = []
    params: List[Any] = []

    if streamer_id:
        where_clauses.append("b.streamer_id = ?")
        params.append(streamer_id)
    else:
        # In der Gesamtansicht: Duplikate von internen Duellen herausfiltern (nur kanonische Zeile mit MIN(id))
        where_clauses.append(
            "(b.battle_id = '' OR b.id = (SELECT MIN(b2.id) FROM tiktok_battles b2 WHERE b2.battle_id = b.battle_id))"
        )
    if cutoff:
        where_clauses.append("b.created_at >= ?")
        params.append(cutoff)
    if result_filter and result_filter.upper() != "ALL":
        where_clauses.append("b.result = ?")
        params.append(result_filter.upper())
    if mode_filter and mode_filter.upper() != "ALL":
        where_clauses.append("b.battle_mode = ?")
        params.append(mode_filter.lower())
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(b.opponent_username) LIKE ? OR LOWER(b.opponent_display_name) LIKE ? "
            "OR LOWER(b.teammate_username) LIKE ? OR LOWER(b.teammate_display_name) LIKE ? "
            "OR LOWER(b.opponent2_username) LIKE ? OR LOWER(b.opponent2_display_name) LIKE ? "
            "OR LOWER(b.opponent3_username) LIKE ? OR LOWER(b.opponent3_display_name) LIKE ?)"
        )
        params.extend([term, term, term, term, term, term, term, term])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_db() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(b.id) AS cnt FROM tiktok_battles b {where_sql}",
            tuple(params),
        ).fetchone()
        total_count = int(count_row["cnt"] or 0) if count_row else 0

        query_sql = f"""
            SELECT
                b.*,
                s.username AS streamer_username,
                s.display_name AS streamer_display_name,
                s.avatar_url AS streamer_avatar_url
            FROM tiktok_battles b
            JOIN streamers s ON s.id = b.streamer_id
            {where_sql}
            ORDER BY b.started_at DESC, b.id DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query_sql, tuple(params + [limit, offset])).fetchall()
        # `raw_data_json` ist internes TikTok-Payload: nie in Listen-Antworten ausliefern.
        raw_battles = []
        for r in rows:
            item = dict(r)
            item.pop("raw_data_json", None)
            raw_battles.append(item)

        # Getrackte Streamer zur schnellen Gegnererkennung laden
        all_streamers = conn.execute("SELECT id, username, display_name, avatar_url FROM streamers").fetchall()
        streamer_by_uname = {str(r["username"]).lower(): dict(r) for r in all_streamers}

        battles = []
        for b in raw_battles:
            opp_uname = str(b.get("opponent_username") or "").lower()
            is_opp_tracked = opp_uname in streamer_by_uname
            b_id = str(b.get("battle_id") or "").strip()

            partner_row = None
            if b_id and b_id != "":
                p_res = conn.execute(
                    """
                    SELECT b.*, s.username AS streamer_username, s.display_name AS streamer_display_name, s.avatar_url AS streamer_avatar_url
                    FROM tiktok_battles b
                    JOIN streamers s ON s.id = b.streamer_id
                    WHERE b.battle_id = ? AND b.id != ?
                    LIMIT 1
                    """,
                    (b_id, b["id"]),
                ).fetchone()
                if p_res:
                    partner_row = dict(p_res)
                    partner_row.pop("raw_data_json", None)

            # Falls keine battle_id passte, aber Gegner getrackt ist: Zeitfenster prüfen (±180s)
            if not partner_row and is_opp_tracked:
                partner_streamer = streamer_by_uname[opp_uname]
                s_at = b.get("started_at") or b.get("created_at") or ""
                if s_at:
                    try:
                        s_dt = datetime.fromisoformat(s_at.replace("Z", ""))
                        win_start = (s_dt - timedelta(seconds=180)).isoformat(timespec="seconds")
                        win_end = (s_dt + timedelta(seconds=180)).isoformat(timespec="seconds")
                        p_res = conn.execute(
                            """
                            SELECT b.*, s.username AS streamer_username, s.display_name AS streamer_display_name, s.avatar_url AS streamer_avatar_url
                            FROM tiktok_battles b
                            JOIN streamers s ON s.id = b.streamer_id
                            WHERE b.streamer_id = ? AND LOWER(b.opponent_username) = ? AND b.id != ?
                              AND b.started_at >= ? AND b.started_at <= ?
                            ORDER BY b.id DESC LIMIT 1
                            """,
                            (partner_streamer["id"], str(b.get("streamer_username") or "").lower(), b["id"], win_start, win_end),
                        ).fetchone()
                        if p_res:
                            partner_row = dict(p_res)
                            partner_row.pop("raw_data_json", None)
                    except Exception:
                        pass

            is_ffa = str(b.get("battle_mode") or "").lower() in ("1v1v1", "1v1v1v1")
            if is_ffa:
                b["is_internal"] = False
                # Gegnerdetails anreichern, falls es getrackte Streamer sind
                for opp_key, dname_key, av_key in [
                    ("opponent_username", "opponent_display_name", "opponent_avatar_url"),
                    ("opponent2_username", "opponent2_display_name", "opponent2_avatar_url"),
                    ("opponent3_username", "opponent3_display_name", "opponent3_avatar_url"),
                ]:
                    u = str(b.get(opp_key) or "").lower()
                    if u in streamer_by_uname:
                        st = streamer_by_uname[u]
                        if not b.get(dname_key) or b.get(dname_key) == b.get(opp_key):
                            b[dname_key] = st.get("display_name") or b.get(dname_key)
                        if not b.get(av_key) or "/pictures/" in str(b.get(av_key)):
                            b[av_key] = st.get("avatar_url") or b.get(av_key)
            elif partner_row or is_opp_tracked:
                b["is_internal"] = True
                p = partner_row or {}
                partner_st = streamer_by_uname.get(opp_uname) or {}

                # Seite A und B bestimmen
                if streamer_id:
                    # In der Einzelstreamer-Ansicht bleibt der gewählte Streamer links (Seite A)
                    b["is_single_view"] = True
                    side_a_data = b
                    side_b_data = p
                    side_b_uname = p.get("streamer_username") or partner_st.get("username") or b.get("opponent_username")
                    side_b_dname = p.get("streamer_display_name") or partner_st.get("display_name") or b.get("opponent_display_name")
                    side_b_avatar = p.get("streamer_avatar_url") or partner_st.get("avatar_url") or b.get("opponent_avatar_url")
                    side_b_score = p.get("streamer_score", b.get("opponent_score", 0))
                    side_b_coins = p.get("coins_earned", 0)
                    side_b_eur = float(p.get("eur_net", 0.0))
                    side_b_id = p.get("streamer_id") or partner_st.get("id")
                else:
                    # In der Gesamtansicht: Der Streamer mit dem höheren Score (oder Seite A) kommt nach links
                    b["is_single_view"] = False
                    score_b = p.get("streamer_score", b.get("opponent_score", 0))
                    score_a = b.get("streamer_score", 0)
                    if score_b > score_a:
                        side_a_data = p
                        side_b_data = b
                        side_b_uname = b.get("streamer_username")
                        side_b_dname = b.get("streamer_display_name")
                        side_b_avatar = b.get("streamer_avatar_url")
                        side_b_score = score_a
                        side_b_coins = b.get("coins_earned", 0)
                        side_b_eur = float(b.get("eur_net", 0.0))
                        side_b_id = b.get("streamer_id")
                    else:
                        side_a_data = b
                        side_b_data = p
                        side_b_uname = p.get("streamer_username") or partner_st.get("username") or b.get("opponent_username")
                        side_b_dname = p.get("streamer_display_name") or partner_st.get("display_name") or b.get("opponent_display_name")
                        side_b_avatar = p.get("streamer_avatar_url") or partner_st.get("avatar_url") or b.get("opponent_avatar_url")
                        side_b_score = score_b
                        side_b_coins = p.get("coins_earned", 0)
                        side_b_eur = float(p.get("eur_net", 0.0))
                        side_b_id = p.get("streamer_id") or partner_st.get("id")

                coins_a = side_a_data.get("coins_earned", 0) or 0
                eur_a = float(side_a_data.get("eur_net", 0.0) or 0.0)
                tot_coins = coins_a + side_b_coins
                tot_eur = round(eur_a + side_b_eur, 2)

                b["total_coins"] = tot_coins
                b["total_eur_net"] = tot_eur
                b["coins_earned"] = tot_coins
                b["eur_net"] = tot_eur

                score_a_val = side_a_data.get("streamer_score", 0) or 0
                score_b_val = side_b_score or 0
                if score_a_val > score_b_val:
                    b["winner_username"] = side_a_data.get("streamer_username")
                    b["winner_display_name"] = side_a_data.get("streamer_display_name")
                elif score_b_val > score_a_val:
                    b["winner_username"] = side_b_uname
                    b["winner_display_name"] = side_b_dname
                else:
                    b["winner_username"] = None
                    b["winner_display_name"] = None

                b["streamer_a"] = {
                    "id": side_a_data.get("streamer_id"),
                    "username": side_a_data.get("streamer_username"),
                    "display_name": side_a_data.get("streamer_display_name"),
                    "avatar_url": side_a_data.get("streamer_avatar_url") or "/static/avatar_default.png",
                    "score": score_a_val,
                    "coins_earned": coins_a,
                    "eur_net": eur_a,
                    "mvp_name": side_a_data.get("streamer_mvp_name") or "",
                    "mvp_score": side_a_data.get("streamer_mvp_score") or 0,
                    "mvp_avatar": side_a_data.get("streamer_mvp_avatar") or "",
                    "result": side_a_data.get("result") or ("WIN" if score_a_val > score_b_val else ("LOSE" if score_a_val < score_b_val else "DRAW")),
                }

                b["streamer_b"] = {
                    "id": side_b_id,
                    "username": side_b_uname,
                    "display_name": side_b_dname,
                    "avatar_url": side_b_avatar or "/static/avatar_default.png",
                    "score": score_b_val,
                    "coins_earned": side_b_coins,
                    "eur_net": side_b_eur,
                    "mvp_name": side_b_data.get("streamer_mvp_name") or b.get("opponent_mvp_name") or "",
                    "mvp_score": side_b_data.get("streamer_mvp_score") or b.get("opponent_mvp_score") or 0,
                    "mvp_avatar": side_b_data.get("streamer_mvp_avatar") or b.get("opponent_mvp_avatar") or "",
                    "result": side_b_data.get("result") or ("WIN" if score_b_val > score_a_val else ("LOSE" if score_b_val < score_a_val else "DRAW")),
                }

                # Kompatibilitätsfelder
                b["streamer_username"] = b["streamer_a"]["username"]
                b["streamer_display_name"] = b["streamer_a"]["display_name"]
                b["streamer_avatar_url"] = b["streamer_a"]["avatar_url"]
                b["streamer_score"] = b["streamer_a"]["score"]

                b["opponent_username"] = b["streamer_b"]["username"]
                b["opponent_display_name"] = b["streamer_b"]["display_name"]
                b["opponent_avatar_url"] = b["streamer_b"]["avatar_url"]
                b["opponent_score"] = b["streamer_b"]["score"]
            else:
                b["is_internal"] = False

            battles.append(b)

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "battles": battles,
    }


def get_battle_stats(
    streamer_id: Optional[int] = None,
    period: str = "all",
) -> Dict[str, Any]:
    """
    Liefert aggregierte Duell-Kennzahlen (Winrate, Duelle gesamt, Einnahmen, Top-Rivale).
    """
    cutoff = _get_period_cutoff(period)

    where_clauses: List[str] = []
    params: List[Any] = []
    if streamer_id:
        where_clauses.append("streamer_id = ?")
        params.append(streamer_id)
    if cutoff:
        where_clauses.append("created_at >= ?")
        params.append(cutoff)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total_expr = "COUNT(DISTINCT CASE WHEN battle_id != '' THEN battle_id ELSE id END)" if not streamer_id else "COUNT(id)"
    with get_db() as conn:
        agg = conn.execute(
            f"""
            SELECT
                {total_expr} AS total_battles,
                COALESCE(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN result = 'LOSE' THEN 1 ELSE 0 END), 0) AS losses,
                COALESCE(SUM(CASE WHEN result = 'DRAW' THEN 1 ELSE 0 END), 0) AS draws,
                COALESCE(SUM(CASE WHEN status = 'active' OR result = 'ONGOING' THEN 1 ELSE 0 END), 0) AS ongoing,
                COALESCE(SUM(coins_earned), 0) AS total_coins,
                COALESCE(SUM(eur_net), 0.0) AS total_eur_net,
                COALESCE(MAX(streamer_score), 0) AS max_streamer_score
            FROM tiktok_battles
            {where_sql}
            """,
            tuple(params),
        ).fetchone()

        total = int(agg["total_battles"] or 0)
        wins = int(agg["wins"] or 0)
        losses = int(agg["losses"] or 0)
        draws = int(agg["draws"] or 0)
        ongoing = int(agg["ongoing"] or 0)
        finished = wins + losses + draws
        winrate = round((wins / finished * 100), 1) if finished > 0 else 0.0

        # Top Rivals (Häufige Gegner & Head-to-Head)
        rival_where = ("WHERE " + " AND ".join(where_clauses + ["opponent_username != ''"])) if where_clauses else "WHERE opponent_username != ''"
        rival_rows = conn.execute(
            f"""
            SELECT
                opponent_username,
                MAX(opponent_display_name) AS opponent_display_name,
                MAX(opponent_avatar_url) AS opponent_avatar_url,
                COUNT(id) AS matches_count,
                COALESCE(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN result = 'LOSE' THEN 1 ELSE 0 END), 0) AS losses,
                COALESCE(SUM(CASE WHEN result = 'DRAW' THEN 1 ELSE 0 END), 0) AS draws,
                COALESCE(SUM(coins_earned), 0) AS total_coins,
                COALESCE(SUM(eur_net), 0.0) AS total_eur_net,
                AVG(streamer_score) AS avg_streamer_score,
                AVG(opponent_score) AS avg_opponent_score
            FROM tiktok_battles
            {rival_where}
            GROUP BY opponent_username
            ORDER BY matches_count DESC, total_coins DESC
            LIMIT 10
            """,
            tuple(params),
        ).fetchall()

        rivals = []
        for r in rival_rows:
            m_cnt = int(r["matches_count"] or 0)
            w_cnt = int(r["wins"] or 0)
            r_fin = w_cnt + int(r["losses"] or 0) + int(r["draws"] or 0)
            r_winrate = round((w_cnt / r_fin * 100), 1) if r_fin > 0 else 0.0
            rivals.append({
                "opponent_username": r["opponent_username"],
                "opponent_display_name": r["opponent_display_name"] or r["opponent_username"],
                "opponent_avatar_url": r["opponent_avatar_url"] or "",
                "matches_count": m_cnt,
                "wins": w_cnt,
                "losses": int(r["losses"] or 0),
                "draws": int(r["draws"] or 0),
                "winrate_pct": r_winrate,
                "total_coins": int(r["total_coins"] or 0),
                "total_eur_net": round(float(r["total_eur_net"] or 0.0), 2),
                "avg_streamer_score": int(round(r["avg_streamer_score"] or 0)),
                "avg_opponent_score": int(round(r["avg_opponent_score"] or 0)),
            })

    return {
        "total_battles": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "ongoing": ongoing,
        "winrate_pct": winrate,
        "total_coins": int(agg["total_coins"] or 0),
        "total_eur_net": round(float(agg["total_eur_net"] or 0.0), 2),
        "max_streamer_score": int(agg["max_streamer_score"] or 0),
        "top_opponent": rivals[0] if rivals else None,
        "rivals": rivals,
    }


def get_battle_details(
    battle_id: int,
    include_raw: bool = False,
    include_gifts: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Liefert vollständige Details eines Battles inkl. aller Geschenke, die während des Matches empfangen wurden.

    Args:
        include_raw: Rohes TikTok-Payload (`raw_data_json`) mitliefern (nur für Admin-Pfade).
        include_gifts: Geschenk-Liste (inkl. Spender-Namen) mitliefern.
    """
    with get_db() as conn:
        b_row = conn.execute(
            """
            SELECT
                b.*,
                s.username AS streamer_username,
                s.display_name AS streamer_display_name,
                s.avatar_url AS streamer_avatar_url
            FROM tiktok_battles b
            JOIN streamers s ON s.id = b.streamer_id
            WHERE b.id = ?
            """,
            (battle_id,),
        ).fetchone()
        if not b_row:
            return None

        battle = dict(b_row)
        if not include_raw:
            battle.pop("raw_data_json", None)

        gifts = []
        if include_gifts and battle.get("started_at") and battle.get("ended_at"):
            g_rows = conn.execute(
                """
                SELECT * FROM gift_events
                WHERE streamer_id = ? AND created_at >= ? AND created_at <= ?
                ORDER BY total_coins DESC, id DESC
                LIMIT 50
                """,
                (battle["streamer_id"], battle["started_at"], battle["ended_at"]),
            ).fetchall()
            gifts = [dict(g) for g in g_rows]

        # Partner-Battle prüfen falls internes Derby
        partner_row = None
        b_id = str(battle.get("battle_id") or "").strip()
        if b_id:
            p_res = conn.execute(
                """
                SELECT b.*, s.username AS streamer_username, s.display_name AS streamer_display_name, s.avatar_url AS streamer_avatar_url
                FROM tiktok_battles b
                JOIN streamers s ON s.id = b.streamer_id
                WHERE b.battle_id = ? AND b.id != ? LIMIT 1
                """,
                (b_id, battle["id"]),
            ).fetchone()
            if p_res:
                partner_row = dict(p_res)
                if not include_raw:
                    partner_row.pop("raw_data_json", None)

        if partner_row:
            battle["is_internal"] = True
            battle["partner_battle"] = partner_row
            battle["total_coins"] = (battle.get("coins_earned") or 0) + (partner_row.get("coins_earned") or 0)
            battle["total_eur_net"] = round(float(battle.get("eur_net") or 0.0) + float(partner_row.get("eur_net") or 0.0), 2)
            if include_gifts and battle.get("started_at") and battle.get("ended_at"):
                g2_rows = conn.execute(
                    """
                    SELECT * FROM gift_events
                    WHERE streamer_id = ? AND created_at >= ? AND created_at <= ?
                    ORDER BY total_coins DESC, id DESC
                    LIMIT 50
                    """,
                    (partner_row["streamer_id"], battle["started_at"], battle["ended_at"]),
                ).fetchall()
                for g in g2_rows:
                    dg = dict(g)
                    dg["recipient_username"] = partner_row["streamer_username"]
                    gifts.append(dg)
                gifts.sort(key=lambda x: -int(x.get("total_coins", 0)))

        battle["gifts"] = gifts
        return battle
