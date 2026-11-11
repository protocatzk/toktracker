"""
TokTracker - Telegram-Nutzer, Rollen und Whitelist-Berechtigungen.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
from shared.permissions import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE,
    PERMISSION_EFFECT_DENY,
    PERMISSION_EFFECT_GRANT,
    PERMISSION_EFFECTS,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    ROLE_VIEWER,
    highest_role,
    is_valid_role,
    normalize_role,
    resolve_permissions,
)


def list_telegram_users() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM telegram_users
            ORDER BY is_allowed DESC,
                     CASE role
                         WHEN 'admin' THEN 0
                         WHEN 'moderator' THEN 1
                         WHEN 'user' THEN 2
                         ELSE 3
                     END ASC,
                     id DESC
            """
        ).fetchall()
        permission_rows = conn.execute(
            """
            SELECT user_id, permission, effect
            FROM telegram_user_permissions
            ORDER BY user_id ASC, permission ASC
            """
        ).fetchall()

    overrides: Dict[int, Dict[str, List[str]]] = {}
    for perm_row in permission_rows:
        user_id = int(perm_row["user_id"])
        effect = str(perm_row["effect"] or "").strip().lower()
        permission = str(perm_row["permission"] or "").strip()
        if effect not in PERMISSION_EFFECTS or permission not in ALL_PERMISSIONS:
            continue
        bucket = overrides.setdefault(user_id, {"grants": [], "denies": []})
        if effect == PERMISSION_EFFECT_GRANT:
            bucket["grants"].append(permission)
        else:
            bucket["denies"].append(permission)

    users: List[Dict[str, Any]] = []
    for row in rows:
        user = dict(row)
        user_id = int(user.get("id") or 0)
        bucket = overrides.get(user_id, {"grants": [], "denies": []})
        user["permission_grants"] = list(bucket["grants"])
        user["permission_denies"] = list(bucket["denies"])
        user["effective_permissions"] = sorted(
            resolve_permissions(
                user.get("role"),
                user.get("is_allowed", 0),
                bucket["grants"],
                bucket["denies"],
            )
        )
        users.append(user)
    return users


def get_telegram_user_by_id(record_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM telegram_users WHERE id = ?", (int(record_id),)
        ).fetchone()
        return dict(row) if row else None


def get_telegram_user_by_identifier(identifier: str | int) -> Optional[Dict[str, Any]]:
    """
    Findet einen Telegram-Nutzer anhand von DB-ID, Telegram-ID, ``@username``,
    ``id:123`` oder ``tg_123`` (Mini-App-Label).
    """
    raw = str(identifier or "").strip()
    if not raw:
        return None
    clean = raw
    if clean.startswith("tg_"):
        clean = clean[3:]
    if clean.startswith("id:"):
        clean = clean[3:]
    clean = clean.lstrip("@").strip()
    if not clean:
        return None

    with get_db() as conn:
        if clean.lstrip("-").isdigit():
            numeric = int(clean)
            row = conn.execute(
                "SELECT * FROM telegram_users WHERE telegram_id = ? OR id = ?",
                (numeric, numeric),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM telegram_users WHERE LOWER(username) = LOWER(?)",
                (clean,),
            ).fetchone()
        return dict(row) if row else None


