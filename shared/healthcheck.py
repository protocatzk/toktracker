"""
TokTracker - Universal Container Healthcheck Script
Wird von Docker HEALTHCHECK verwendet:
  python -m shared.healthcheck <api|ingest|bot|scheduler>
"""

import json
import sys

import httpx

from shared.bus import get_bus
from shared.config import config
from shared.contracts import (
    KEY_HEARTBEAT_BOT,
    KEY_HEARTBEAT_SCHEDULER,
    PREFIX_DIAG_WORKER,
    PREFIX_HEARTBEAT_INGEST,
)


def check_api() -> bool:
    try:
        resp = httpx.get(f"http://127.0.0.1:{config.app_port}/api/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def check_ingest() -> bool:
    if not config.has_redis:
        return True
    try:
        bus = get_bus()
        keys = bus.scan_keys_sync(f"{PREFIX_HEARTBEAT_INGEST}*")
        if not keys:
            return False

        # Zusätzlich: Hängen alle verbundenen Worker ohne WebSocket-Frames?
        # Ein einzelner stale Worker ist noch kein Container-Notfall (der
        # In-Process-Watchdog greift dort selbst), aber ein komplett
        # verklemmter Ingest soll als unhealthy sichtbar werden.
        connected = []
        for key in bus.scan_keys_sync(f"{PREFIX_DIAG_WORKER}*"):
            raw = bus.get_kv_sync(key)
            if not raw:
                continue
            try:
                snap = json.loads(raw)
            except Exception:
                continue
            if snap.get("state") == "connected":
                connected.append(int(snap.get("last_frame_age_seconds", -1) or -1))

        return not (
            connected
            and all(age > (config.tiktok_stall_timeout * 2) for age in connected)
        )
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
