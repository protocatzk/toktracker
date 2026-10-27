import asyncio
import json
import logging
from typing import Any, Dict, Optional

from shared.auth_store import admin_auth_manager
from shared.bus import get_bus
from shared.config import config
from shared.contracts import KEY_DIAG_BOT, RPC_BOT_QUEUE

logger = logging.getLogger("toktracker.bot_client")


class BotClient:
    """
    Client für Telegram-Bot Interaktionen.
    - Im All-in-One-Modus (Monolith): Greift direkt auf telegram_bot_service zu.
    - Im Microservice-Modus: Nutzt Redis RPC für Aktionen und Redis KV für Telemetrie.
    """

    def __init__(self):
        self._local_bot: Optional[Any] = None
        self.bus = get_bus()

    def set_local_bot(self, bot_service: Any) -> None:
        self._local_bot = bot_service

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._local_bot is not None and config.service_role in ("all", "bot"):
            try:
                return self._local_bot.get_diagnostics()
            except Exception as exc:
                logger.debug("Fehler bei lokalem get_diagnostics: %s", exc)

        if config.has_redis:
            raw = self.bus.get_kv_sync(KEY_DIAG_BOT)
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass

        # Fallback Telemetrie
        return {
            "sdk_available": True,
            "state": "remote" if config.has_redis else "disabled",
            "bot_username": "@toktracker_bot",
            "has_token": bool(config.telegram_bot_token),
            "default_chat_id": config.telegram_chat_id,
            "access_mode": config.telegram_access_mode,
            "group_support": True,
            "allowed_users_count": 0,
            "pending_users_count": 0,
            "started_at": None,
            "last_report_sent_at": None,
            "last_error": "",
            "logs": [],
        }

    async def send_admin_login_challenge(
        self,
        identifier_hint: Optional[str] = None,
        client_info: str = "Web-Browser",
    ) -> Dict[str, Any]:
        if self._local_bot is not None and config.service_role in ("all", "bot"):
            return await self._local_bot.send_admin_login_challenge(identifier_hint, client_info)

        # Challenge zuerst im AuthManager anlegen
        challenge = admin_auth_manager.create_challenge(client_info=client_info)
        cid = challenge["challenge_id"]
        code = challenge["code"]

        if not config.has_redis:
            return {
                "ok": True,
                "challenge_id": cid,
                "delivered_count": 0,
                "bot_running": False,
                "bot_username": "",
                "expires_in": admin_auth_manager.CHALLENGE_TTL_SECONDS,
                "message": f"Lokaler Einmal-Code: {code}",
            }

        # Per Redis RPC an den bot-Container senden
        res = await self.bus.rpc_call(
            RPC_BOT_QUEUE,
            {
                "action": "send_login_challenge",
                "challenge_id": cid,
                "code": code,
                "identifier_hint": identifier_hint,
                "client_info": client_info,
            },
            timeout=3.5,
        )

        if res.get("ok"):
            return res

        return {
            "ok": True,
            "challenge_id": cid,
            "delivered_count": 0,
            "bot_running": False,
            "bot_username": "",
            "expires_in": admin_auth_manager.CHALLENGE_TTL_SECONDS,
            "message": (
                f"Einmal-Code: {code}. Telegram-Bot antwortet aktuell nicht "
                f"({res.get('error', 'Keine Verbindung')})."
            ),
        }

    async def send_report_now(
        self, chat_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        if self._local_bot is not None and config.service_role in ("all", "bot"):
            return await self._local_bot.send_report_now(chat_id=chat_id, hours=hours)

        if not config.has_redis:
            return {"ok": False, "error": "Redis nicht konfiguriert und kein lokaler Bot aktiv."}

        return await self.bus.rpc_call(
            RPC_BOT_QUEUE,
            {
                "action": "send_report_now",
                "chat_id": chat_id,
                "hours": hours,
            },
            timeout=8.0,
        )

    async def start(self) -> None:
        if self._local_bot is not None and config.service_role in ("all", "bot"):
            await self._local_bot.start()

    async def stop(self) -> None:
        if self._local_bot is not None and config.service_role in ("all", "bot"):
            await self._local_bot.stop()


bot_client = BotClient()
