"""
TokTracker - Chat-Nachrichten, Wortwolken- und Phrasen-Analyse.
"""

import re
from collections import Counter
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


def batch_record_chat_messages(messages: List[Dict[str, Any]]) -> int:
    """
    Fügt einen Batch von Chatnachrichten mit einer einzigen Query performant ein.
    Wird vom StreamerWorker periodisch (alle 2s) aufgerufen.
    """
    if not messages:
        return 0

    now_default = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for m in messages:
        u_name = str(m.get("username") or "viewer").strip().lstrip("@")
        nick = str(m.get("nickname") or u_name).strip()
        c_text = str(m.get("comment") or "").strip()
        if not c_text:
            continue
        tier = str(m.get("whale_tier") or "")
        is_w = 1 if (m.get("is_whale") or tier) else 0
        rows.append((
            int(m["streamer_id"]),
            m.get("session_id"),
            str(m.get("user_id") or ""),
            u_name,
            nick,
            str(m.get("avatar_url") or ""),
            c_text,
            is_w,
            tier,
            m.get("created_at") or now_default,
        ))

    if not rows:
        return 0

    sql = """
    INSERT INTO chat_messages (
        streamer_id, session_id, user_id, username, nickname,
        avatar_url, comment, is_whale, whale_tier, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db() as conn:
        conn.executemany(sql, rows)
    return len(rows)


def cleanup_old_chat_messages(days: int = 7) -> int:
    """
    Rolling Retention: Löscht Chat-Nachrichten, die älter als `days` Tage sind (Standard: 7 Tage).
    Die aggregierten Spenderprofile und Geschenk-Events (gift_events) bleiben dauerhaft erhalten!
    """
    cutoff_dt = datetime.now() - timedelta(days=days)
    cutoff_iso = cutoff_dt.isoformat(timespec="seconds")
    cutoff_space = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM chat_messages WHERE created_at < ? OR created_at < ?",
            (cutoff_iso, cutoff_space),
        )
        return getattr(cur, "rowcount", 0) or 0


def _build_chat_search_clause(search: str) -> Tuple[Optional[str], List[Any]]:
    """
    Intelligente Such-Klausel für Chat-Logs:
    - Unterstützt '@nutzername' (sucht in username, nickname, comment-mentions und streamer)
    - Unterstützt '#id' (sucht nach exakter Nachrichten-ID)
    - Unterstützt reguläre Wörter und Phrasen
    - Mehrere Tokens werden mit AND kombiniert
    """
    raw = search.strip()
    if not raw:
        return None, []

    tokens = [t.strip() for t in raw.split() if t.strip()]
    if not tokens:
        return None, []

    clauses: List[str] = []
    params: List[Any] = []

    for token in tokens:
        if token.startswith("#") and token[1:].isdigit():
            clauses.append("c.id = ?")
            params.append(int(token[1:]))
        elif token.startswith("@"):
            clean_u = token.lstrip("@").lower()
            if clean_u:
                clauses.append("""(
                    LOWER(c.username) LIKE ?
                    OR LOWER(c.nickname) LIKE ?
                    OR LOWER(c.comment) LIKE ?
                    OR LOWER(s.username) LIKE ?
                )""")
                pat = f"%{clean_u}%"
                params.extend([pat, pat, pat, pat])
            else:
                clauses.append("c.comment LIKE ?")
                params.append("%@%")
        else:
            clauses.append("""(
                LOWER(c.comment) LIKE ?
                OR LOWER(c.username) LIKE ?
                OR LOWER(c.nickname) LIKE ?
                OR LOWER(s.username) LIKE ?
                OR LOWER(s.display_name) LIKE ?
            )""")
            pat = f"%{token.lower()}%"
            params.extend([pat, pat, pat, pat, pat])

    if not clauses:
        return None, []

    combined_sql = "(" + " AND ".join(clauses) + ")"
    return combined_sql, params


def get_chat_messages(
    streamer_id: Optional[int] = None,
    session_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    username: Optional[str] = None,
    min_tier: Optional[str] = None,
    only_whales: bool = False,
    before_id: Optional[int] = None,
    after_id: Optional[int] = None,
    order_dir: Optional[str] = None,
    include_total: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Liefert gefilterte Chat-Nachrichten pro Streamer, Session oder global über alle Kanäle.
    Unterstützt intelligente Suche (inkl. @username und #id), direkte Benutzer-Filterung,
    Pagination (Limit & Offset), Sortierrichtung und Gesamtanzahl-Berechnung.
    """
    where_clauses = ["1=1"]
    params: List[Any] = []

    if streamer_id:
        where_clauses.append("c.streamer_id = ?")
        params.append(streamer_id)

    if session_id:
        where_clauses.append("c.session_id = ?")
        params.append(session_id)

    if username and isinstance(username, str):
        clean_user = username.strip().lstrip("@").lower()
        if clean_user:
            where_clauses.append("(LOWER(c.username) = ? OR LOWER(c.nickname) = ?)")
            params.extend([clean_user, clean_user])

    if search and isinstance(search, str):
        search_sql, search_params = _build_chat_search_clause(search)
        if search_sql:
            where_clauses.append(search_sql)
            params.extend(search_params)

    if min_tier == "whale":
        where_clauses.append("c.whale_tier = 'whale'")
    elif min_tier == "shark":
        where_clauses.append("c.whale_tier IN ('whale', 'shark')")
    elif min_tier == "dolphin" or only_whales:
        where_clauses.append("(c.is_whale = 1 OR c.whale_tier != '')")

    order_direction = "DESC"
    if after_id:
        where_clauses.append("c.id > ?")
        params.append(after_id)
        order_direction = "ASC"
    elif before_id:
        where_clauses.append("c.id < ?")
        params.append(before_id)
        order_direction = "DESC"
    elif order_dir:
        order_direction = "ASC" if str(order_dir).upper() == "ASC" else "DESC"

    where_sql = " AND ".join(where_clauses)

    total_count = 0
    if include_total:
        count_sql = f"""
        SELECT COUNT(*) AS total
        FROM chat_messages c
        WHERE {where_sql}
        """
        with get_db() as conn:
            cnt_row = conn.execute(count_sql, params).fetchone()
            if cnt_row:
                try:
                    total_count = int(cnt_row["total"])
                except (KeyError, TypeError, IndexError):
                    total_count = int(cnt_row[0])

    query = f"""
    SELECT
        c.id, c.streamer_id, c.session_id, c.user_id, c.username, c.nickname,
        c.avatar_url, c.comment, c.is_whale, c.whale_tier, c.created_at,
        s.username AS streamer_username, s.display_name AS streamer_display_name,
        s.avatar_url AS streamer_avatar_url
    FROM chat_messages c
    JOIN streamers s ON s.id = c.streamer_id
    WHERE {where_sql}
    ORDER BY c.id {order_direction}
    LIMIT ? OFFSET ?
    """
    exec_params = list(params) + [max(1, min(limit, 500)), max(0, offset)]

    with get_db() as conn:
        rows = conn.execute(query, exec_params).fetchall()
        result = []
        for r in rows:
            rd = dict(r)
            rd["is_whale"] = bool(rd["is_whale"])
            result.append(rd)

        if not include_total:
            total_count = len(result)

        return result, total_count


