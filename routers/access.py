"""
Zugriffsverwaltung: Whitelist, Rollen und persönliche Rechte-Overrides.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from schemas import TelegramUserPermissionRequest, TelegramUserPermissionsUpdateRequest
from shared.api_deps import require_permission
from shared.database import (
    delete_telegram_user,
    get_telegram_access_mode,
    get_telegram_user_by_id,
    get_telegram_user_by_identifier,
    get_telegram_user_permission_overrides,
    init_db,
    list_telegram_users,
    replace_telegram_user_permissions,
    upsert_telegram_user_permission,
)
from shared.permissions import (
    ALL_PERMISSIONS,
    PERM_SETTINGS_MANAGE,
    PERM_SYSTEM_MANAGE,
    PERM_USERS_MANAGE,
    PERMISSION_LABELS,
    ROLE_ADMIN,
    ROLE_PERMISSIONS,
    normalize_role,
    resolve_permissions,
    session_permissions,
)

router = APIRouter()


@router.get(
    "/api/telegram/users",
    tags=["Telegram Bot API"],
    summary="Listet alle Telegram-Nutzer (Whitelist, Admins & offene Anfragen) sowie den Zugriffsmodus",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
@router.get(
    "/api/v1/telegram/users",
    tags=["Telegram Bot API"],
    summary="Listet alle Telegram-Nutzer (Whitelist, Admins & offene Anfragen) sowie den Zugriffsmodus",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
def api_get_telegram_users():
    init_db()
    return {
        "access_mode": get_telegram_access_mode(),
        "users": list_telegram_users(),
    }


@router.post(
    "/api/telegram/users",
    tags=["Telegram Bot API"],
    summary="Fügt einen Telegram-Nutzer per ID oder @username zur Whitelist hinzu oder ändert seine Rolle",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
@router.post(
    "/api/v1/telegram/users",
    tags=["Telegram Bot API"],
    summary="Fügt einen Telegram-Nutzer per ID oder @username zur Whitelist hinzu oder ändert seine Rolle",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
def api_upsert_telegram_user(payload: TelegramUserPermissionRequest):
    init_db()
    try:
        user_row = upsert_telegram_user_permission(
            identifier=payload.identifier,
            is_allowed=payload.is_allowed,
            role=payload.role,
            first_name=payload.first_name,
            note=payload.note,
        )
        return {"ok": True, "user": user_row, "access_mode": get_telegram_access_mode()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_CRITICAL_PERMISSIONS = frozenset({
    PERM_USERS_MANAGE,
    PERM_SETTINGS_MANAGE,
    PERM_SYSTEM_MANAGE,
})


def _permission_definitions() -> List[Dict[str, str]]:
    return [
        {
            "key": permission,
            "label": PERMISSION_LABELS.get(permission, permission),
            "scope": "bot" if permission.startswith("bot.") else "web",
        }
        for permission in sorted(ALL_PERMISSIONS)
    ]


def _telegram_user_permission_payload(user_row: Dict[str, Any]) -> Dict[str, Any]:
    role = normalize_role(user_row.get("role"))
    overrides = get_telegram_user_permission_overrides(int(user_row["id"]))
    grants = list(overrides.get("grants") or [])
    denies = list(overrides.get("denies") or [])
    effective = sorted(
        resolve_permissions(
            role,
            user_row.get("is_allowed", 0),
            grants,
            denies,
        )
    )
    return {
        "user": user_row,
        "role": role,
        "role_permissions": sorted(ROLE_PERMISSIONS.get(role, frozenset())),
        "grants": grants,
        "denies": denies,
        "effective_permissions": effective,
        "permissions": _permission_definitions(),
    }


def _session_user_id(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    if not payload:
        return None
    try:
        identifier = payload.get("telegram_id") or payload.get("sub")
        user_row = get_telegram_user_by_identifier(identifier) if identifier else None
        return int(user_row["id"]) if user_row else None
    except Exception:
        return None


@router.get(
    "/api/telegram/users/{record_id}/permissions",
    tags=["Telegram Bot API"],
    summary="Liefert Rolle, persönliche Overrides und effektive Rechte eines Kontos",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
@router.get(
    "/api/v1/telegram/users/{record_id}/permissions",
    tags=["Telegram Bot API"],
    summary="Liefert Rolle, persönliche Overrides und effektive Rechte eines Kontos",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
def api_get_telegram_user_permissions(record_id: int):
    init_db()
    user_row = get_telegram_user_by_id(record_id)
    if not user_row:
        raise HTTPException(status_code=404, detail="Telegram-Nutzer nicht gefunden.")
    return _telegram_user_permission_payload(user_row)


@router.put(
    "/api/telegram/users/{record_id}/permissions",
    tags=["Telegram Bot API"],
    summary="Ersetzt die persönlichen Rechte-Overrides eines Kontos",
)
@router.put(
    "/api/v1/telegram/users/{record_id}/permissions",
    tags=["Telegram Bot API"],
    summary="Ersetzt die persönlichen Rechte-Overrides eines Kontos",
)
def api_update_telegram_user_permissions(
    record_id: int,
    payload: TelegramUserPermissionsUpdateRequest,
    session_payload: Dict[str, Any] = Depends(require_permission(PERM_USERS_MANAGE)),
):
    init_db()
    user_row = get_telegram_user_by_id(record_id)
    if not user_row:
        raise HTTPException(status_code=404, detail="Telegram-Nutzer nicht gefunden.")

    if _session_user_id(session_payload) == record_id:
        raise HTTPException(
            status_code=403,
            detail="Eigene Rechte können nicht geändert werden. Bitte einen anderen Admin verwenden.",
        )

    if (
        normalize_role(user_row.get("role")) == ROLE_ADMIN
        and normalize_role(session_payload.get("role")) != ROLE_ADMIN
    ):
        raise HTTPException(
            status_code=403,
            detail="Rechte von Administratoren dürfen nur Administratoren ändern.",
        )

    requested = set(payload.grants) | set(payload.denies)
    actor_permissions = session_permissions(session_payload)
    if not requested.issubset(actor_permissions):
        raise HTTPException(
            status_code=403,
            detail="Es können nur Rechte vergeben oder entzogen werden, die das eigene Konto besitzt.",
        )

    if requested & _CRITICAL_PERMISSIONS and normalize_role(session_payload.get("role")) != ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Kritische Rechte dürfen nur Administratoren vergeben oder entziehen.",
        )

    try:
        replace_telegram_user_permissions(
            record_id,
            payload.grants,
            payload.denies,
            created_by=str(session_payload.get("sub") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated_row = get_telegram_user_by_id(record_id) or user_row
    result = _telegram_user_permission_payload(updated_row)
    result["ok"] = True
    return result


@router.delete(
    "/api/telegram/users/{record_id}",
    tags=["Telegram Bot API"],
    summary="Entfernt einen Telegram-Nutzer aus der Datenbank",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
@router.delete(
    "/api/v1/telegram/users/{record_id}",
    tags=["Telegram Bot API"],
    summary="Entfernt einen Telegram-Nutzer aus der Datenbank",
    dependencies=[Depends(require_permission(PERM_USERS_MANAGE))],
)
def api_delete_telegram_user(record_id: int):
    init_db()
    deleted = delete_telegram_user(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Telegram-Nutzer nicht gefunden.")
    return {"ok": True, "deleted_id": record_id}
