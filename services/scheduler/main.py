import asyncio
import logging
import os
import signal
import time

from shared.bot_client import bot_client
from shared.bus import get_bus
from shared.config import config
from shared.contracts import KEY_HEARTBEAT_SCHEDULER, LOCK_SCHEDULER
from shared.database import (
    cleanup_old_chat_messages,
    init_db,
)
from system_service import get_system_health
from tiktok_service import refresh_donor_tier_cache

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [scheduler] %(message)s",
)
logger = logging.getLogger("toktracker.scheduler")

KEY_LAST_REPORT_TIME = "tt:scheduler:last_24h_report"


async def main():
    logger.info("Starte TokTracker Scheduler Service (Role: %s, Redis: %s)...", config.service_role, config.has_redis)
    init_db()

    bus = get_bus()
    instance_id = f"scheduler-{os.uname().nodename if hasattr(os, 'uname') else 'host'}-{os.getpid()}"
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _sig_handler():
        logger.info("Signal empfangen – beende Scheduler Service...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            pass

    # Leader Lock
    if config.has_redis:
        acquired = await bus.acquire_lease(LOCK_SCHEDULER, instance_id, ttl_seconds=15)
        while not acquired and not stop_event.is_set():
            logger.info("Eine andere Scheduler-Instanz hält das Leader-Lock. Warte...")
            await asyncio.sleep(5.0)
            acquired = await bus.acquire_lease(LOCK_SCHEDULER, instance_id, ttl_seconds=15)

    # 1. Heartbeat Loop
    async def _heartbeat_loop():
        while not stop_event.is_set():
            try:
                if config.has_redis:
                    await bus.renew_lease(LOCK_SCHEDULER, instance_id, ttl_seconds=15)
                    await bus.set_kv(KEY_HEARTBEAT_SCHEDULER, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ttl=15)
            except Exception as exc:
                logger.debug("Heartbeat Fehler im Scheduler: %s", exc)
            await asyncio.sleep(5.0)

    # 2. 24h-Report Job (prüft alle 60 Sekunden)
    async def _report_job_loop():
        while not stop_event.is_set():
            try:
                if config.telegram_chat_id:
                    last_ts_str = await bus.get_kv(KEY_LAST_REPORT_TIME)
                    last_ts = float(last_ts_str) if last_ts_str else 0.0
                    now = time.time()

                    # Wenn noch nie gelaufen oder > 24h her
                    if last_ts == 0.0:
                        # Initialisiere auf jetzt, damit beim Containerstart nicht gespammt wird
                        await bus.set_kv(KEY_LAST_REPORT_TIME, str(now))
                    elif (now - last_ts) >= 86400:
                        logger.info("24h-Report fällig – versende automatischen Bericht...")
                        res = await bot_client.send_report_now(chat_id=config.telegram_chat_id, hours=24)
                        if res.get("ok"):
                            await bus.set_kv(KEY_LAST_REPORT_TIME, str(now))
                            logger.info("24h-Report erfolgreich versendet.")
                        else:
                            logger.warning("24h-Report konnte nicht versendet werden: %s", res.get("error"))
            except Exception as exc:
                logger.error("Fehler im 24h-Report-Scheduler-Job: %s", exc)

            await asyncio.sleep(60.0)

    # 3. Disk-Health & System-Monitor Job (alle 15 Minuten)
    async def _disk_health_loop():
        last_alert_time = 0.0
        alert_active = False

        while not stop_event.is_set():
            try:
                health = await asyncio.to_thread(get_system_health, True)
                disk = health.get("host", {}).get("disk", {})
                pct = float(disk.get("percent", 0.0))
                now = time.time()

                if pct >= 85.0:
                    if not alert_active or (now - last_alert_time) > 14400:
                        alert_active = True
                        last_alert_time = now
                        logger.warning("Kritischer Speicherplatz erkannt (%.1f%%)", pct)
                        # Optional: Alert an Bot senden
                elif pct < 78.0 and alert_active:
                    alert_active = False
                    logger.info("Speicherplatz wieder normalisiert (%.1f%%)", pct)

            except Exception as exc:
                logger.debug("Fehler im Disk-Health-Job: %s", exc)

            await asyncio.sleep(900.0)

    # 4. DB Cleanup & Donor Cache Job (alle 6 Stunden)
    async def _maintenance_loop():
        while not stop_event.is_set():
            try:
                logger.info("Führe geplante Wartungsaufgaben aus (Chat Cleanup & Donor Cache)...")
                await asyncio.to_thread(cleanup_old_chat_messages, days=7)
                await asyncio.to_thread(refresh_donor_tier_cache)
            except Exception as exc:
                logger.debug("Fehler im Wartungs-Job: %s", exc)

            await asyncio.sleep(21600.0)

    t1 = asyncio.create_task(_heartbeat_loop())
    t2 = asyncio.create_task(_report_job_loop())
    t3 = asyncio.create_task(_disk_health_loop())
    t4 = asyncio.create_task(_maintenance_loop())

    await stop_event.wait()
    t1.cancel()
    t2.cancel()
    t3.cancel()
    t4.cancel()

    if config.has_redis:
        await bus.release_lease(LOCK_SCHEDULER, instance_id)
        await bus.delete_kv(KEY_HEARTBEAT_SCHEDULER)

    logger.info("Scheduler Service sauber beendet.")


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        logger.info("uvloop für Scheduler Service aktiviert.")
    except Exception:
        pass
    asyncio.run(main())