COMMON_CHAT_STOP_WORDS = {
    # Deutsch
    "der", "die", "das", "dem", "den", "des", "ein", "eine", "einer", "eines", "einem", "einen",
    "und", "oder", "aber", "auch", "ist", "sind", "war", "waren", "sein", "haben", "hat", "hatte",
    "wird", "werden", "mit", "von", "aus", "bei", "nach", "zu", "zum", "zur", "in", "im", "an", "am",
    "auf", "über", "unter", "vor", "hinter", "für", "um", "durch", "ohne", "gegen", "wie", "so", "dann",
    "als", "wenn", "weil", "dass", "da", "hier", "dort", "wo", "wer", "was", "warum", "ich", "du", "er",
    "sie", "es", "wir", "ihr", "mich", "dich", "ihn", "uns", "euch", "ihnen", "mir", "dir", "ihm",
    "mein", "dein", "unser", "euer", "ihre", "meine", "deine", "seine", "unsere", "eure", "ihren",
    "nicht", "noch", "nur", "schon", "jetzt", "wieder", "immer", "mehr", "sehr", "viel", "viele",
    "etwas", "alles", "nichts", "man", "mal", "halt", "doch", "ja", "nein", "bitte", "danke",
    "hallo", "servus", "moin", "guten", "hab", "habe", "hast", "geht", "gehts", "geht's", "kann", "kannst",
    "können", "muss", "musst", "müssen", "will", "willst", "wollen", "soll", "sollte", "macht", "machen",
    "gut", "schlecht", "okay", "ok", "dies", "diese", "dieser", "dieses", "diesem", "diesen",
    # Englisch
    "the", "and", "or", "but", "on", "at", "to", "for", "with", "from", "by", "is", "are", "were", "be", "been", "have", "has", "had", "do", "does", "did", "can", "would", "should",
    "it", "its", "you", "they", "them", "my", "your", "this", "that", "what", "which", "who", "not", "no", "yes",
}


