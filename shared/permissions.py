"""
TokTracker - zentrale Rollen- und Rechteverwaltung.

Die Rechte sind bewusst als feine, stringbasierte Capabilities modelliert.
Rollen bilden diese Capabilities auf feste Mengen ab. So koennen einzelne
Endpunkte genau ein Recht verlangen, ohne die Rolle selbst zu kennen.

Die Datei ist frei von FastAPI- und Datenbankabhaengigkeiten und damit
isoliert testbar.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional

# ---------------------------------------------------------------------------
# Rollen
# ---------------------------------------------------------------------------

ROLE_VIEWER = "viewer"
ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"

# Reihenfolge = aufsteigende Berechtigungsstufe.
ROLES = (ROLE_VIEWER, ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN)
DEFAULT_ROLE = ROLE_VIEWER

ROLE_PRIORITY: Dict[str, int] = {
    ROLE_VIEWER: 0,
    ROLE_USER: 1,
    ROLE_MODERATOR: 2,
    ROLE_ADMIN: 3,
}

ROLE_LABELS: Dict[str, str] = {
    ROLE_VIEWER: "Gast / Zuschauer",
    ROLE_USER: "Nutzer / Mitglied (Whitelist)",
    ROLE_MODERATOR: "Moderator",
    ROLE_ADMIN: "Administrator",
}

# Alte/alternative Schreibweisen, die beim Lesen toleriert werden.
LEGACY_ROLE_ALIASES: Dict[str, str] = {
    "public": ROLE_VIEWER,
    "guest": ROLE_VIEWER,
    "gast": ROLE_VIEWER,
    "viewer": ROLE_VIEWER,
    "member": ROLE_USER,
    "mitglied": ROLE_USER,
    "nutzer": ROLE_USER,
    "user": ROLE_USER,
    "mod": ROLE_MODERATOR,
    "moderator": ROLE_MODERATOR,
    "administrator": ROLE_ADMIN,
    "admin": ROLE_ADMIN,
}

# ---------------------------------------------------------------------------
# Rechte / Capabilities
# ---------------------------------------------------------------------------

PERM_PUBLIC_VIEW = "public.view"
PERM_RADAR_VIEW = "radar.view"
PERM_CHATINTEL_VIEW = "chatintel.view"
PERM_ANALYTICS_VIEW = "analytics.view"
PERM_EXPORT_DOWNLOAD = "export.download"
PERM_SYSTEM_VIEW = "system.view"
PERM_CRM_EDIT = "crm.edit"
PERM_STREAMERS_MANAGE = "streamers.manage"
PERM_GIFTS_BOOK = "gifts.book"
PERM_SETTINGS_MANAGE = "settings.manage"
PERM_USERS_MANAGE = "users.manage"
PERM_SYSTEM_MANAGE = "system.manage"
PERM_REPORTS_SEND = "reports.send"

ALL_PERMISSIONS: FrozenSet[str] = frozenset({
    PERM_PUBLIC_VIEW,
    PERM_RADAR_VIEW,
    PERM_CHATINTEL_VIEW,
    PERM_ANALYTICS_VIEW,
    PERM_EXPORT_DOWNLOAD,
    PERM_SYSTEM_VIEW,
    PERM_CRM_EDIT,
    PERM_STREAMERS_MANAGE,
    PERM_GIFTS_BOOK,
    PERM_SETTINGS_MANAGE,
    PERM_USERS_MANAGE,
    PERM_SYSTEM_MANAGE,
    PERM_REPORTS_SEND,
})

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    ROLE_VIEWER: frozenset({PERM_PUBLIC_VIEW}),
    ROLE_USER: frozenset({
        PERM_PUBLIC_VIEW,
        PERM_RADAR_VIEW,
        PERM_CHATINTEL_VIEW,
    }),
    ROLE_MODERATOR: frozenset({
        PERM_PUBLIC_VIEW,
        PERM_RADAR_VIEW,
        PERM_CHATINTEL_VIEW,
        PERM_ANALYTICS_VIEW,
        PERM_EXPORT_DOWNLOAD,
        PERM_SYSTEM_VIEW,
    }),
    ROLE_ADMIN: ALL_PERMISSIONS,
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def normalize_role(role: Optional[str]) -> str:
    """Liefert eine gueltige Rolle. Unbekannte Werte werden fail-closed zu viewer."""
    if role is None:
        return DEFAULT_ROLE
    clean = str(role).strip().lower()
    if not clean:
        return DEFAULT_ROLE
    return LEGACY_ROLE_ALIASES.get(clean, DEFAULT_ROLE)


def is_valid_role(role: Optional[str]) -> bool:
    """True, wenn der Wert (inkl. Alias) einer bekannten Rolle entspricht."""
    if role is None:
        return False
    clean = str(role).strip().lower()
    return clean in LEGACY_ROLE_ALIASES


def role_priority(role: Optional[str]) -> int:
    return ROLE_PRIORITY.get(normalize_role(role), 0)


def highest_role(*roles: Optional[str]) -> str:
    """Waehlt die hoechste Rolle aus mehreren Kandidaten."""
    best = DEFAULT_ROLE
    best_priority = -1
    for role in roles:
        normalized = normalize_role(role)
        priority = ROLE_PRIORITY.get(normalized, 0)
        if priority > best_priority:
            best = normalized
            best_priority = priority
    return best


def role_label(role: Optional[str]) -> str:
    return ROLE_LABELS.get(normalize_role(role), ROLE_LABELS[ROLE_VIEWER])


def is_blocked(is_allowed: Any) -> bool:
    """
    True, wenn eine Session keine Berechtigung hat.

    -1 = gesperrt, 0 = wartend/entzogen, False = nicht freigegeben.
    Nur 1/True gilt als freigeschaltet.
    """
    if is_allowed is False:
        return True
    try:
        return int(is_allowed) <= 0
    except (TypeError, ValueError):
        # Fehlende/unklare Claims gelten nicht als explizite Freigabe.
        return is_allowed is None


def permissions_for(role: Optional[str], is_allowed: Any = 1) -> FrozenSet[str]:
    """Rechte einer Rolle. Gesperrte Nutzer erhalten keinerlei Rechte."""
    if is_blocked(is_allowed):
        return frozenset()
    return ROLE_PERMISSIONS.get(normalize_role(role), frozenset())


def has_permission(payload: Optional[Dict[str, Any]], permission: str) -> bool:
    """Prueft ein Session-Payload auf ein einzelnes Recht."""
    if not payload:
        return False

    if is_blocked(payload.get("is_allowed", 1)):
        return False

    role = normalize_role(payload.get("role"))
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def has_any_permission(payload: Optional[Dict[str, Any]], permissions: Any) -> bool:
    return any(has_permission(payload, perm) for perm in permissions)


def session_permissions(payload: Optional[Dict[str, Any]]) -> FrozenSet[str]:
    """Alle Rechte eines Session-Payloads (fuer Frontend/Mini-App)."""
    if not payload:
        return frozenset()
    if is_blocked(payload.get("is_allowed", 1)):
        return frozenset()
    return ROLE_PERMISSIONS.get(normalize_role(payload.get("role")), frozenset())
