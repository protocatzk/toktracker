import asyncio
import logging
import signal

from services.ingest.coordinator import IngestCoordinator
from shared.config import config
from shared.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [ingest] %(message)s",
)

# httpx/httpcore loggen jede Request-URL auf INFO. Die Telegram-Bot-API-URL
# enthält den Bot-Token – der landet damit im Klartext in den Container-Logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("toktracker.ingest")


async def main():
    logger.info("Starte TokTracker Ingest Service (Role: %s, Redis: %s)...", config.service_role, config.has_redis)
    init_db()

    coordinator = IngestCoordinator()
    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def _sig_handler():
        logger.info("Signal empfangen – beende Ingest-Service...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            pass

    await coordinator.start()

    await stop_event.wait()
    await coordinator.stop()
    logger.info("Ingest Service erfolgreich beendet.")


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        logger.info("uvloop erfolgreich für Ingest Service aktiviert.")
    except Exception:
        pass
    asyncio.run(main())