EMOJI_REGEX = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]", re.UNICODE)


def get_chat_analysis(
    streamer_id: Optional[int] = None,
    session_id: Optional[int] = None,
    period: str = "all",
    min_word_len: int = 3,
    limit_words: int = 80,
    limit_phrases: int = 30,
    limit_emojis: int = 25,
) -> Dict[str, Any]:
    """
    Führt eine hochperformante NLP-Analyse über Chatnachrichten durch:
    - Wortwolke (Häufigkeit & Gewichtung ohne Stopwörter)
    - Häufige Phrasen & N-Grams (2er- und 3er-Wortkombinationen)
    - Top Emojis & Emote-Häufigkeiten
    - Top-Chatter-Rangliste
    - KPIs (Nachrichten gesamt, Unique Chatter, Whale-Nachrichten, etc.)
    """
    where_clauses = ["1=1"]
    params: List[Any] = []

    if session_id:
        where_clauses.append("c.session_id = ?")
        params.append(session_id)
    elif streamer_id:
        where_clauses.append("c.streamer_id = ?")
        params.append(streamer_id)

    if period != "all" and not session_id:
        cutoff = _get_period_cutoff(period)
        where_clauses.append("c.created_at >= ?")
        params.append(cutoff)

    where_sql = " AND ".join(where_clauses)
    query = f"""
    SELECT
        c.id, c.comment, c.username, c.nickname, c.avatar_url,
        c.is_whale, c.whale_tier, c.created_at
    FROM chat_messages c
    WHERE {where_sql}
    ORDER BY c.id DESC
    LIMIT 6000
    """

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return {
            "total_messages": 0,
            "unique_chatters": 0,
            "whale_messages": 0,
            "avg_chars_per_msg": 0,
            "chatter_diversity_pct": 0.0,
            "words": [],
            "phrases": [],
            "emojis": [],
            "top_chatters": [],
        }

    total_messages = len(rows)
    all_words: List[str] = []
    all_phrases: List[str] = []
    all_emojis: List[str] = []
    user_counter: Counter = Counter()
    user_meta: Dict[str, Dict[str, Any]] = {}
    whale_count = 0
    total_chars = 0

    for r in rows:
        text = str(r["comment"] or "").strip()
        total_chars += len(text)
        username = str(r["username"] or "").strip()
        if username:
            user_counter[username] += 1
            if username not in user_meta:
                user_meta[username] = {
                    "nickname": str(r["nickname"] or username).strip(),
                    "avatar_url": str(r["avatar_url"] or ""),
                    "is_whale": bool(r["is_whale"]),
                    "whale_tier": str(r["whale_tier"] or ""),
                }

        if r["is_whale"]:
            whale_count += 1

        # Emojis finden
        found_emojis = EMOJI_REGEX.findall(text)
        all_emojis.extend(found_emojis)

        # Bereinigung für Text-Tokens
        cleaned = re.sub(r"https?://\S+|www\.\S+|@\w+", " ", text)
        cleaned = re.sub(r"[^\w\s]", " ", cleaned.lower())
        tokens = [w for w in cleaned.split() if len(w) >= 2 and not w.isdigit()]

        # Wortwolken-Tokens (ohne Stopwörter, Mindestlänge)
        valid_words = [w for w in tokens if len(w) >= min_word_len and w not in COMMON_CHAT_STOP_WORDS]
        all_words.extend(valid_words)

        # 2-Grams (Wortpaare)
        for i in range(len(tokens) - 1):
            w1, w2 = tokens[i], tokens[i + 1]
            # Mindestens ein Wort darf kein Stopwort sein
            if (
                len(w1) >= 2
                and len(w2) >= 2
                and (w1 not in COMMON_CHAT_STOP_WORDS or w2 not in COMMON_CHAT_STOP_WORDS)
            ):
                all_phrases.append(f"{w1} {w2}")

        # 3-Grams (3er Phrasen)
        for i in range(len(tokens) - 2):
            w1, w2, w3 = tokens[i], tokens[i + 1], tokens[i + 2]
            if (
                len(w1) >= 2
                and len(w2) >= 2
                and len(w3) >= 2
                and (
                    w1 not in COMMON_CHAT_STOP_WORDS
                    or w2 not in COMMON_CHAT_STOP_WORDS
                    or w3 not in COMMON_CHAT_STOP_WORDS
                )
            ):
                all_phrases.append(f"{w1} {w2} {w3}")

    # 1. Wortwolken-Berechnung
    word_counts = Counter(all_words).most_common(limit_words)
    max_word_count = word_counts[0][1] if word_counts else 1
    word_cloud_data = []
    for word, count in word_counts:
        # Gewichtung von 1 bis 100
        weight = max(1, round((count / max_word_count) * 100))
        word_cloud_data.append({
            "text": word,
            "count": count,
            "weight": weight,
        })

    # 2. Phrasen-Ranking
    phrase_counts = Counter(all_phrases).most_common(limit_phrases)
    phrases_data = []
    for phrase, count in phrase_counts:
        if count >= 2:
            phrases_data.append({
                "phrase": phrase,
                "count": count,
                "pct": round((count / total_messages) * 100, 1),
                "words": len(phrase.split()),
            })

    # 3. Emoji-Ranking
    emoji_counts = Counter(all_emojis).most_common(limit_emojis)
    emoji_data = []
    for emo, count in emoji_counts:
        emoji_data.append({
            "emoji": emo,
            "count": count,
            "pct": round((count / total_messages) * 100, 1),
        })

    # 4. Top Chatter
    top_chatters_raw = user_counter.most_common(12)
    top_chatters = []
    for uname, count in top_chatters_raw:
        meta = user_meta.get(uname, {})
        top_chatters.append({
            "username": uname,
            "nickname": meta.get("nickname", uname),
            "avatar_url": meta.get("avatar_url", ""),
            "is_whale": meta.get("is_whale", False),
            "whale_tier": meta.get("whale_tier", ""),
            "count": count,
            "pct": round((count / total_messages) * 100, 1),
        })

    unique_chatters = len(user_counter)
    diversity = round((unique_chatters / max(1, total_messages)) * 100, 1)
    avg_len = round(total_chars / max(1, total_messages), 1)

    return {
        "total_messages": total_messages,
        "unique_chatters": unique_chatters,
        "whale_messages": whale_count,
        "avg_chars_per_msg": avg_len,
        "chatter_diversity_pct": diversity,
        "words": word_cloud_data,
        "phrases": phrases_data,
        "emojis": emoji_data,
        "top_chatters": top_chatters,
    }