def get_telegram_user_permissions(user_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT permission, effect, created_by, created_at
            FROM telegram_user_permissions
            WHERE user_id = ?
            ORDER BY permission ASC
            """,
            (int(user_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def get_telegram_user_permission_overrides(user_id: int) -> Dict[str, List[str]]:
    grants: List[str] = []
    denies: List[str] = []
    for row in get_telegram_user_permissions(user_id):
        effect = str(row.get("effect") or "").strip().lower()
        permission = str(row.get("permission") or "").strip()
        if effect not in PERMISSION_EFFECTS or permission not in ALL_PERMISSIONS:
            continue
        if effect == PERMISSION_EFFECT_GRANT:
            grants.append(permission)
        else:
            denies.append(permission)
    return {"grants": sorted(grants), "denies": sorted(denies)}


def replace_telegram_user_permissions(
    user_id: int,
    grants: List[str] | Tuple[str, ...] = (),
    denies: List[str] | Tuple[str, ...] = (),
    created_by: str = "",
) -> Dict[str, List[str]]:
    """
    Ersetzt alle persönlichen Overrides eines Kontos atomar.

    Unbekannte Capabilities oder gleichzeitig erteilte/entzogene Rechte werden
    mit ``ValueError`` abgelehnt.
    """
    grant_set = {str(permission or "").strip() for permission in grants}
    deny_set = {str(permission or "").strip() for permission in denies}
    grant_set.discard("")
    deny_set.discard("")

    unknown = sorted((grant_set | deny_set) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError("Unbekannte Rechte: " + ", ".join(unknown))
    overlap = sorted(grant_set & deny_set)
    if overlap:
        raise ValueError(
            "Rechte können nicht gleichzeitig erteilt und entzogen werden: "
            + ", ".join(overlap)
        )

    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        user_row = conn.execute(
            "SELECT id FROM telegram_users WHERE id = ?", (int(user_id),)
        ).fetchone()
        if not user_row:
            raise ValueError("Telegram-Nutzer nicht gefunden.")

        conn.execute(
            "DELETE FROM telegram_user_permissions WHERE user_id = ?",
            (int(user_id),),
        )
        for permission in sorted(grant_set | deny_set):
            effect = (
                PERMISSION_EFFECT_GRANT if permission in grant_set else PERMISSION_EFFECT_DENY
            )
            conn.execute(
                """
                INSERT INTO telegram_user_permissions (
                    user_id, permission, effect, created_by, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), permission, effect, created_by or "", now),
            )

    return {
        "grants": sorted(grant_set),
        "denies": sorted(deny_set),
    }


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

    raw_role = role.strip().lower() if role else ROLE_USER
    if not is_valid_role(raw_role):
        raise ValueError(
            "Ungültige Rolle. Erlaubt sind: viewer, user, moderator, admin."
        )
    clean_role = normalize_role(raw_role)

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
            merged_role = highest_role(row_by_id["role"], row_by_uname["role"])
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
            new_role = ROLE_ADMIN if in_env_admin else normalize_role(row["role"])
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
            if in_env_admin:
                initial_role = ROLE_ADMIN
            elif mode == "public":
                initial_role = ROLE_VIEWER
            else:
                initial_role = ROLE_USER
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

        permission_grants: List[str] = []
        permission_denies: List[str] = []
        if not in_env_admin and row_id:
            for perm_row in conn.execute(
                """
                SELECT permission, effect
                FROM telegram_user_permissions
                WHERE user_id = ?
                ORDER BY permission ASC
                """,
                (int(row_id),),
            ).fetchall():
                effect = str(perm_row["effect"] or "").strip().lower()
                permission = str(perm_row["permission"] or "").strip()
                if effect not in PERMISSION_EFFECTS or permission not in ALL_PERMISSIONS:
                    continue
                if effect == PERMISSION_EFFECT_GRANT:
                    permission_grants.append(permission)
                else:
                    permission_denies.append(permission)

    is_allowed_flag = int(user_row.get("is_allowed", 0))
    role_val = normalize_role(user_row.get("role", DEFAULT_ROLE))

    if is_allowed_flag < 0:
        allowed = False
        is_admin = False
        effective_role = ROLE_VIEWER
    elif mode == "public":
        allowed = True
        is_admin = bool(is_allowed_flag == 1 and role_val == ROLE_ADMIN)
        effective_role = role_val if is_allowed_flag == 1 else ROLE_VIEWER
    else:
        allowed = bool(is_allowed_flag == 1 or group_whitelisted)
        is_admin = bool(is_allowed_flag == 1 and role_val == ROLE_ADMIN)
        if is_allowed_flag == 1:
            effective_role = role_val
        elif group_whitelisted:
            effective_role = ROLE_USER
        else:
            effective_role = ROLE_VIEWER

    is_whitelisted = bool(
        allowed and effective_role in (ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN)
    )
    effective_permissions = sorted(
        resolve_permissions(
            effective_role,
            1 if allowed else 0,
            permission_grants,
            permission_denies,
        )
    )

    return {
        "allowed": allowed,
        "is_admin": is_admin,
        "is_whitelisted": is_whitelisted,
        "role": effective_role,
        "mode": mode,
        "is_group": is_group,
        "user": user_row,
        "permission_grants": sorted(permission_grants),
        "permission_denies": sorted(permission_denies),
        "permissions": effective_permissions,
    }
