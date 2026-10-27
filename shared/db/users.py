"""
TokTracker - Telegram-Nutzer, Rollen und Whitelist-Berechtigungen.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False

from shared.config import config
from shared.db._base import get_db
from shared.db.settings import get_telegram_access_mode


def list_telegram_users() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM telegram_users
            ORDER BY is_allowed DESC, CASE WHEN role = 'admin' THEN 0 ELSE 1 END ASC, id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_telegram_user_permission(
    identifier: str | int,
    is_allowed: int | bool = 1,
    role: str = "user",
    first_name: Optional[str] = None,
    note: Optional[str] = None,
    telegram_id_override: Optional[int] = None,
    username_override: Optional[str] = None,
) -> Dict[str, Any]:
    raw = str(identifier).strip()
    if not raw:
        raise ValueError("Bitte eine Telegram User-ID oder einen [@]username angeben.")

    clean_role = role.strip().lower() if role else "user"
    if clean_role not in ("admin", "user"):
        clean_role = "user"

    allowed_val = int(is_allowed)
    if allowed_val not in (-1, 0, 1):
        allowed_val = 1 if bool(is_allowed) else 0

    now = datetime.now().isoformat(timespec="seconds")
    clean_ident = raw.lstrip("@").strip()
    is_numeric_id = clean_ident.lstrip("-").isdigit()

    with get_db() as conn:
        existing = None
        tg_id: Optional[int] = telegram_id_override
        uname: Optional[str] = (username_override or "").strip().lstrip("@").lower() or None

        if is_numeric_id:
            tg_id = int(clean_ident)
            existing = conn.execute(
                "SELECT * FROM telegram_users WHERE telegram_id = ? OR id = ?",
                (tg_id, tg_id),
            ).fetchone()
            if not existing and uname:
                existing = conn.execute(
                    "SELECT * FROM telegram_users WHERE LOWER(username) = LOWER(?)",
                    (uname,),
                ).fetchone()
        else:
            uname = clean_ident.lower()
            existing = conn.execute(
                "SELECT * FROM telegram_users WHERE LOWER(username) = LOWER(?)",
                (uname,),
            ).fetchone()
            if not existing and tg_id is not None:
                existing = conn.execute(
                    "SELECT * FROM telegram_users WHERE telegram_id = ?",
                    (tg_id,),
                ).fetchone()

        if existing:
            new_tg_id = tg_id if tg_id is not None else existing["telegram_id"]
            new_uname = uname if uname else existing["username"]
            new_fname = first_name if first_name is not None else existing["first_name"]
            new_note = note if note is not None else existing["note"]
            conn.execute(
                """
                UPDATE telegram_users
                SET telegram_id = ?, username = ?, is_allowed = ?, role = ?, first_name = ?, note = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (new_tg_id, new_uname, allowed_val, clean_role, new_fname, new_note, now, existing["id"]),
            )
            row_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO telegram_users (
                    telegram_id, username, first_name, role, is_allowed, note, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tg_id,
                    uname or "",
                    first_name or "",
                    clean_role,
                    allowed_val,
                    note or "Manuell angelegt",
                    now,
                    now,
                ),
            )
            row_id = cur.lastrowid

        row = conn.execute(
            "SELECT * FROM telegram_users WHERE id = ?", (row_id,)
        ).fetchone()
        return dict(row)


def delete_telegram_user(record_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM telegram_users WHERE id = ?", (record_id,))
        return cur.rowcount > 0


def check_telegram_user_access(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    chat_id: Optional[int] = None,
    chat_title: Optional[str] = None,
) -> Dict[str, Any]:
    clean_uname = (username or "").strip().lstrip("@").lower()
    clean_fname = (first_name or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    mode = get_telegram_access_mode()

    in_env_admin = (
        telegram_id in config.env_allowed_telegram_ids
        or (clean_uname and clean_uname in config.env_allowed_telegram_usernames)
    )

    is_group = bool(chat_id is not None and chat_id != telegram_id)
    source_note = (
        f"Gruppe: {chat_title or chat_id}" if is_group else "Privatchat"
    )

    with get_db() as conn:
        row_by_id = conn.execute(
            "SELECT * FROM telegram_users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()

        row_by_uname = None
        if clean_uname:
            row_by_uname = conn.execute(
                "SELECT * FROM telegram_users WHERE LOWER(username) = LOWER(?)",
                (clean_uname,),
            ).fetchone()

        if row_by_id and row_by_uname and row_by_id["id"] != row_by_uname["id"]:
            merged_allowed = max(int(row_by_id["is_allowed"]), int(row_by_uname["is_allowed"]))
            if (int(row_by_id["is_allowed"]) < 0 or int(row_by_uname["is_allowed"]) < 0) and merged_allowed < 1:
                merged_allowed = -1
            merged_role = (
                "admin"
                if (row_by_id["role"] == "admin" or row_by_uname["role"] == "admin")
                else "user"
            )
            conn.execute("DELETE FROM telegram_users WHERE id = ?", (row_by_uname["id"],))
            conn.execute(
                "UPDATE telegram_users SET is_allowed = ?, role = ? WHERE id = ?",
                (merged_allowed, merged_role, row_by_id["id"]),
            )
            row = conn.execute(
                "SELECT * FROM telegram_users WHERE id = ?", (row_by_id["id"],)
            ).fetchone()
        else:
            row = row_by_id or row_by_uname

        if row:
            new_role = "admin" if in_env_admin else row["role"]
            new_allowed = 1 if in_env_admin else int(row["is_allowed"])
            conn.execute(
                """
                UPDATE telegram_users
                SET telegram_id = ?,
                    username = COALESCE(NULLIF(?, ''), username),
                    first_name = COALESCE(NULLIF(?, ''), first_name),
                    role = ?,
                    is_allowed = ?,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    telegram_id,
                    clean_uname,
                    clean_fname,
                    new_role,
                    new_allowed,
                    now,
                    row["id"],
                ),
            )
            row_id = row["id"]
        else:
            initial_role = "admin" if in_env_admin else "user"
            initial_allowed = 1 if in_env_admin else 0
            note = "Aus .env autorisiert" if in_env_admin else f"Anfrage ({source_note})"
            cur = conn.execute(
                """
                INSERT INTO telegram_users (
                    telegram_id, username, first_name, role, is_allowed, note, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    clean_uname,
                    clean_fname,
                    initial_role,
                    initial_allowed,
                    note,
                    now,
                    now,
                ),
            )
            row_id = cur.lastrowid

        user_row = dict(
            conn.execute("SELECT * FROM telegram_users WHERE id = ?", (row_id,)).fetchone()
        )

        group_whitelisted = False
        if is_group and chat_id is not None:
            grp_row = conn.execute(
                "SELECT is_allowed FROM telegram_users WHERE telegram_id = ?",
                (int(chat_id),),
            ).fetchone()
            if grp_row and int(grp_row["is_allowed"]) == 1:
                group_whitelisted = True

    is_allowed_flag = int(user_row.get("is_allowed", 0))
    role_val = user_row.get("role", "user")

    if is_allowed_flag < 0:
        allowed = False
        is_admin = False
    elif mode == "public":
        allowed = True
        is_admin = bool(is_allowed_flag == 1 and role_val == "admin")
    else:
        allowed = bool(is_allowed_flag == 1 or group_whitelisted)
        is_admin = bool(is_allowed_flag == 1 and role_val == "admin")

    return {
        "allowed": allowed,
        "is_admin": is_admin,
        "mode": mode,
        "is_group": is_group,
        "user": user_row,
    }
