import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from typing import List, Optional, Set
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger("toktracker.config")

# Projekt-Wurzelverzeichnis (/app bzw. Repo-Root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = BASE_DIR
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Lädt lokal die .env-Datei (sofern vorhanden).
# In Produktion (Docker / Systemd / Cloud) gesetzte echte Umgebungsvariablen haben Vorrang (override=False).
# Nicht lesbare Dateien dürfen den Start nicht verhindern: In Containern kommen die
# Werte ohnehin aus der Prozess-Umgebung (compose env_file), die Datei ist dort optional.
try:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
except OSError as _env_err:  # z.B. PermissionError bei falschen File-Rechten
    logger.warning(".env konnte nicht gelesen werden (%s): %s", ENV_PATH, _env_err)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def _parse_csv_list(raw: str) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    """Liest ein Boolean aus der Umgebung (1/true/yes/on bzw. 0/false/no/off)."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AppConfig:
    # Server
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "5000"))

    # Service Role ("all", "api", "ingest", "bot", "scheduler")
    service_role: str = os.getenv("SERVICE_ROLE", "all").strip().lower()

    # Redis URL für Message-Bus & Shared State (z.B. redis://redis:6379/0)
    redis_url: str = os.getenv("REDIS_URL", "").strip()

    # Datenbank-Engine ("sqlite" oder "mysql")
    db_engine: str = os.getenv("DB_ENGINE", "sqlite").strip().lower()
    database_url: str = os.getenv("DATABASE_URL", "").strip()

    # Lokale SQLite-Datenbank (Standard, wenn DB_ENGINE=sqlite)
    db_path: str = os.getenv(
        "TIKTOK_DB_PATH",
        os.path.join(BASE_DIR, "tiktok_earnings.db"),
    )

    # Externer MySQL / MariaDB Server (aktiv, sobald DB_ENGINE=mysql oder DATABASE_URL=mysql://...)
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root").strip()
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "toktracker").strip()

    # API-Sicherheit & Admin-Session-Signierung
    api_key: str = os.getenv("TIKTOK_API_KEY", "").strip()
    session_secret: str = os.getenv("SESSION_SECRET", "").strip()
    admin_password: str = os.getenv("ADMIN_PASSWORD", "").strip()

    # Sicherheits-Härtung (WP 1): Cookie-Flags, Proxy-Vertrauen, API-Doku, API-Key per Query
    session_cookie_secure: str = os.getenv("SESSION_COOKIE_SECURE", "auto").strip().lower()
    trust_proxy_headers: bool = _env_bool("TRUST_PROXY_HEADERS", True)
    allow_api_key_query: bool = _env_bool("ALLOW_API_KEY_QUERY", True)
    enable_api_docs: bool = _env_bool("ENABLE_API_DOCS", False)

    # TikTokLive Session & Authentifizierung (für altersbeschränkte Streams / höhere Rate-Limits)
    tiktok_session_id: str = os.getenv("TIKTOK_SESSION_ID", "").strip()
    tiktok_target_idc: str = os.getenv("TIKTOK_TARGET_IDC", "eu-ttp2").strip()

    # EulerStream Sign-API-Key (wird von TikTokLive intern für WebSocket-Signierung genutzt)
    tiktok_sign_api_key: str = os.getenv("TIKTOK_SIGN_API_KEY", "").strip()

    # Optionale Proxies
    tiktok_web_proxy: Optional[str] = os.getenv("TIKTOK_WEB_PROXY", "").strip() or None
    tiktok_ws_proxy: Optional[str] = os.getenv("TIKTOK_WS_PROXY", "").strip() or None

    # Telegram Bot Konfiguration & Zugriffskontrolle
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    # Zugriffsmodus: "whitelist" oder "public"
    telegram_access_mode: str = os.getenv("TELEGRAM_ACCESS_MODE", "whitelist").strip().lower()
    # Kommagetrennte Telegram User-IDs oder [@]usernames aus der .env
    telegram_allowed_users_raw: str = os.getenv("TELEGRAM_ALLOWED_USERS", "").strip()
    # Optionale externe WebApp / Mini-App URL für Telegram
    telegram_webapp_url: str = os.getenv("TELEGRAM_WEBAPP_URL", os.getenv("WEBAPP_URL", "")).strip()

    # Wird in __post_init__ gesetzt: "env" | "derived" | "ephemeral"
    session_secret_source: str = ""

    def __post_init__(self) -> None:
        if self.database_url.lower().startswith(("mysql://", "mysql+pymysql://", "mariadb://")):
            parsed = urlparse(self.database_url)
            self.db_engine = "mysql"
            if parsed.hostname:
                self.mysql_host = parsed.hostname
            if parsed.port:
                self.mysql_port = int(parsed.port)
            if parsed.username:
                self.mysql_user = parsed.username
            if parsed.password is not None:
                self.mysql_password = parsed.password
            if parsed.path and parsed.path.strip("/"):
                self.mysql_database = parsed.path.strip("/")

        self._init_session_secret()
        if self.session_cookie_secure not in ("auto", "1", "0", "true", "false", "yes", "no", "on", "off", "always"):
            logger.warning(
                "Ungültiger SESSION_COOKIE_SECURE-Wert '%s' – verwende 'auto'.", self.session_cookie_secure
            )
            self.session_cookie_secure = "auto"

    def _init_session_secret(self) -> None:
        """
        Härtet die Session-Signierung:
        1. Explizit gesetztes SESSION_SECRET wird validiert (min. 32 Zeichen).
        2. Ohne SESSION_SECRET, aber mit Bot-Token und API-Key: deterministische Ableitung
           (bisheriges Verhalten, damit Sessions Neustarts überleben) + Warnung.
        3. Sonst: zufälliges Secret zur Laufzeit (sicher, aber Sessions überleben keinen Neustart).
        """
        if self.session_secret:
            if len(self.session_secret) < 32:
                raise ValueError(
                    "SESSION_SECRET ist zu kurz (min. 32 Zeichen). "
                    'Erzeugen mit: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            self.session_secret_source = "env"
            return

        if self.telegram_bot_token and self.api_key:
            seed = f"toktracker-session-{self.telegram_bot_token}-{self.api_key}-{BASE_DIR}"
            self.session_secret = hashlib.sha256(seed.encode("utf-8")).hexdigest()
            self.session_secret_source = "derived"
            logger.warning(
                "SESSION_SECRET nicht gesetzt – Secret wird aus TELEGRAM_BOT_TOKEN + TIKTOK_API_KEY abgeleitet. "
                "Bitte ein eigenes SESSION_SECRET (32+ Zeichen) in der .env setzen."
            )
            return

        self.session_secret = secrets.token_hex(32)
        self.session_secret_source = "ephemeral"
        logger.warning(
            "SESSION_SECRET nicht gesetzt und keine Ableitungsquelle vorhanden – es wird ein zufälliges "
            "Laufzeit-Secret erzeugt. Alle Admin-Sessions werden bei jedem Neustart ungültig!"
        )

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def is_mysql(self) -> bool:
        return self.db_engine in ("mysql", "mariadb")

    @property
    def has_tiktok_session(self) -> bool:
        return bool(self.tiktok_session_id)

    @property
    def has_sign_api_key(self) -> bool:
        return bool(self.tiktok_sign_api_key)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def env_allowed_telegram_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for item in _parse_csv_list(self.telegram_allowed_users_raw):
            clean = item.lstrip("@").strip()
            if clean.lstrip("-").isdigit():
                ids.add(int(clean))
        if self.telegram_chat_id and self.telegram_chat_id.lstrip("-").isdigit():
            cid = int(self.telegram_chat_id)
            if cid > 0:
                ids.add(cid)
        return ids

    @property
    def env_allowed_telegram_usernames(self) -> Set[str]:
        names: Set[str] = set()
        for item in _parse_csv_list(self.telegram_allowed_users_raw):
            clean = item.lstrip("@").strip().lower()
            if clean and not clean.lstrip("-").isdigit():
                names.add(clean)
        return names

    def public_summary(self) -> dict:
        """Gibt eine sichere, maskierte Übersicht für das Dashboard/Diagnose-JSON zurück."""
        return {
            "env_file_loaded": os.path.exists(ENV_PATH),
            "service_role": self.service_role,
            "has_redis": self.has_redis,
            "db_engine": "mysql" if self.is_mysql else "sqlite",
            "db_target": (
                f"{self.mysql_user}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
                if self.is_mysql
                else os.path.basename(self.db_path)
            ),
            "has_tiktok_session": self.has_tiktok_session,
            "tiktok_session_masked": _mask_secret(self.tiktok_session_id),
            "tiktok_target_idc": self.tiktok_target_idc if self.has_tiktok_session else "",
            "has_sign_api_key": self.has_sign_api_key,
            "sign_api_key_masked": _mask_secret(self.tiktok_sign_api_key),
            "has_api_key_protection": self.has_api_key,
            "api_key_query_allowed": self.allow_api_key_query,
            "api_docs_enabled": self.enable_api_docs,
            "session_secret_source": self.session_secret_source,
            "session_cookie_secure": self.session_cookie_secure,
            "trust_proxy_headers": self.trust_proxy_headers,
            "has_web_proxy": bool(self.tiktok_web_proxy),
            "has_telegram_config": bool(self.telegram_bot_token),
            "telegram_access_mode": self.telegram_access_mode,
            "telegram_webapp_url": self.telegram_webapp_url,
        }


config = AppConfig()
