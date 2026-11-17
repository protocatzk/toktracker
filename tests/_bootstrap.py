"""
TokTracker - Test-Bootstrap (muss VOR jedem Import von `app` / `shared.*` laufen).

Zweck:
- Tests laufen niemals gegen die Produktions-/Entwicklungsdatenbank: jeder Lauf
  legt eine eigene MariaDB-Datenbank (`toktracker_test_<pid>_<token>`) an und
  droppt sie am Ende wieder.
- Das Schema wird gegen dieselbe Engine geprüft, die auch in Produktion läuft
  (MariaDB/MySQL) – kein abweichender SQLite-Testdialekt mehr.
- Deterministische Secrets/API-Keys, keine Telegram-Verbindungen.
- Redis ist opt-in über `TOKTRACKER_TEST_REDIS_URL` (z.B. CI-Service-Container).

Verwendung am Anfang jedes Testmoduls:

    try:
        from . import _bootstrap  # noqa: F401  (pytest: Paket-Import)
    except ImportError:
        import _bootstrap  # noqa: F401         (unittest discover / direkt)

Voraussetzungen: erreichbarer MariaDB/MySQL-Server. Zugangsdaten kommen aus
`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`; der User braucht
`CREATE DATABASE`/`DROP DATABASE` für `toktracker_test_%`
(siehe `docker/mariadb-init/10-test-grants.sql`).
"""

from __future__ import annotations

import atexit
import os
import sys

import pymysql

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# .env genauso laden wie die App, damit Tests dieselben Zugangsdaten nutzen.
# Wichtig: Werte, die bereits im Prozess gesetzt sind, haben Vorrang.
_ENV_KEYS_AT_IMPORT = set(os.environ)
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"), override=False)
except Exception:  # pragma: no cover - fehlende/unlesbare .env ist okay
    pass

_BOOTSTRAP_FLAG = "TOKTRACKER_TEST_BOOTSTRAPPED"

# Jede Test-Datenbank trägt diesen Präfix. Der Guard weiter unten verhindert,
# dass ein fehlkonfigurierter Lauf versehentlich die echte Datenbank trifft.
TEST_DB_PREFIX = "toktracker_test_"

_CREDENTIAL_HINT = (
    "Tests brauchen eine erreichbare MariaDB/MySQL-Instanz.\n"
    "  • Lokal/Docker: `docker compose up -d db` (Port 127.0.0.1:3306 ist veröffentlicht).\n"
    "  • Im Container: run_tests.sh nutzt MYSQL_HOST=db.\n"
    "  • Der DB-User braucht CREATE/DROP DATABASE für 'toktracker_test_%'\n"
    "    (docker/mariadb-init/10-test-grants.sh).\n"
    "  • Zugangsdaten: MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD."
)


def _connect_with_host(host: str, database: str | None = None, connect_timeout: int = 10):
    return pymysql.connect(
        host=host,
        port=int(os.environ.get("MYSQL_PORT", "3306") or 3306),
        user=os.environ.get("MYSQL_USER", "root").strip() or "root",
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=connect_timeout,
    )


