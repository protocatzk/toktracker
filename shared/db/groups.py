"""
TokTracker - Streamer-Gruppen (Many-to-Many).

Gruppen bündeln beliebig viele Streamer zu einem Auswertungs-Scope, z. B.
Team, Agentur oder Kampagne. Ein Streamer kann in mehreren Gruppen Mitglied
sein. Die Gruppen dienen als Filter für Charts, Dashboard-Analytics, Exporte
und Bot-Reports.
"""

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from shared.db._base import get_db

MAX_GROUP_NAME_LENGTH = 191
MAX_GROUP_DESCRIPTION_LENGTH = 512
MAX_GROUP_COLOR_LENGTH = 16


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _invalidate_analytics_cache() -> None:
    """Mitgliedschafts-Änderungen sofort in den Analytics-Caches sichtbar machen."""
    try:  # Lazy import vermeidet einen Zirkelbezug analytics -> groups.
        from shared.db.analytics import invalidate_overview_cache

        invalidate_overview_cache()
    except Exception:  # pragma: no cover - Cache-Invalidierung ist best effort
        pass
    try:
        from shared.chart_views import clear_chart_view_cache

        clear_chart_view_cache()
    except Exception:  # pragma: no cover - nur relevant, wenn Charts geladen sind
        pass


def normalize_group_name(value: Any) -> str:
    """Bereinigt einen Gruppennamen (Whitespace, Länge) für Lookups und Anlage."""
    name = " ".join(str(value or "").split())
    return name[:MAX_GROUP_NAME_LENGTH]


def _clean_description(value: Any) -> str:
    return str(value or "").strip()[:MAX_GROUP_DESCRIPTION_LENGTH]


def _clean_color(value: Any) -> str:
    """Akzeptiert nur Hex-Farben, damit der Wert gefahrlos im Frontend landet."""
    color = str(value or "").strip()[:MAX_GROUP_COLOR_LENGTH]
    if not color:
        return ""
    return color if re.fullmatch(r"#[0-9a-fA-F]{3,8}", color) else ""


def _unique_streamer_ids(streamer_ids: Optional[Iterable[Any]]) -> List[int]:
    cleaned: List[int] = []
    seen = set()
    for raw in streamer_ids or []:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        if sid <= 0 or sid in seen:
            continue
        seen.add(sid)
        cleaned.append(sid)
    return cleaned


def _members_by_group(conn: Any, group_ids: Optional[List[int]] = None) -> Dict[int, List[int]]:
    sql = "SELECT group_id, streamer_id FROM streamer_group_members"
    params: tuple = ()
    if group_ids is not None:
        if not group_ids:
            return {}
        placeholders = ",".join("?" for _ in group_ids)
        sql += f" WHERE group_id IN ({placeholders})"
        params = tuple(group_ids)
    sql += " ORDER BY group_id ASC, streamer_id ASC"
    rows = conn.execute(sql, params).fetchall()
    members: Dict[int, List[int]] = {}
    for row in rows:
        members.setdefault(int(row["group_id"]), []).append(int(row["streamer_id"]))
    return members


def _serialize_group(row: Any, streamer_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    members = list(streamer_ids or [])
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "description": str(row["description"] or ""),
        "color": str(row["color"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "streamer_ids": members,
        "member_count": len(members),
    }


def list_streamer_groups() -> List[Dict[str, Any]]:
    """Liefert alle Gruppen inklusive Mitglieder-IDs, alphabetisch sortiert."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM streamer_groups").fetchall()
        members = _members_by_group(conn)
        groups = [
            _serialize_group(row, members.get(int(row["id"]), []))
            for row in rows
        ]
        groups.sort(key=lambda g: (g["name"].lower(), g["id"]))
        return groups


def get_streamer_group(group_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamer_groups WHERE id = ?", (int(group_id),)
        ).fetchone()
        if not row:
            return None
        members = _members_by_group(conn, [int(group_id)])
        return _serialize_group(row, members.get(int(group_id), []))


def get_streamer_group_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Case-insensitiver Lookup über den Gruppennamen."""
    cleaned = normalize_group_name(name)
    if not cleaned:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamer_groups WHERE LOWER(name) = LOWER(?)",
            (cleaned,),
        ).fetchone()
        if not row:
            return None
        members = _members_by_group(conn, [int(row["id"])])
        return _serialize_group(row, members.get(int(row["id"]), []))


def resolve_streamer_group(reference: Any) -> Optional[Dict[str, Any]]:
    """Löst eine Gruppen-ID oder einen Gruppennamen in eine Gruppe auf."""
    if reference is None or str(reference).strip() == "":
        return None
    if isinstance(reference, int) or str(reference).strip().isdigit():
        group = get_streamer_group(int(reference))
        if group:
            return group
    return get_streamer_group_by_name(str(reference))


def get_group_streamer_ids(group_id: Optional[int]) -> List[int]:
    """Mitglieder-IDs einer Gruppe; leere Liste bei unbekannter Gruppe."""
    if group_id is None:
        return []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT streamer_id FROM streamer_group_members WHERE group_id = ? ORDER BY streamer_id ASC",
            (int(group_id),),
        ).fetchall()
        return [int(r["streamer_id"]) for r in rows]


