"""
TokTracker - zentrale Rollen- und Rechteverwaltung.

Die Rechte sind bewusst als feine, stringbasierte Capabilities modelliert.
Rollen bilden diese Capabilities auf feste Mengen ab. So koennen einzelne
Endpunkte genau ein Recht verlangen, ohne die Rolle selbst zu kennen.

Die Datei ist frei von FastAPI- und Datenbankabhaengigkeiten und damit
isoliert testbar.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Tuple

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

# ---------------------------------------------------------------------------
# Bot-Capabilities
#
# Bot-Befehle werden bewusst ueber eigene bot.*-Rechte gesteuert. So kann eine
# Rolle im Web mehr sehen als im Telegram-Bot (oder umgekehrt), ohne dass die
# beiden Oberflaechen aneinander gekoppelt sind.
# ---------------------------------------------------------------------------

PERM_BOT_PUBLIC_VIEW = "bot.public.view"
PERM_BOT_RADAR_VIEW = "bot.radar.view"
PERM_BOT_ANALYTICS_VIEW = "bot.analytics.view"
PERM_BOT_SYSTEM_VIEW = "bot.system.view"
PERM_BOT_CRM_EDIT = "bot.crm.edit"
PERM_BOT_STREAMERS_MANAGE = "bot.streamers.manage"
PERM_BOT_USERS_MANAGE = "bot.users.manage"
PERM_BOT_SETTINGS_MANAGE = "bot.settings.manage"
PERM_BOT_ADMIN_LOGIN = "bot.admin.login"

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
    PERM_BOT_PUBLIC_VIEW,
    PERM_BOT_RADAR_VIEW,
    PERM_BOT_ANALYTICS_VIEW,
    PERM_BOT_SYSTEM_VIEW,
    PERM_BOT_CRM_EDIT,
    PERM_BOT_STREAMERS_MANAGE,
    PERM_BOT_USERS_MANAGE,
    PERM_BOT_SETTINGS_MANAGE,
    PERM_BOT_ADMIN_LOGIN,
})

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    ROLE_VIEWER: frozenset({
        PERM_PUBLIC_VIEW,
        PERM_BOT_PUBLIC_VIEW,
    }),
    ROLE_USER: frozenset({
        PERM_PUBLIC_VIEW,
        PERM_RADAR_VIEW,
        PERM_CHATINTEL_VIEW,
        PERM_BOT_PUBLIC_VIEW,
        PERM_BOT_RADAR_VIEW,
    }),
    ROLE_MODERATOR: frozenset({
        PERM_PUBLIC_VIEW,
        PERM_RADAR_VIEW,
        PERM_CHATINTEL_VIEW,
        PERM_ANALYTICS_VIEW,
        PERM_EXPORT_DOWNLOAD,
        PERM_SYSTEM_VIEW,
        PERM_BOT_PUBLIC_VIEW,
        PERM_BOT_RADAR_VIEW,
        PERM_BOT_ANALYTICS_VIEW,
        PERM_BOT_SYSTEM_VIEW,
    }),
    ROLE_ADMIN: ALL_PERMISSIONS,
}

# Lesbare Labels fuer Web-UI, Bot-Hilfe und die Rechte-Matrix unter /access.
PERMISSION_LABELS: Dict[str, str] = {
    PERM_PUBLIC_VIEW: "Öffentliche Seiten ansehen",
    PERM_RADAR_VIEW: "Spender-Radar & Chatlogs ansehen",
    PERM_CHATINTEL_VIEW: "Chat-Intelligence ansehen",
    PERM_ANALYTICS_VIEW: "Statistiken & Analytics ansehen",
    PERM_EXPORT_DOWNLOAD: "CSV-Exporte herunterladen",
    PERM_SYSTEM_VIEW: "Systemstatus ansehen",
    PERM_CRM_EDIT: "CRM & VIP-Markierungen bearbeiten",
    PERM_STREAMERS_MANAGE: "Streamer verwalten & tracken",
    PERM_GIFTS_BOOK: "Geschenke manuell buchen",
    PERM_SETTINGS_MANAGE: "Einstellungen & Zugriffsmodus verwalten",
    PERM_USERS_MANAGE: "Nutzer, Whitelist & Rollen verwalten",
    PERM_SYSTEM_MANAGE: "System verwalten",
    PERM_REPORTS_SEND: "Reports versenden",
    PERM_BOT_PUBLIC_VIEW: "Bot: öffentliche Befehle",
    PERM_BOT_RADAR_VIEW: "Bot: Radar, Whales & Spender",
    PERM_BOT_ANALYTICS_VIEW: "Bot: Reports & Statistiken",
    PERM_BOT_SYSTEM_VIEW: "Bot: Worker-/Systemstatus",
    PERM_BOT_CRM_EDIT: "Bot: VIP-/CRM-Aktionen",
    PERM_BOT_STREAMERS_MANAGE: "Bot: Streamer & Live-Alerts verwalten",
    PERM_BOT_USERS_MANAGE: "Bot: Whitelist & Rollen verwalten",
    PERM_BOT_SETTINGS_MANAGE: "Bot: Zugriffsmodus umschalten",
    PERM_BOT_ADMIN_LOGIN: "Bot: Web-Admin-Login freigeben",
}

# ---------------------------------------------------------------------------
# Bot-Befehl -> Capability
#
# Diese Map ist die einzige Quelle fuer die Rechtezuordnung der Bot-Befehle.
# Aliase werden auf den kanonischen Befehlsnamen normalisiert.
# ---------------------------------------------------------------------------

BOT_COMMAND_PERMISSIONS: Dict[str, Optional[str]] = {
    "help": PERM_BOT_PUBLIC_VIEW,
    "miniapp": PERM_BOT_PUBLIC_VIEW,
    "whoami": None,  # Zeigt nur den eigenen Status und bleibt immer erreichbar.
    "streamers": PERM_BOT_PUBLIC_VIEW,
    "gifts": PERM_BOT_PUBLIC_VIEW,
    "overview": PERM_BOT_ANALYTICS_VIEW,
    "report": PERM_BOT_ANALYTICS_VIEW,
    "streamer": PERM_BOT_ANALYTICS_VIEW,
    "radar": PERM_BOT_RADAR_VIEW,
    "whales": PERM_BOT_RADAR_VIEW,
    "donor": PERM_BOT_RADAR_VIEW,
    "vip": PERM_BOT_RADAR_VIEW,
    "loyalty": PERM_BOT_RADAR_VIEW,
    "status": PERM_BOT_SYSTEM_VIEW,
    "login": PERM_BOT_ADMIN_LOGIN,
    "add": PERM_BOT_STREAMERS_MANAGE,
    "track": PERM_BOT_STREAMERS_MANAGE,
    "stop": PERM_BOT_STREAMERS_MANAGE,
    "alert": PERM_BOT_STREAMERS_MANAGE,
    "allow": PERM_BOT_USERS_MANAGE,
    "revoke": PERM_BOT_USERS_MANAGE,
    "users": PERM_BOT_USERS_MANAGE,
    "mode": PERM_BOT_SETTINGS_MANAGE,
}

BOT_COMMAND_ALIASES: Dict[str, str] = {
    "start": "help",
    "help": "help",
    "app": "miniapp",
    "miniapp": "miniapp",
    "id": "whoami",
    "whoami": "whoami",
    "overview": "overview",
    "dashboard": "overview",
    "finanzen": "overview",
    "radar": "radar",
    "whales_radar": "radar",
    "whales": "whales",
    "whale_alerts": "whales",
    "alerts": "whales",
    "donor": "donor",
    "dossier": "donor",
    "spender": "donor",
    "vip": "vip",
    "vips": "vip",
    "loyalty": "loyalty",
    "switchers": "loyalty",
    "frontenwechsler": "loyalty",
    "streamers": "streamers",
    "channels": "streamers",
    "liste": "streamers",
    "gifts": "gifts",
    "geschenke": "gifts",
    "ticker": "gifts",
    "report": "report",
    "bericht": "report",
    "streamer": "streamer",
    "stats": "streamer",
    "status": "status",
    "worker": "status",
    "workers": "status",
    "login": "login",
    "add": "add",
    "track": "track",
    "stop": "stop",
    "alert": "alert",
    "livealert": "alert",
    "livealerts": "alert",
    "allow": "allow",
    "revoke": "revoke",
    "users": "users",
    "mode": "mode",
}

BOT_COMMAND_LABELS: Dict[str, str] = {
    "help": "/help, /start",
    "miniapp": "/app, /miniapp",
    "whoami": "/id, /whoami",
    "streamers": "/streamers, /channels, /liste",
    "gifts": "/gifts, /geschenke, /ticker",
    "overview": "/overview, /dashboard, /finanzen",
    "report": "/report",
    "streamer": "/streamer, /stats",
    "radar": "/radar",
    "whales": "/whales, /alerts",
    "donor": "/donor, /spender",
    "vip": "/vip",
    "loyalty": "/loyalty, /switchers",
    "status": "/status, /worker",
    "login": "/login",
    "add": "/add",
    "track": "/track",
    "stop": "/stop",
    "alert": "/alert, /livealert",
    "allow": "/allow",
    "revoke": "/revoke",
    "users": "/users",
    "mode": "/mode",
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


# ---------------------------------------------------------------------------
# Bot-Befehl-Hilfsfunktionen
# ---------------------------------------------------------------------------

def normalize_bot_command(command: Optional[str]) -> Optional[str]:
    """Normalisiert einen Bot-Befehl (inkl. Alias) auf seinen kanonischen Namen."""
    if not command:
        return None
    clean = str(command).strip().lower().lstrip("/").split("@", 1)[0]
    return BOT_COMMAND_ALIASES.get(clean, clean if clean in BOT_COMMAND_PERMISSIONS else None)


def is_known_bot_command(command: Optional[str]) -> bool:
    """True, wenn der Befehl (inkl. Alias) in der zentralen Matrix bekannt ist."""
    return normalize_bot_command(command) in BOT_COMMAND_PERMISSIONS


def bot_command_permission(command: Optional[str]) -> Optional[str]:
    """Liefert die fuer einen Bot-Befehl benoetigte Capability (None = ohne Pruefung)."""
    canonical = normalize_bot_command(command)
    if canonical is None:
        return None
    return BOT_COMMAND_PERMISSIONS.get(canonical)


def bot_command_allowed(command: Optional[str], role: Optional[str], is_allowed: Any = 1) -> bool:
    """True, wenn die Rolle den Bot-Befehl ausfuehren darf. Unbekannte Befehle: False."""
    canonical = normalize_bot_command(command)
    if canonical is None:
        return False
    required = BOT_COMMAND_PERMISSIONS.get(canonical)
    if required is None:
        return True
    return required in permissions_for(role, is_allowed)


def bot_commands_for(role: Optional[str], is_allowed: Any = 1) -> Tuple[str, ...]:
    """Alle kanonischen Bot-Befehle, die eine Rolle ausfuehren darf."""
    perms = permissions_for(role, is_allowed)
    return tuple(
        command
        for command, required in BOT_COMMAND_PERMISSIONS.items()
        if required is None or required in perms
    )


def permission_label(permission: str) -> str:
    """Lesbares Label fuer eine Capability (Fallback: Rohwert)."""
    return PERMISSION_LABELS.get(permission, permission)

