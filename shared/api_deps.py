"""
FastAPI-Auth-Dependencies: Session-Cookie, API-Key und Capability-Prüfung.

Liegt bewusst unter ``shared``, damit ausgelagerte Router (``routers/*``) die
Dependencies verwenden können, ohne ``app`` zu importieren. Ein Import aus
``app`` wäre zirkulär, weil ``app`` die Router registriert.
"""

import hmac
import logging
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Header, HTTPException, Query, Request

from shared.auth_store import AdminAuthManager, admin_auth_manager
from shared.config import config
from shared.database import (
    get_settings,
    get_telegram_user_by_identifier,
    get_telegram_user_permission_overrides,
)
from shared.permissions import (
    ALL_PERMISSIONS,
    ROLE_ADMIN,
    has_permission,
    is_blocked,
    normalize_role,
)

logger = logging.getLogger("toktracker.auth")


def api_key_matches(provided: str, configured: str) -> bool:
    """Vergleicht API-Keys in konstanter Zeit (Timing-Angriffe vermeiden)."""
    if not provided or not configured:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def provided_api_key(x_api_key: Optional[str], query_api_key: Optional[str]) -> str:
    """Header hat Vorrang; Query-Parameter nur bei ALLOW_API_KEY_QUERY=1."""
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if query_api_key and config.allow_api_key_query:
        return query_api_key.strip()
    return ""


def extract_session_token(
    toktracker_admin_session: Optional[str],
    x_admin_session: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    token = toktracker_admin_session or x_admin_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    return token


def enrich_session_permissions(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ergänzt die Session um persönliche Rechte-Overrides aus der Datenbank."""
    if not payload:
        return payload

    grants: List[str] = []
    denies: List[str] = []
    try:
        identifier = payload.get("telegram_id") or payload.get("sub")
        user_row = get_telegram_user_by_identifier(identifier) if identifier else None
        if user_row:
            overrides = get_telegram_user_permission_overrides(int(user_row["id"]))
            grants = list(overrides.get("grants") or [])
            denies = list(overrides.get("denies") or [])
    except Exception as exc:  # pragma: no cover - DB-Ausfall darf Login nicht blockieren
        logger.debug("Persönliche Rechte konnten nicht geladen werden: %s", exc)

    payload["permission_grants"] = grants
    payload["permission_denies"] = denies
    return payload


def verify_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verifiziert ein Session-Token und reichert es mit effektiven Rechten an."""
    return enrich_session_permissions(admin_auth_manager.verify_session_token(token))


def session_payload_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Liest die Session aus Cookie/Header einer normalen Browser-Anfrage."""
    token = extract_session_token(
        request.cookies.get(AdminAuthManager.COOKIE_NAME),
        request.headers.get("x-admin-session"),
        request.headers.get("authorization"),
    )
    return verify_session_token(token)


def _api_key_payload() -> Dict[str, Any]:
    return {
        "sub": "api_key",
        "role": ROLE_ADMIN,
        "is_allowed": True,
        "permissions": sorted(ALL_PERMISSIONS),
    }


def resolve_access_payload(
    toktracker_admin_session: Optional[str],
    x_admin_session: Optional[str],
    authorization: Optional[str],
    x_api_key: Optional[str],
    api_key: Optional[str],
    permission: Optional[str] = None,
) -> Dict[str, Any]:
    token = extract_session_token(toktracker_admin_session, x_admin_session, authorization)
    session_payload = verify_session_token(token)
    if session_payload:
        if permission and not has_permission(session_payload, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Zugriff verweigert: Das Recht '{permission}' fehlt für diese Rolle.",
            )
        return session_payload

    configured_key = (config.api_key or get_settings().get("api_key") or "").strip()
    provided = provided_api_key(x_api_key, api_key)
    if api_key_matches(provided, configured_key):
        return _api_key_payload()

    raise HTTPException(
        status_code=401,
        detail="Nicht autorisiert. Bitte unter /login per Telegram authentifizieren oder gültigen X-API-Key übergeben.",
    )


def require_permission(permission: str):
    """FastAPI-Dependency-Factory: verlangt eine bestimmte Capability."""

    def dependency(
        toktracker_admin_session: Optional[str] = Cookie(default=None),
        x_admin_session: Optional[str] = Header(default=None, alias="X-Admin-Session"),
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        api_key: Optional[str] = Query(default=None, description="Optionaler API-Key per Query-Parameter"),
    ) -> Dict[str, Any]:
        return resolve_access_payload(
            toktracker_admin_session,
            x_admin_session,
            authorization,
            x_api_key,
            api_key,
            permission=permission,
        )

    return dependency


def verify_admin_or_api_key(
    toktracker_admin_session: Optional[str] = Cookie(default=None),
    x_admin_session: Optional[str] = Header(default=None, alias="X-Admin-Session"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    api_key: Optional[str] = Query(default=None, description="Optionaler API-Key per Query-Parameter"),
) -> Dict[str, Any]:
    """
    Schützt alle reinen Admin-Endpunkte (Einstellungen, Nutzerverwaltung,
    Demo-Daten, destruktive Streamer-Aktionen).
    """
    payload = resolve_access_payload(
        toktracker_admin_session,
        x_admin_session,
        authorization,
        x_api_key,
        api_key,
    )
    if normalize_role(payload.get("role")) != ROLE_ADMIN or is_blocked(payload.get("is_allowed", True)):
        raise HTTPException(
            status_code=403,
            detail="Zugriff verweigert: Dieser Bereich ist Administratoren vorbehalten.",
        )
    return payload