def get_chat_export_data(
    streamer_id: Optional[int] = None,
    session_id: Optional[int] = None,
    search: Optional[str] = None,
    username: Optional[str] = None,
    only_whales: bool = False,
    limit: int = 25000,
) -> List[Dict[str, Any]]:
    """
    Liefert Chatdaten für den CSV-, JSON- oder Text-Export.
    """
    where_clauses = ["1=1"]
    params: List[Any] = []

    if streamer_id:
        where_clauses.append("c.streamer_id = ?")
        params.append(streamer_id)

    if session_id:
        where_clauses.append("c.session_id = ?")
        params.append(session_id)

    if username and isinstance(username, str):
        clean_user = username.strip().lstrip("@").lower()
        if clean_user:
            where_clauses.append("(LOWER(c.username) = ? OR LOWER(c.nickname) = ?)")
            params.extend([clean_user, clean_user])

    if search and isinstance(search, str):
        search_sql, search_params = _build_chat_search_clause(search)
        if search_sql:
            where_clauses.append(search_sql)
            params.extend(search_params)

    if only_whales:
        where_clauses.append("(c.is_whale = 1 OR c.whale_tier != '')")

    where_sql = " AND ".join(where_clauses)
    query = f"""
    SELECT
        c.id, c.created_at, s.username AS streamer_username,
        c.session_id, c.user_id, c.username, c.nickname, c.avatar_url,
        c.is_whale, c.whale_tier, c.comment
    FROM chat_messages c
    JOIN streamers s ON s.id = c.streamer_id
    WHERE {where_sql}
    ORDER BY c.id ASC
    LIMIT ?
    """
    params.append(max(1, min(limit, 50000)))

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
