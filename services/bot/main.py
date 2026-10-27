import asyncio
import json
import logging
import os
import signal
import time

from shared.bus import get_bus
from shared.config import config
from shared.contracts import (
    KEY_DIAG_BOT,
    KEY_HEARTBEAT_BOT,
    LOCK_BOT,
    RPC_BOT_QUEUE,
)
from shared.database import init_db
from telegram_service import telegram_bot_service

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [bot] %(message)s",
)

# httpx/httpcore loggen jede Request-URL auf INFO. Die Telegram-Bot-API-URL
# enthält den Bot-Token – der landet damit im Klartext in den Container-Logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("toktracker.bot_service")


async def main():
    logger.info("Starte TokTracker Telegram-Bot Service (Role: %s, Redis: %s)...", config.service_role, config.has_redis)
    init_db()

    bus = get_bus()
    instance_id = f"bot-{os.uname().nodename if hasattr(os, 'uname') else 'host'}-{os.getpid()}"
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _sig_handler():
        logger.info("Signal empfangen – beende Telegram-Bot Service...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            pass

    # Leader Lock (stellt sicher, dass nur 1 Bot-Instanz Telegram Updates pollt)
    if config.has_redis:
        acquired = await bus.acquire_lease(LOCK_BOT, instance_id, ttl_seconds=15)
        while not acquired and not stop_event.is_set():
            logger.info("Eine andere Bot-Instanz hält bereits das Leader-Lock. Warte...")
            await asyncio.sleep(5.0)
            acquired = await bus.acquire_lease(LOCK_BOT, instance_id, ttl_seconds=15)

    # Bot starten
    await telegram_bot_service.start()

    # RPC Listener für Login-Challenges & Reports
    async def _handle_rpc(payload: dict) -> dict:
        action = payload.get("action")
        logger.info("Bot RPC Request empfangen: %s", action)
        if action == "send_login_challenge":
            identifier_hint = payload.get("identifier_hint")
            client_info = payload.get("client_info", "Web-Browser")
            return await telegram_bot_service.send_admin_login_challenge(
                identifier_hint=identifier_hint,
                client_info=client_info,
            )
        elif action == "send_report_now":
            chat_id = payload.get("chat_id")
            hours = int(payload.get("hours", 24))
            return await telegram_bot_service.send_report_now(chat_id=chat_id, hours=hours)
        return {"ok": False, "error": f"Unbekannte Action {action}"}

    if config.has_redis:
        await bus.rpc_listen(RPC_BOT_QUEUE, _handle_rpc)

    # Telemetrie & Heartbeat Loop
    async def _telemetry_loop():
        while not stop_event.is_set():
            try:
                if config.has_redis:
                    # Renew leader lock
                    await bus.renew_lease(LOCK_BOT, instance_id, ttl_seconds=15)
                    await bus.set_kv(KEY_HEARTBEAT_BOT, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ttl=15)

                    diag = telegram_bot_service.get_diagnostics()
                    await bus.set_kv(KEY_DIAG_BOT, json.dumps(diag, default=str), ttl=15)
            except Exception as exc:
                logger.debug("Fehler im Bot-Telemetrie-Loop: %s", exc)
            await asyncio.sleep(3.0)

    telemetry_task = asyncio.create_task(_telemetry_loop())

    await stop_event.wait()
    telemetry_task.cancel()

    await telegram_bot_service.stop()
    if config.has_redis:
        await bus.release_lease(LOCK_BOT, instance_id)
        await bus.delete_kv(KEY_HEARTBEAT_BOT)

    logger.info("Telegram-Bot Service sauber beendet.")


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        logger.info("uvloop für Telegram-Bot Service aktiviert.")
    except Exception:
        pass
    asyncio.run(main())
