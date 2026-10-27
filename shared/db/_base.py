"""
TokTracker - Verbindungs-Handling: DBRow, MySQL-Wrapper, Connection-Pool, get_db().
"""

import queue
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Generator, List, Optional, Sequence

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False

from shared.config import config

DB_PATH = config.db_path


DEFAULT_SETTINGS: Dict[str, str] = {
    "usd_per_diamond": "0.005",        # Netto-Auszahlung an Streamer pro Coin/Diamond in USD
    "gross_usd_per_coin": "0.0106",    # Brutto-Kaufpreis für Zuschauer pro Coin in USD
    "usd_to_eur_rate": "0.92",         # Wechselkurs USD -> EUR
    "currency_primary": "EUR",         # Primäre Anzeige-Währung (EUR oder USD)
    "poll_interval_seconds": "45",     # Intervall für Auto-Live-Check wenn Streamer offline ist
    "api_key": "",                     # Optionaler API-Key für externe Bot-Abfragen
    "telegram_access_mode": config.telegram_access_mode if config.telegram_access_mode in ("whitelist", "public") else "whitelist",
    "public_banner_enabled": "1",      # 1 = Aktiv, 0 = Deaktiviert
    "public_banner_title": "Exklusive Whitelist-Features & Chat-Intelligence",
    "public_banner_text": "Schalte erweiterte Analysen wie Chat-Intelligence, Streamer-Vergleiche und das Spender-Radar frei. Kontaktiere unseren Telegram-Bot für eine Freischaltung!",
    "public_banner_style": "highlight", # highlight | info | success | warning
    "public_banner_btn_text": "Whitelist anfragen ↗",
    "public_banner_btn_url": "",       # Leer = autom. Telegram-Bot Link
    "public_show_donors": "0",         # 0 = Spender-Namen auf öffentlichen Flächen maskieren
}


class DBRow(dict):
    """
    Kompatibilitäts-Zeilenobjekt für MySQL/MariaDB, das sich exakt wie `sqlite3.Row` verhält:
    - Unterstützt Dictionary-Zugriff (`row["username"]`, `dict(row)`, `row.get(...)`)
    - Unterstützt numerischen Index-Zugriff (`row[0]` z.B. bei `SELECT COUNT(*) ... fetchone()[0]`)
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        # MySQL/MariaDB liefert DECIMAL-Spalten als Decimal. Für die restliche
        # Anwendung (und für JSON-Ausgaben) wird zentral auf float normalisiert,
        # damit SQLite und MySQL identische Typen liefern.
        normalized = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in data.items()
        }
        super().__init__(normalized)
        self._values = list(normalized.values())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class MySQLCursorWrapper:
    """Wrapper um den PyMySQL DictCursor mit `sqlite3.Cursor`-kompatibler Schnittstelle."""

    def __init__(self, raw_cursor: Any) -> None:
        self._cur = raw_cursor

    @property
    def lastrowid(self) -> int:
        return int(self._cur.lastrowid or 0)

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount or 0)

    def fetchone(self) -> Optional[DBRow]:
        row = self._cur.fetchone()
        return DBRow(row) if row is not None else None

    def fetchall(self) -> List[DBRow]:
        rows = self._cur.fetchall()
        return [DBRow(r) for r in rows] if rows else []


class MySQLConnectionWrapper:
    """
    Übersetzt die SQLite-Queries aus `database.py` automatisch für MySQL / MariaDB:
    - `?` -> `%s`
    - `INSERT OR IGNORE INTO` -> `INSERT IGNORE INTO`
    - `INSERT OR REPLACE INTO` -> `REPLACE INTO`
    - `MAX(a, b)` (2 Argumente) -> `GREATEST(a, b)`
    """

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn

    @staticmethod
    def _translate_sql(sql: str) -> str:
        out = sql.replace("?", "%s")
        out = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT IGNORE INTO", out, flags=re.IGNORECASE)
        out = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "REPLACE INTO", out, flags=re.IGNORECASE)
        out = re.sub(r"\bMAX\s*\(\s*last_fan_tickets\s*,\s*%s\s*\)", "GREATEST(last_fan_tickets, %s)", out, flags=re.IGNORECASE)
        return out

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> MySQLCursorWrapper:
        translated = self._translate_sql(sql)
        cur = self._conn.cursor()
        cur.execute(translated, tuple(params) if params is not None else None)
        return MySQLCursorWrapper(cur)

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> MySQLCursorWrapper:
        translated = self._translate_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(translated, [tuple(p) for p in seq_of_params])
        return MySQLCursorWrapper(cur)


    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        # Verbindung wird vom MySQLConnectionPool verwaltet
        pass


class MySQLConnectionPool:
    """
    Thread-sicherer Connection-Pool für MySQL/MariaDB.
    Verhindert das ständige Neuaufbauen von TCP-Verbindungen (bis zu 8 Verb./Sekunde)
    und senkt CPU-Last von MariaDB und Python drastisch.
    """

    def __init__(self, max_size: int = 25, timeout: float = 15.0):
        self._pool: queue.Queue[Any] = queue.Queue(maxsize=max_size)
        self._max_size = max_size
        self._timeout = timeout
        self._created = 0
        self._lock = threading.Lock()

    def get_connection(self) -> Any:
        while True:
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.ping(reconnect=True)
                    return conn
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    with self._lock:
                        self._created = max(0, self._created - 1)
            except queue.Empty:
                break

        with self._lock:
            if self._created < self._max_size:
                self._created += 1
                can_create = True
            else:
                can_create = False

        if can_create:
            try:
                return _open_mysql_connection(include_db=True)
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise

        conn = self._pool.get(timeout=self._timeout)
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created = max(0, self._created - 1)
            return _open_mysql_connection(include_db=True)

    def release_connection(self, conn: Any) -> None:
        if conn is None:
            return
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created = max(0, self._created - 1)


_mysql_pool: Optional[MySQLConnectionPool] = None


_mysql_pool_lock = threading.Lock()


def get_mysql_pool() -> MySQLConnectionPool:
    global _mysql_pool
    if _mysql_pool is None:
        with _mysql_pool_lock:
            if _mysql_pool is None:
                _mysql_pool = MySQLConnectionPool(max_size=25, timeout=15.0)
    return _mysql_pool


def _open_mysql_connection(include_db: bool = True) -> Any:
    if not PYMYSQL_AVAILABLE:
        raise RuntimeError(
            "Für DB_ENGINE=mysql wird das Paket 'pymysql' benötigt (pip install pymysql)."
        )
    conn = pymysql.connect(
        host=config.mysql_host,
        port=config.mysql_port,
        user=config.mysql_user,
        password=config.mysql_password,
        database=config.mysql_database if include_db else None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
    )
    with conn.cursor() as cur:
        cur.execute("SET SESSION sql_mode = (SELECT REPLACE(@@sql_mode, 'ONLY_FULL_GROUP_BY', ''))")
    return conn


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """
    Universeller Datenbank-Context-Manager für `toktracker`:
    - Standard (`DB_ENGINE=sqlite`): Lokale SQLite-Datenbank im schnellen WAL-Modus.
    - Externer SQL-Server (`DB_ENGINE=mysql`): MySQL / MariaDB über Thread-sicheren Connection-Pool.
    """
    if config.is_mysql:
        pool = get_mysql_pool()
        raw_conn = pool.get_connection()
        wrapper = MySQLConnectionWrapper(raw_conn)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            pool.release_connection(raw_conn)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _get_period_cutoff(period: str) -> Optional[str]:
    now = datetime.now()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    if period == "24h":
        return (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    if period == "7d":
        return (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    if period == "30d":
        return (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    return None
