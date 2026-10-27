"""
TokTracker - Universal Container Healthcheck Script
Wird von Docker HEALTHCHECK verwendet:
  python -m shared.healthcheck <api|ingest|bot|scheduler>
"""

import sys
import time
import httpx
from shared.bus import get_bus
from shared.config import config
from shared.contracts import (
    KEY_HEARTBEAT_BOT,
    KEY_HEARTBEAT_SCHEDULER,
    PREFIX_HEARTBEAT_INGEST,
)


def check_api() -> bool:
    try:
        resp = httpx.get(f"http://127.0.0.1:{config.app_port}/", timeout=3.0)
        return resp.status_code in (200, 302, 307)
    except Exception:
        return False


def check_ingest() -> bool:
    if not config.has_redis:
        return True
    try:
        bus = get_bus()
        keys = bus.scan_keys_sync(f"{PREFIX_HEARTBEAT_INGEST}*")
        return len(keys) > 0
    except Exception:
        return False


def check_bot() -> bool:
    if not config.has_redis or not config.telegram_bot_token:
        return True
    try:
        bus = get_bus()
        val = bus.get_kv_sync(KEY_HEARTBEAT_BOT)
        return bool(val)
    except Exception:
        return False


def check_scheduler() -> bool:
    if not config.has_redis:
        return True
    try:
        bus = get_bus()
        val = bus.get_kv_sync(KEY_HEARTBEAT_SCHEDULER)
        return bool(val)
    except Exception:
        return False


def main():
    role = sys.argv[1].lower() if len(sys.argv) > 1 else "api"
    success = False
    if role == "api":
        success = check_api()
    elif role == "ingest":
        success = check_ingest()
    elif role == "bot":
        success = check_bot()
    elif role == "scheduler":
        success = check_scheduler()
    else:
        success = True

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
