import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Lädt lokal die .env-Datei (sofern vorhanden).
# In Produktion (Docker / Systemd / Cloud) gesetzte echte Umgebungsvariablen haben Vorrang (override=False).
load_dotenv(dotenv_path=ENV_PATH, override=False)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


@dataclass
class AppConfig:
    # Server
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "5000"))

    # Datenbank
    db_path: str = os.getenv(
        "TIKTOK_DB_PATH",
        os.path.join(BASE_DIR, "tiktok_earnings.db"),
    )

    # API-Sicherheit für externe Zugriffe / Telegram-Bot
    api_key: str = os.getenv("TIKTOK_API_KEY", "").strip()

    # TikTokLive Session & Authentifizierung (für altersbeschränkte Streams / höhere Rate-Limits)
    tiktok_session_id: str = os.getenv("TIKTOK_SESSION_ID", "").strip()
    tiktok_target_idc: str = os.getenv("TIKTOK_TARGET_IDC", "eu-ttp2").strip()

    # EulerStream Sign-API-Key (wird von TikTokLive intern für WebSocket-Signierung genutzt)
    tiktok_sign_api_key: str = os.getenv("TIKTOK_SIGN_API_KEY", "").strip()

    # Optionale Proxies
    tiktok_web_proxy: Optional[str] = os.getenv("TIKTOK_WEB_PROXY", "").strip() or None
    tiktok_ws_proxy: Optional[str] = os.getenv("TIKTOK_WS_PROXY", "").strip() or None

    # Telegram Bot Vorbereitung (optional für direkten Versand oder Bot-Prozess)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    @property
    def has_tiktok_session(self) -> bool:
        return bool(self.tiktok_session_id)

    @property
    def has_sign_api_key(self) -> bool:
        return bool(self.tiktok_sign_api_key)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def public_summary(self) -> dict:
        """Gibt eine sichere, maskierte Übersicht für das Dashboard/Diagnose-JSON zurück (ohne Klartext-Secrets)."""
        return {
            "env_file_loaded": os.path.exists(ENV_PATH),
            "has_tiktok_session": self.has_tiktok_session,
            "tiktok_session_masked": _mask_secret(self.tiktok_session_id),
            "tiktok_target_idc": self.tiktok_target_idc if self.has_tiktok_session else "",
            "has_sign_api_key": self.has_sign_api_key,
            "sign_api_key_masked": _mask_secret(self.tiktok_sign_api_key),
            "has_api_key_protection": self.has_api_key,
            "has_web_proxy": bool(self.tiktok_web_proxy),
            "has_telegram_config": bool(self.telegram_bot_token and self.telegram_chat_id),
        }


config = AppConfig()
