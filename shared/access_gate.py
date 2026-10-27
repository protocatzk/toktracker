"""
TokTracker - Zugriffssperre (Access Gate).

Solange `ACCESS_GATE=whitelist` gesetzt ist, sind nur folgende Flächen öffentlich:

* Login- und Logout-Seite sowie die Telegram-/Mini-App-Login-Endpunkte
  (sonst käme niemand mehr an eine Session),
* statische Assets (`/static`, `/pictures`),
* `/api/health` und `/robots.txt`,
* die Mini-App-Seite (`/miniapp`, `/app`, `/webapp`), damit dort der
  Telegram-`initData`-Login laufen kann.

Alles andere — auch `/`, `/public` und sämtliche Daten-APIs — erfordert eine
gültige Session (Rolle `admin` oder `is_allowed`) oder einen gültigen API-Key.
Die Logik ist bewusst hier gebündelt und frei von FastAPI-Abhängigkeiten, damit
sie ohne Server getestet werden kann.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Exakt erlaubte Pfade (ohne Login kommt man sonst nicht weiter).
EXEMPT_PATHS = frozenset({
    # Seiten
    "/login",
    "/logout",
    "/miniapp",
    "/app",
    "/webapp",
    # Infrastruktur
    "/robots.txt",
    "/favicon.ico",
    "/api/health",
    # Admin-Login (Browser + Telegram-Widget)
    "/api/auth/password",
    "/api/auth/logout",
    "/api/auth/telegram/request",
    "/api/auth/telegram/verify",
    "/api/auth/telegram/poll",
    "/api/auth/telegram/widget",
    "/api/auth/telegram/widget-callback",
    # Mini-App-Login (Telegram initData / OTP)
    "/api/miniapp/auth",
    "/api/miniapp/auth/status",
    "/api/miniapp/auth/request_otp",
    "/api/miniapp/auth/verify_otp",
    "/api/miniapp/auth/logout",
})

EXEMPT_PREFIXES = ("/static/", "/pictures/")


def is_exempt_path(path: str) -> bool:
    """True, wenn der Pfad ohne Anmeldung erreichbar bleiben muss."""
    if path in EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def session_grants_access(payload: Optional[Dict[str, Any]]) -> bool:
    """Admins und freigeschaltete Whitelist-Nutzer dürfen durch."""
    if not payload:
        return False
    return payload.get("role") == "admin" or payload.get("is_allowed") is True


def wants_json(path: str, accept_header: str = "") -> bool:
    """API-Aufrufe bekommen 401 statt eines Redirects auf die Login-Seite."""
    if path.startswith("/api/"):
        return True
    return "application/json" in (accept_header or "").lower()
