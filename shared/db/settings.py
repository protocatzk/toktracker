"""
TokTracker - Key-Value-Settings inkl. 30s-Cache (Kurse, Zugriffsmodus, Banner).
"""

import threading
import time
from typing import Any, Dict, Optional

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False

from shared.config import config
from shared.db._base import DEFAULT_SETTINGS, get_db

_settings_cache: Optional[Dict[str, Any]] = None


_settings_cache_time: float = 0.0


_settings_cache_lock = threading.Lock()


_SETTINGS_TTL = 30.0  # Sekunden Cache gegen DB-Spamming


def invalidate_settings_cache() -> None:
    global _settings_cache_time
    _settings_cache_time = 0.0


def get_settings(force_refresh: bool = False) -> Dict[str, Any]:
    global _settings_cache, _settings_cache_time
    now = time.monotonic()
    if not force_refresh and _settings_cache is not None and (now - _settings_cache_time) < _SETTINGS_TTL:
        return _settings_cache.copy()

    with _settings_cache_lock:
        if not force_refresh and _settings_cache is not None and (now - _settings_cache_time) < _SETTINGS_TTL:
            return _settings_cache.copy()

        with get_db() as conn:
            rows = conn.execute("SELECT `key`, `value` FROM settings").fetchall()
            data = {r["key"]: r["value"] for r in rows}
        mode = str(data.get("telegram_access_mode", config.telegram_access_mode or "whitelist")).lower()
        if mode not in ("whitelist", "public"):
            mode = "whitelist"

        banner_enabled_raw = str(data.get("public_banner_enabled", DEFAULT_SETTINGS["public_banner_enabled"])).strip().lower()
        banner_style = str(data.get("public_banner_style", DEFAULT_SETTINGS["public_banner_style"])).strip().lower()
        if banner_style not in ("highlight", "info", "success", "warning"):
            banner_style = "highlight"

        res = {
            "usd_per_diamond": float(data.get("usd_per_diamond", 0.005)),
            "gross_usd_per_coin": float(data.get("gross_usd_per_coin", 0.0106)),
            "usd_to_eur_rate": float(data.get("usd_to_eur_rate", 0.92)),
            "currency_primary": data.get("currency_primary", "EUR"),
            "poll_interval_seconds": int(float(data.get("poll_interval_seconds", 45))),
            "api_key": str(data.get("api_key", "")),
            "telegram_access_mode": mode,
            "public_banner_enabled": banner_enabled_raw in ("1", "true", "yes", "on"),
            "public_banner_title": str(data.get("public_banner_title", DEFAULT_SETTINGS["public_banner_title"])),
            "public_banner_text": str(data.get("public_banner_text", DEFAULT_SETTINGS["public_banner_text"])),
            "public_banner_style": banner_style,
            "public_banner_btn_text": str(data.get("public_banner_btn_text", DEFAULT_SETTINGS["public_banner_btn_text"])),
            "public_banner_btn_url": str(data.get("public_banner_btn_url", DEFAULT_SETTINGS["public_banner_btn_url"])),
            "public_show_donors": str(
                data.get("public_show_donors", DEFAULT_SETTINGS["public_show_donors"])
            ).strip().lower() in ("1", "true", "yes", "on"),
        }
        _settings_cache = res
        _settings_cache_time = now
        return res.copy()


def update_settings(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    with get_db() as conn:
        for key in DEFAULT_SETTINGS:
            if key in new_settings and new_settings[key] is not None:
                val = str(new_settings[key]).strip()
                if key == "telegram_access_mode":
                    val = val.lower()
                    if val not in ("whitelist", "public"):
                        continue
                elif key == "public_banner_enabled" or key == "public_show_donors":
                    val = "1" if str(new_settings[key]).strip().lower() in ("1", "true", "yes", "on") else "0"
                elif key == "public_banner_style":
                    val = val.lower()
                    if val not in ("highlight", "info", "success", "warning"):
                        val = "highlight"
                conn.execute(
                    "INSERT OR REPLACE INTO settings (`key`, `value`) VALUES (?, ?)",
                    (key, val),
                )
    invalidate_settings_cache()
    return get_settings(force_refresh=True)


def get_telegram_access_mode() -> str:
    return get_settings().get("telegram_access_mode", "whitelist")


def set_telegram_access_mode(mode: str) -> str:
    clean_mode = mode.strip().lower()
    if clean_mode not in ("whitelist", "public"):
        raise ValueError("Modus muss 'whitelist' oder 'public' sein.")
    update_settings({"telegram_access_mode": clean_mode})
    return clean_mode