def _connect(database: str | None = None):
    host = os.environ.get("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    return _connect_with_host(host, database)


def _host_reachable(host: str) -> bool:
    try:
        _connect_with_host(host, connect_timeout=3).close()
        return True
    except pymysql.err.OperationalError as exc:
        # 2002/2003 = Verbindung fehlgeschlagen; alles andere (z.B. 1045) heißt:
        # Host antwortet, nur die Zugangsdaten passen nicht.
        code = exc.args[0] if exc.args else 0
        return code not in (2002, 2003)
    except Exception:
        return False


def _resolve_host() -> None:
    """
    `.env` beschreibt die Docker-Interna (`MYSQL_HOST=db`). Läuft pytest auf dem
    Host, ist die DB nur über den veröffentlichten Port 127.0.0.1 erreichbar.
    Explizit exportierte Werte werden nie überschrieben.
    """
    if "MYSQL_HOST" in _ENV_KEYS_AT_IMPORT:
        return
    host = os.environ.get("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host in ("127.0.0.1", "localhost", "::1"):
        return
    if _host_reachable(host):
        return
    if _host_reachable("127.0.0.1"):
        os.environ["MYSQL_HOST"] = "127.0.0.1"



def _execute(sql: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()


def _drop_stale_test_databases(keep: str) -> None:
    """Räumt Test-DBs abgebrochener Läufe auf (best effort, nur verwaiste PIDs)."""
    if os.environ.get("TOKTRACKER_TEST_KEEP_DB") == "1":
        return
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE ?",
                    (f"{TEST_DB_PREFIX}%",),
                )
                names = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return

    for name in names:
        if name == keep:
            continue
        parts = name[len(TEST_DB_PREFIX):].split("_", 1)
        if not parts or not parts[0].isdigit():
            continue
        if _pid_alive(int(parts[0])):
            continue
        try:
            _execute(f"DROP DATABASE IF EXISTS `{name}`")
        except Exception:
            pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False
    return True


def _create_test_database(name: str) -> None:
    try:
        _execute(
            f"CREATE DATABASE IF NOT EXISTS `{name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    except Exception as exc:  # pragma: no cover - Umgebungsfehler
        raise SystemExit(
            f"Test-Datenbank '{name}' konnte nicht angelegt werden: {exc}\n{_CREDENTIAL_HINT}"
        ) from exc


def _drop_test_database(name: str) -> None:
    if os.environ.get("TOKTRACKER_TEST_KEEP_DB") == "1":
        return
    try:
        _execute(f"DROP DATABASE IF EXISTS `{name}`")
    except Exception:
        pass


def _require_test_database_name(name: str) -> None:
    if not name.startswith(TEST_DB_PREFIX):
        raise SystemExit(
            f"Verweigert: MYSQL_DATABASE={name!r} ist keine Test-Datenbank "
            f"(erwartet: Präfix {TEST_DB_PREFIX!r}). Tests dürfen niemals gegen "
            "die Entwicklungs- oder Produktionsdatenbank laufen."
        )


# Idempotent: bei doppeltem Import (z.B. Container-Kopie + Repo-Paket) wird die
# bereits konfigurierte Umgebung wiederverwendet statt eine zweite DB anzulegen.
_ALREADY_BOOTSTRAPPED = os.environ.get(_BOOTSTRAP_FLAG) == "1"

if _ALREADY_BOOTSTRAPPED:
    _DB_NAME = os.environ.get("MYSQL_DATABASE", "")
    _require_test_database_name(_DB_NAME)
else:
    # --- Datenbank: eigene MariaDB je Testlauf -------------------------------
    os.environ.pop("DB_ENGINE", None)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("TIKTOK_DB_PATH", None)
    _resolve_host()

    _DB_NAME = f"{TEST_DB_PREFIX}{os.getpid()}_{os.urandom(3).hex()}"
    _require_test_database_name(_DB_NAME)
    _create_test_database(_DB_NAME)
    _drop_stale_test_databases(_DB_NAME)
    atexit.register(_drop_test_database, _DB_NAME)

if not _ALREADY_BOOTSTRAPPED:
    os.environ["MYSQL_DATABASE"] = _DB_NAME

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
    # Standardmäßig ohne Zugriffssperre testen; tests/test_access_gate.py schaltet
    # sie gezielt ein (config.access_gate wird dort gepatcht).
    os.environ["ACCESS_GATE"] = "off"
    os.environ["ALLOW_API_KEY_QUERY"] = "1"
    os.environ["TRUST_PROXY_HEADERS"] = "1"
    os.environ["SESSION_COOKIE_SECURE"] = "auto"
    os.environ["LOG_LEVEL"] = "WARNING"  # Test-Läufe nicht mit INFO-Logs fluten
    os.environ[_BOOTSTRAP_FLAG] = "1"

TEST_DB_NAME = _DB_NAME
TEST_REDIS_URL = os.environ.get("REDIS_URL", "")

# Schema einmalig anlegen, damit alle Tests ohne Lifespan/API-Bootstrap laufen.
from shared.database import init_db  # noqa: E402

init_db()
