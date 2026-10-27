import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from shared.bus import get_bus
from shared.config import config
from shared.contracts import PREFIX_AUTH_CHALLENGE
from shared.database import list_telegram_users

logger = logging.getLogger("toktracker.auth")


class AdminAuthManager:
    """
    Verwaltet Telegram-basierte Admin-Logins (6-stelliger Einmal-Code / OTP sowie
    1-Klick-Freigabe per Telegram Inline-Button) und signierte Admin-Session-Cookies.
    Unterstützt sowohl Redis (verteilt über Microservices) als auch Memory-Fallback.
    """

    COOKIE_NAME = "toktracker_admin_session"
    CHALLENGE_TTL_SECONDS = 600  # 10 Minuten Gültigkeit
    SESSION_TTL_SECONDS = 86400 * 7  # Standard: 7 Tage (ohne Zugriffssperre)
    SESSION_TTL_GATED_SECONDS = 86400  # während ACCESS_GATE=whitelist: 24 Stunden
    MAX_CODE_ATTEMPTS = 5  # Fehlversuche pro Challenge, danach gesperrt

    def __init__(self) -> None:
        self._memory_challenges: Dict[str, Dict[str, Any]] = {}
        self.bus = get_bus()

    def _cleanup_memory_expired(self) -> None:
        now = time.time()
        expired = [cid for cid, ch in self._memory_challenges.items() if ch.get("expires_at", 0) < now]
        for cid in expired:
            self._memory_challenges.pop(cid, None)

    def _save_challenge(self, ch: Dict[str, Any]) -> None:
        cid = ch["challenge_id"]
        if config.has_redis:
            self.bus.set_kv_sync(f"{PREFIX_AUTH_CHALLENGE}{cid}", json.dumps(ch, default=str), ttl=self.CHALLENGE_TTL_SECONDS)
        else:
            self._cleanup_memory_expired()
            self._memory_challenges[cid] = ch

    def _load_challenge(self, cid: str) -> Optional[Dict[str, Any]]:
        if config.has_redis:
            raw = self.bus.get_kv_sync(f"{PREFIX_AUTH_CHALLENGE}{cid}")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except Exception:
                return None
        else:
            self._cleanup_memory_expired()
            return self._memory_challenges.get(cid)

    def _list_active_challenges(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if config.has_redis:
            keys = self.bus.scan_keys_sync(f"{PREFIX_AUTH_CHALLENGE}*")
            for k in keys:
                raw = self.bus.get_kv_sync(k)
                if raw:
                    try:
                        items.append(json.loads(raw))
                    except Exception:
                        pass
        else:
            self._cleanup_memory_expired()
            items = list(self._memory_challenges.values())
        return items

    def create_challenge(
        self,
        client_info: str = "Web-Browser",
        admin_label: str = "telegram_admin",
    ) -> Dict[str, Any]:
        challenge_id = secrets.token_hex(16)
        code = f"{secrets.randbelow(900000) + 100000}"
        now = time.time()
        challenge = {
            "challenge_id": challenge_id,
            "code": code,
            "created_at": now,
            "expires_at": now + self.CHALLENGE_TTL_SECONDS,
            "status": "pending",  # pending | approved | rejected | consumed | locked
            "attempts": 0,
            "admin_label": admin_label,
            "client_info": client_info,
        }
        self._save_challenge(challenge)
        return challenge

    def get_latest_pending_challenge(self) -> Optional[Dict[str, Any]]:
        pending = [ch for ch in self._list_active_challenges() if ch.get("status") == "pending"]
        if not pending:
            return None
        pending.sort(key=lambda c: c.get("created_at", 0), reverse=True)
        return pending[0]

    def approve_challenge(self, challenge_id: str, admin_label: str) -> Optional[Dict[str, Any]]:
        ch = self._load_challenge(challenge_id)
        if not ch or ch.get("status") not in ("pending", "approved"):
            return None
        ch["status"] = "approved"
        ch["admin_label"] = admin_label
        self._save_challenge(ch)
        return ch

    def reject_challenge(self, challenge_id: str, admin_label: str) -> Optional[Dict[str, Any]]:
        ch = self._load_challenge(challenge_id)
        if not ch:
            return None
        ch["status"] = "rejected"
        ch["admin_label"] = admin_label
        self._save_challenge(ch)
        return ch

    def get_recent_challenges(self, limit: int = 25) -> List[Dict[str, Any]]:
        items = self._list_active_challenges()
        items.sort(key=lambda c: c.get("created_at", 0), reverse=True)
        return items[:limit]

    def poll_challenge(self, challenge_id: str) -> Dict[str, Any]:
        ch = self._load_challenge(challenge_id)
        if not ch:
            return {"status": "expired"}
        status = ch.get("status", "pending")
        if status == "approved":
            ch["status"] = "consumed"
            self._save_challenge(ch)
            return {
                "status": "approved",
                "admin_label": ch.get("admin_label") or "telegram_admin",
                "attempts": int(ch.get("attempts") or 0),
            }
        return {"status": status, "attempts": int(ch.get("attempts") or 0)}

    def _is_code_challenge_open(self, challenge: Dict[str, Any]) -> bool:
        return str(challenge.get("status")) in ("pending", "approved")

    def _register_failed_attempt(self, challenge: Dict[str, Any]) -> None:
        """Zählt einen Fehlversuch und sperrt die Challenge ab MAX_CODE_ATTEMPTS."""
        attempts = int(challenge.get("attempts") or 0) + 1
        challenge["attempts"] = attempts
        if attempts >= self.MAX_CODE_ATTEMPTS:
            challenge["status"] = "locked"
            logger.warning(
                "Login-Challenge %s nach %s Fehlversuchen gesperrt.",
                challenge.get("challenge_id"),
                attempts,
            )
        self._save_challenge(challenge)

    def verify_code(self, code: str, challenge_id: Optional[str] = None) -> Optional[str]:
        clean_code = (code or "").strip().replace(" ", "")
        if not clean_code:
            return None

        # Fallback auf ADMIN_PASSWORD aus .env
        if config.admin_password and hmac.compare_digest(clean_code, config.admin_password):
            return "env_admin"

        if challenge_id:
            ch = self._load_challenge(challenge_id)
            if ch and self._is_code_challenge_open(ch):
                if hmac.compare_digest(str(ch.get("code", "")), clean_code):
                    ch["status"] = "consumed"
                    self._save_challenge(ch)
                    return str(ch.get("admin_label") or "telegram_admin")
                self._register_failed_attempt(ch)

        for ch in self._list_active_challenges():
            if self._is_code_challenge_open(ch) and hmac.compare_digest(str(ch.get("code", "")), clean_code):
                ch["status"] = "consumed"
                self._save_challenge(ch)
                return str(ch.get("admin_label") or "telegram_admin")

        return None

    def verify_telegram_auth(self, auth_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        received_hash = auth_data.get("hash")
        if not received_hash or not isinstance(received_hash, str):
            return False, "Fehlende Signatur (hash)", None

        try:
            auth_date = int(auth_data.get("auth_date", 0))
        except (ValueError, TypeError):
            return False, "Ungültiges auth_date Format", None

        now = int(time.time())
        if (now - auth_date) > 86400 or (auth_date - now) > 300:
            return False, "Login-Sitzung abgelaufen (älter als 24 Stunden)", None

        token = (config.telegram_bot_token or "").strip()
        if not token:
            return False, "Telegram Bot-Token nicht konfiguriert", None

        secret_key = hashlib.sha256(token.encode("utf-8")).digest()
        check_items = []
        for key in sorted(auth_data.keys()):
            if key == "hash":
                continue
            val = auth_data[key]
            if val is not None and val != "":
                check_items.append(f"{key}={val}")
        data_check_string = "\n".join(check_items)

        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            return False, "Ungültige kryptografische Signatur", None

        telegram_id = auth_data.get("id")
        username = (auth_data.get("username") or "").strip().lstrip("@")
        user_identifier = f"@{username}" if username else f"id:{telegram_id}"
        return True, None, user_identifier

    def session_ttl_seconds(self) -> int:
        """Kürzere Sessions, solange die Zugriffssperre aktiv ist."""
        return self.SESSION_TTL_GATED_SECONDS if config.has_access_gate else self.SESSION_TTL_SECONDS

    def create_session_token(
        self,
        admin_label: str = "telegram_admin",
        role: str = "admin",
        is_allowed: bool = True,
    ) -> str:
        payload = {
            "sub": admin_label,
            "role": role,
            "is_allowed": is_allowed,
            "iat": int(time.time()),
            "exp": int(time.time()) + self.session_ttl_seconds(),
            "nonce": secrets.token_hex(8),
        }
        raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
        sig = hmac.new(
            config.session_secret.encode("utf-8"),
            b64_payload.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return f"{b64_payload}.{sig}"

    def verify_session_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token or "." not in token:
            return None
        try:
            b64_payload, sig = token.rsplit(".", 1)
            expected_sig = hmac.new(
                config.session_secret.encode("utf-8"),
                b64_payload.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            padding = "=" * (-len(b64_payload) % 4)
            raw_bytes = base64.urlsafe_b64decode(b64_payload + padding)
            payload = json.loads(raw_bytes.decode("utf-8"))
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            payload.setdefault("role", "admin")
            payload.setdefault("is_allowed", True)
            return payload
        except Exception:
            return None

    def validate_webapp_init_data(self, init_data: str) -> Optional[Dict[str, Any]]:
        if not init_data or not config.telegram_bot_token:
            return None
        try:
            parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
            received_hash = parsed.pop("hash", None)
            if not received_hash:
                return None

            data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
            secret_key = hmac.new(
                b"WebAppData",
                config.telegram_bot_token.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            expected_hash = hmac.new(
                secret_key,
                data_check_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(received_hash, expected_hash):
                return None

            user_raw = parsed.get("user")
            user_data = json.loads(user_raw) if user_raw else {}
            auth_date = int(parsed.get("auth_date", 0))

            return {
                "user": user_data,
                "auth_date": auth_date,
                "query_id": parsed.get("query_id"),
                "chat_type": parsed.get("chat_type"),
            }
        except Exception:
            return None

    def is_admin_user(self, telegram_id: Optional[int] = None, username: Optional[str] = None) -> bool:
        clean_uname = (username or "").strip().lstrip("@").lower()

        if telegram_id is not None:
            try:
                tid = int(telegram_id)
                if tid in config.env_allowed_telegram_ids:
                    return True
            except (ValueError, TypeError):
                pass

        if clean_uname and clean_uname in config.env_allowed_telegram_usernames:
            return True

        try:
            users = list_telegram_users()
            for u in users:
                u_tid = u.get("telegram_id")
                u_uname = str(u.get("username") or "").strip().lstrip("@").lower()
                is_allowed = int(u.get("is_allowed", 0)) == 1
                is_admin = u.get("role") == "admin"

                if is_allowed and is_admin:
                    if telegram_id is not None and u_tid:
                        try:
                            if int(u_tid) == int(telegram_id):
                                return True
                        except (ValueError, TypeError):
                            pass
                    if clean_uname and u_uname and clean_uname == u_uname:
                        return True
        except Exception:
            pass

        return False


admin_auth_manager = AdminAuthManager()
