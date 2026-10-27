"""
TokTracker - Test-Bootstrap (muss VOR jedem Import von `app` / `shared.*` laufen).

Zweck:
- Tests laufen niemals gegen die Produktions-Datenbank (immer SQLite in einem
  temporären Verzeichnis).
- Deterministische Secrets/API-Keys, keine Telegram-Verbindungen.
- Redis ist opt-in über `TOKTRACKER_TEST_REDIS_URL` (z.B. CI-Service-Container).

Verwendung am Anfang jedes Testmoduls:

    try:
        from . import _bootstrap  # noqa: F401  (pytest: Paket-Import)
    except ImportError:
        import _bootstrap  # noqa: F401         (unittest discover / direkt)
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_BOOTSTRAP_FLAG = "TOKTRACKER_TEST_BOOTSTRAPPED"

# Idempotent: bei doppeltem Import (z.B. Container-Kopie + Repo-Paket) wird die
# bereits konfigurierte Umgebung wiederverwendet statt eine zweite DB anzulegen.
_ALREADY_BOOTSTRAPPED = os.environ.get(_BOOTSTRAP_FLAG) == "1"

if _ALREADY_BOOTSTRAPPED:
    _TMP_DIR = os.path.dirname(os.environ.get("TIKTOK_DB_PATH", "")) or tempfile.mkdtemp(prefix="toktracker-tests-")
    _DB_PATH = os.environ.get("TIKTOK_DB_PATH") or os.path.join(_TMP_DIR, "toktracker_test.db")
else:
    _TMP_DIR = tempfile.mkdtemp(prefix="toktracker-tests-")
    _DB_PATH = os.path.join(_TMP_DIR, "toktracker_test.db")

    def _cleanup() -> None:
        shutil.rmtree(_TMP_DIR, ignore_errors=True)

    atexit.register(_cleanup)

# --- Datenbank: immer isolierte SQLite-Datei ---------------------------------
os.environ["DB_ENGINE"] = "sqlite"
os.environ["TIKTOK_DB_PATH"] = _DB_PATH
os.environ.pop("DATABASE_URL", None)

if not _ALREADY_BOOTSTRAPPED:
    # --- Bus: standardmäßig MemoryBus, Redis nur explizit --------------------
    _test_redis = os.environ.get("TOKTRACKER_TEST_REDIS_URL", "").strip()
    os.environ["REDIS_URL"] = _test_redis

    # --- Service-Rolle & Secrets ---------------------------------------------
    os.environ["SERVICE_ROLE"] = "test"
    os.environ["SESSION_SECRET"] = "test-" + "0" * 60
    os.environ["ADMIN_PASSWORD"] = ""
    os.environ["TIKTOK_API_KEY"] = "test-api-key"
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["TELEGRAM_CHAT_ID"] = ""
    os.environ["TELEGRAM_ALLOWED_USERS"] = ""
    os.environ["TELEGRAM_ACCESS_MODE"] = "whitelist"
    os.environ["ENABLE_API_DOCS"] = "0"
    os.environ["ALLOW_API_KEY_QUERY"] = "1"
    os.environ["TRUST_PROXY_HEADERS"] = "1"
    os.environ["SESSION_COOKIE_SECURE"] = "auto"
    os.environ["LOG_LEVEL"] = "WARNING"  # Test-Läufe nicht mit INFO-Logs fluten
    os.environ[_BOOTSTRAP_FLAG] = "1"

TEST_DB_PATH = _DB_PATH
TEST_REDIS_URL = os.environ.get("REDIS_URL", "")

# Schema einmalig anlegen, damit alle Tests ohne Lifespan/API-Bootstrap laufen.
from shared.database import init_db  # noqa: E402

init_db()