def get_groups_for_streamer(streamer_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT g.*
            FROM streamer_groups g
            JOIN streamer_group_members m ON m.group_id = g.id
            WHERE m.streamer_id = ?
            """,
            (int(streamer_id),),
        ).fetchall()
        groups = [_serialize_group(row, [int(streamer_id)]) for row in rows]
        groups.sort(key=lambda g: (g["name"].lower(), g["id"]))
        return groups


def set_streamer_group_members(group_id: int, streamer_ids: Optional[Iterable[Any]]) -> List[int]:
    """
    Ersetzt die Mitgliederliste einer Gruppe vollständig.

    Unbekannte Streamer-IDs werden verworfen, damit Fremdschlüssel nicht
    fehlschlagen. Gibt die tatsächlich gespeicherten IDs zurück.
    """
    wanted = _unique_streamer_ids(streamer_ids)
    with get_db() as conn:
        if wanted:
            placeholders = ",".join("?" for _ in wanted)
            valid_rows = conn.execute(
                f"SELECT id FROM streamers WHERE id IN ({placeholders})",
                tuple(wanted),
            ).fetchall()
            valid = {int(r["id"]) for r in valid_rows}
            wanted = [sid for sid in wanted if sid in valid]

        conn.execute(
            "DELETE FROM streamer_group_members WHERE group_id = ?", (int(group_id),)
        )
        now = _now_iso()
        for sid in wanted:
            conn.execute(
                """
                INSERT INTO streamer_group_members (group_id, streamer_id, created_at)
                VALUES (?, ?, ?)
                """,
                (int(group_id), int(sid), now),
            )
        conn.execute(
            "UPDATE streamer_groups SET updated_at = ? WHERE id = ?",
            (now, int(group_id)),
        )
    _invalidate_analytics_cache()
    return wanted


def create_streamer_group(
    name: str,
    description: str = "",
    color: str = "",
    streamer_ids: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """
    Legt eine Gruppe an.

    Raises:
        ValueError: bei leerem Namen oder bereits vergebener Bezeichnung.
    """
    cleaned = normalize_group_name(name)
    if not cleaned:
        raise ValueError("Gruppenname darf nicht leer sein.")
    now = _now_iso()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM streamer_groups WHERE LOWER(name) = LOWER(?)", (cleaned,)
        ).fetchone()
        if existing:
            raise ValueError(f"Gruppe '{cleaned}' existiert bereits.")
        cur = conn.execute(
            """
            INSERT INTO streamer_groups (name, description, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cleaned, _clean_description(description), _clean_color(color), now, now),
        )
        group_id = int(cur.lastrowid)
    if streamer_ids is not None:
        set_streamer_group_members(group_id, streamer_ids)
    else:
        _invalidate_analytics_cache()
    group = get_streamer_group(group_id)
    if not group:  # pragma: no cover - direkter Folgefehler der DB
        raise RuntimeError("Gruppe konnte nach dem Anlegen nicht geladen werden.")
    return group


def update_streamer_group(
    group_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Aktualisiert Stammdaten einer Gruppe; Mitglieder bleiben unverändert."""
    current = get_streamer_group(group_id)
    if not current:
        return None

    new_name = current["name"] if name is None else normalize_group_name(name)
    if not new_name:
        raise ValueError("Gruppenname darf nicht leer sein.")
    if new_name.lower() != current["name"].lower():
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM streamer_groups WHERE LOWER(name) = LOWER(?) AND id <> ?",
                (new_name, int(group_id)),
            ).fetchone()
            if existing:
                raise ValueError(f"Gruppe '{new_name}' existiert bereits.")

    new_description = (
        current["description"] if description is None else _clean_description(description)
    )
    new_color = current["color"] if color is None else _clean_color(color)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE streamer_groups
            SET name = ?, description = ?, color = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_name, new_description, new_color, _now_iso(), int(group_id)),
        )
    _invalidate_analytics_cache()
    return get_streamer_group(group_id)


def delete_streamer_group(group_id: int) -> bool:
    with get_db() as conn:
        # Explizit aufräumen, damit unabhängig von FK-Enforcement
        # keine verwaisten Mitgliedschaften bleiben.
        conn.execute(
            "DELETE FROM streamer_group_members WHERE group_id = ?", (int(group_id),)
        )
        cur = conn.execute(
            "DELETE FROM streamer_groups WHERE id = ?", (int(group_id),)
        )
        deleted = bool(cur.rowcount)
    if deleted:
        _invalidate_analytics_cache()
    return deleted
