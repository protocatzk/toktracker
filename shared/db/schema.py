"""
TokTracker - Schema-Initialisierung und Migrationen für SQLite und MySQL/MariaDB.
"""

import re
import sqlite3
import threading
from datetime import datetime

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - pymysql ist in Produktion installiert
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False

from shared.config import config
from shared.db._base import DEFAULT_SETTINGS, MySQLConnectionWrapper, _open_mysql_connection, get_db

_db_init_lock = threading.Lock()


_db_initialized: bool = False


def _ensure_column_sqlite(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def _ensure_column_mysql(conn: MySQLConnectionWrapper, table: str, column: str, col_def: str) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?
        """,
        (config.mysql_database, table, column),
    ).fetchone()
    if not row or int(row[0]) == 0:
        conn.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_def}")


def _ensure_index_mysql(conn: MySQLConnectionWrapper, table: str, index_name: str, columns_sql: str, unique: bool = False) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND INDEX_NAME = ?
        """,
        (config.mysql_database, table, index_name),
    ).fetchone()
    if not row or int(row[0]) == 0:
        uniq_kw = "UNIQUE " if unique else ""
        conn.execute(f"CREATE {uniq_kw}INDEX {index_name} ON {table}({columns_sql})")


def _init_mysql_schema() -> None:
    # 1. Datenbank anlegen, falls sie noch nicht existiert
    try:
        bootstrap_conn = _open_mysql_connection(include_db=False)
        try:
            with bootstrap_conn.cursor() as cur:
                db_name = re.sub(r"[^a-zA-Z0-9_]", "", config.mysql_database) or "toktracker"
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            bootstrap_conn.commit()
        finally:
            bootstrap_conn.close()
    except Exception:
        # Falls der MySQL-User keine CREATE DATABASE Rechte hat und die DB bereits existiert, normal fortfahren
        pass

    raw_conn = _open_mysql_connection(include_db=True)
    conn = MySQLConnectionWrapper(raw_conn)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                `key` VARCHAR(128) PRIMARY KEY,
                `value` TEXT NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS streamers (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(191) NOT NULL UNIQUE,
                display_name VARCHAR(255),
                avatar_url TEXT,
                room_id VARCHAR(128),
                follower_count BIGINT DEFAULT 0,
                is_live TINYINT DEFAULT 0,
                is_tracking TINYINT DEFAULT 0,
                auto_monitor TINYINT DEFAULT 0,
                current_viewers INT DEFAULT 0,
                last_error TEXT,
                created_at VARCHAR(64) NOT NULL,
                last_seen_at VARCHAR(64)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stream_sessions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                streamer_id BIGINT NOT NULL,
                room_id VARCHAR(128),
                title VARCHAR(512) DEFAULT '',
                started_at VARCHAR(64) NOT NULL,
                ended_at VARCHAR(64),
                peak_viewers INT DEFAULT 0,
                last_fan_tickets BIGINT DEFAULT 0,
                status VARCHAR(32) DEFAULT 'active',
                CONSTRAINT fk_sessions_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gift_events (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                streamer_id BIGINT NOT NULL,
                session_id BIGINT NULL,
                event_uid VARCHAR(191) UNIQUE,
                sender_user_id VARCHAR(128) DEFAULT '',
                sender_username VARCHAR(191) NOT NULL,
                sender_nickname VARCHAR(255),
                is_super_fan TINYINT DEFAULT 0,
                gift_id INT DEFAULT 0,
                gift_name VARCHAR(255) NOT NULL,
                gift_icon_url TEXT,
                diamond_count INT NOT NULL,
                repeat_count INT NOT NULL DEFAULT 1,
                combo_count INT DEFAULT 1,
                group_id VARCHAR(128) DEFAULT '',
                room_fan_tickets BIGINT DEFAULT 0,
                total_coins BIGINT NOT NULL,
                usd_net DOUBLE NOT NULL,
                eur_net DOUBLE NOT NULL,
                usd_gross DOUBLE NOT NULL,
                eur_gross DOUBLE NOT NULL,
                source VARCHAR(64) DEFAULT 'tiktoklive',
                created_at VARCHAR(64) NOT NULL,
                CONSTRAINT fk_gifts_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                CONSTRAINT fk_gifts_session FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_users (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username VARCHAR(191),
                first_name VARCHAR(255) DEFAULT '',
                role VARCHAR(32) DEFAULT 'user',
                is_allowed TINYINT DEFAULT 0,
                note VARCHAR(512) DEFAULT '',
                created_at VARCHAR(64) NOT NULL,
                last_seen_at VARCHAR(64)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_battles (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                streamer_id BIGINT NOT NULL,
                session_id BIGINT NULL,
                battle_id VARCHAR(128) NOT NULL,
                opponent_user_id VARCHAR(128) DEFAULT '',
                opponent_username VARCHAR(191) DEFAULT '',
                opponent_display_name VARCHAR(255) DEFAULT '',
                opponent_avatar_url TEXT,
                started_at VARCHAR(64) NOT NULL,
                ended_at VARCHAR(64),
                duration_seconds INT DEFAULT 300,
                streamer_score INT DEFAULT 0,
                opponent_score INT DEFAULT 0,
                result VARCHAR(32) DEFAULT 'ONGOING',
                streamer_mvp_name VARCHAR(255) DEFAULT '',
                streamer_mvp_score INT DEFAULT 0,
                streamer_mvp_avatar TEXT,
                opponent_mvp_name VARCHAR(255) DEFAULT '',
                opponent_mvp_score INT DEFAULT 0,
                opponent_mvp_avatar TEXT,
                coins_earned BIGINT DEFAULT 0,
                usd_net DOUBLE DEFAULT 0.0,
                eur_net DOUBLE DEFAULT 0.0,
                usd_gross DOUBLE DEFAULT 0.0,
                eur_gross DOUBLE DEFAULT 0.0,
                status VARCHAR(32) DEFAULT 'active',
                raw_data_json MEDIUMTEXT,
                created_at VARCHAR(64) NOT NULL,
                CONSTRAINT fk_battles_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                CONSTRAINT fk_battles_session FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS page_views (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                path VARCHAR(255) NOT NULL,
                visitor_hash VARCHAR(64) NOT NULL,
                user_agent VARCHAR(512) DEFAULT '',
                device_type VARCHAR(32) DEFAULT 'desktop',
                referrer VARCHAR(512) DEFAULT '',
                status_code INT DEFAULT 200,
                response_time_ms DOUBLE DEFAULT 0.0,
                created_at VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_sessions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                session_type VARCHAR(32) NOT NULL,
                telegram_id BIGINT NULL,
                username VARCHAR(191) DEFAULT '',
                first_name VARCHAR(255) DEFAULT '',
                client_ip_hash VARCHAR(64) DEFAULT '',
                status VARCHAR(32) DEFAULT 'active',
                details_json TEXT,
                created_at VARCHAR(64) NOT NULL,
                last_active_at VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                streamer_id BIGINT NOT NULL,
                session_id BIGINT NULL,
                user_id VARCHAR(128) DEFAULT '',
                username VARCHAR(191) NOT NULL,
                nickname VARCHAR(255) DEFAULT '',
                avatar_url TEXT,
                comment TEXT NOT NULL,
                is_whale TINYINT DEFAULT 0,
                whale_tier VARCHAR(32) DEFAULT '',
                created_at VARCHAR(64) NOT NULL,
                CONSTRAINT fk_chat_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                CONSTRAINT fk_chat_session FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS donor_crm (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(191) NOT NULL UNIQUE,
                is_vip TINYINT DEFAULT 0,
                tags TEXT,
                notes TEXT,
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_calls (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                endpoint VARCHAR(191) NOT NULL,
                method VARCHAR(16) NOT NULL DEFAULT 'GET',
                status_code INT NOT NULL DEFAULT 200,
                response_time_ms FLOAT NOT NULL DEFAULT 0.0,
                client_ip VARCHAR(64) DEFAULT '',
                ip_hash VARCHAR(64) DEFAULT '',
                user_agent VARCHAR(500) DEFAULT '',
                auth_type VARCHAR(32) DEFAULT 'none',
                api_key_name VARCHAR(64) DEFAULT '',
                is_external TINYINT NOT NULL DEFAULT 1,
                query_params VARCHAR(500) DEFAULT '',
                created_at VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        _ensure_index_mysql(conn, "gift_events", "idx_gift_events_streamer_date", "streamer_id, created_at")
        _ensure_index_mysql(conn, "gift_events", "idx_gift_events_session", "session_id")
        _ensure_index_mysql(conn, "gift_events", "idx_gift_events_sender", "sender_username")
        _ensure_index_mysql(conn, "stream_sessions", "idx_stream_sessions_streamer", "streamer_id, started_at")
        _ensure_index_mysql(conn, "telegram_users", "idx_telegram_users_username", "username")
        _ensure_index_mysql(conn, "tiktok_battles", "idx_battles_streamer", "streamer_id, created_at")
        _ensure_index_mysql(conn, "tiktok_battles", "idx_battles_battle_id", "battle_id")
        _ensure_index_mysql(conn, "tiktok_battles", "idx_battles_result", "result")
        _ensure_index_mysql(conn, "tiktok_battles", "idx_battles_opponent", "opponent_username")
        _ensure_index_mysql(conn, "page_views", "idx_page_views_created", "created_at")
        _ensure_index_mysql(conn, "page_views", "idx_page_views_path", "path")
        _ensure_index_mysql(conn, "page_views", "idx_page_views_visitor", "visitor_hash, created_at")
        _ensure_index_mysql(conn, "bot_sessions", "idx_bot_sessions_type", "session_type, created_at")
        _ensure_index_mysql(conn, "bot_sessions", "idx_bot_sessions_telegram_id", "telegram_id")
        _ensure_index_mysql(conn, "chat_messages", "idx_chat_messages_streamer_created", "streamer_id, created_at")
        _ensure_index_mysql(conn, "chat_messages", "idx_chat_messages_created", "created_at")
        _ensure_index_mysql(conn, "chat_messages", "idx_chat_messages_username", "username")
        _ensure_index_mysql(conn, "chat_messages", "idx_chat_messages_whale", "is_whale, streamer_id")
        _ensure_index_mysql(conn, "chat_messages", "idx_chat_messages_session", "session_id")
        _ensure_index_mysql(conn, "donor_crm", "idx_donor_crm_username", "username")
        _ensure_index_mysql(conn, "donor_crm", "idx_donor_crm_vip", "is_vip")
        _ensure_index_mysql(conn, "api_calls", "idx_api_calls_created", "created_at")
        _ensure_index_mysql(conn, "api_calls", "idx_api_calls_endpoint", "endpoint")
        _ensure_index_mysql(conn, "api_calls", "idx_api_calls_external", "is_external, created_at")
        _ensure_index_mysql(conn, "api_calls", "idx_api_calls_status", "status_code")

        _ensure_column_mysql(conn, "tiktok_battles", "battle_mode", "VARCHAR(32) DEFAULT '1v1'")
        _ensure_column_mysql(conn, "tiktok_battles", "teammate_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "teammate_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "teammate_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "teammate_avatar_url", "TEXT")
        _ensure_column_mysql(conn, "tiktok_battles", "teammate_score", "BIGINT DEFAULT 0")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent2_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent2_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent2_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent2_avatar_url", "TEXT")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent2_score", "BIGINT DEFAULT 0")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent3_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent3_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent3_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent3_avatar_url", "TEXT")
        _ensure_column_mysql(conn, "tiktok_battles", "opponent3_score", "BIGINT DEFAULT 0")
        _ensure_column_mysql(conn, "tiktok_battles", "streamer_rank", "INT DEFAULT 0")
        conn.commit()
    finally:
        raw_conn.close()


def _init_sqlite_schema() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                `key` TEXT PRIMARY KEY,
                `value` TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS streamers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT,
                avatar_url TEXT,
                room_id TEXT,
                follower_count INTEGER DEFAULT 0,
                is_live INTEGER DEFAULT 0,
                is_tracking INTEGER DEFAULT 0,
                auto_monitor INTEGER DEFAULT 0,
                current_viewers INTEGER DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS stream_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                streamer_id INTEGER NOT NULL,
                room_id TEXT,
                title TEXT DEFAULT '',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                peak_viewers INTEGER DEFAULT 0,
                last_fan_tickets INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS gift_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                streamer_id INTEGER NOT NULL,
                session_id INTEGER,
                event_uid TEXT UNIQUE,
                sender_user_id TEXT DEFAULT '',
                sender_username TEXT NOT NULL,
                sender_nickname TEXT,
                is_super_fan INTEGER DEFAULT 0,
                gift_id INTEGER DEFAULT 0,
                gift_name TEXT NOT NULL,
                gift_icon_url TEXT,
                diamond_count INTEGER NOT NULL,
                repeat_count INTEGER NOT NULL DEFAULT 1,
                combo_count INTEGER DEFAULT 1,
                group_id TEXT DEFAULT '',
                room_fan_tickets INTEGER DEFAULT 0,
                total_coins INTEGER NOT NULL,
                usd_net REAL NOT NULL,
                eur_net REAL NOT NULL,
                usd_gross REAL NOT NULL,
                eur_gross REAL NOT NULL,
                source TEXT DEFAULT 'tiktoklive',
                created_at TEXT NOT NULL,
                FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS telegram_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT COLLATE NOCASE,
                first_name TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                is_allowed INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS tiktok_battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                streamer_id INTEGER NOT NULL,
                session_id INTEGER,
                battle_id TEXT NOT NULL,
                opponent_user_id TEXT DEFAULT '',
                opponent_username TEXT DEFAULT '',
                opponent_display_name TEXT DEFAULT '',
                opponent_avatar_url TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds INTEGER DEFAULT 300,
                streamer_score INTEGER DEFAULT 0,
                opponent_score INTEGER DEFAULT 0,
                result TEXT DEFAULT 'ONGOING',
                streamer_mvp_name TEXT DEFAULT '',
                streamer_mvp_score INTEGER DEFAULT 0,
                streamer_mvp_avatar TEXT,
                opponent_mvp_name TEXT DEFAULT '',
                opponent_mvp_score INTEGER DEFAULT 0,
                opponent_mvp_avatar TEXT,
                coins_earned INTEGER DEFAULT 0,
                usd_net REAL DEFAULT 0.0,
                eur_net REAL DEFAULT 0.0,
                usd_gross REAL DEFAULT 0.0,
                eur_gross REAL DEFAULT 0.0,
                status TEXT DEFAULT 'active',
                raw_data_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                visitor_hash TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                device_type TEXT DEFAULT 'desktop',
                referrer TEXT DEFAULT '',
                status_code INTEGER DEFAULT 200,
                response_time_ms REAL DEFAULT 0.0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bot_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_type TEXT NOT NULL,
                telegram_id INTEGER NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                client_ip_hash TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                details_json TEXT,
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                streamer_id INTEGER NOT NULL,
                session_id INTEGER,
                user_id TEXT DEFAULT '',
                username TEXT NOT NULL COLLATE NOCASE,
                nickname TEXT DEFAULT '',
                avatar_url TEXT,
                comment TEXT NOT NULL,
                is_whale INTEGER DEFAULT 0,
                whale_tier TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES stream_sessions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS donor_crm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                is_vip INTEGER DEFAULT 0,
                tags TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'GET',
                status_code INTEGER NOT NULL DEFAULT 200,
                response_time_ms REAL NOT NULL DEFAULT 0.0,
                client_ip TEXT DEFAULT '',
                ip_hash TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                auth_type TEXT DEFAULT 'none',
                api_key_name TEXT DEFAULT '',
                is_external INTEGER NOT NULL DEFAULT 1,
                query_params TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )

        _ensure_column_sqlite(conn, "streamers", "auto_monitor", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "streamers", "current_viewers", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "streamers", "last_error", "TEXT DEFAULT ''")

        _ensure_column_sqlite(conn, "gift_events", "session_id", "INTEGER")
        _ensure_column_sqlite(conn, "gift_events", "event_uid", "TEXT")
        _ensure_column_sqlite(conn, "gift_events", "sender_user_id", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "gift_events", "is_super_fan", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "gift_events", "combo_count", "INTEGER DEFAULT 1")
        _ensure_column_sqlite(conn, "gift_events", "group_id", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "gift_events", "room_fan_tickets", "INTEGER DEFAULT 0")

        _ensure_column_sqlite(conn, "tiktok_battles", "battle_mode", "TEXT DEFAULT '1v1'")
        _ensure_column_sqlite(conn, "tiktok_battles", "teammate_user_id", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "teammate_username", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "teammate_display_name", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "teammate_avatar_url", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "teammate_score", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent2_user_id", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent2_username", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent2_display_name", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent2_avatar_url", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent2_score", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent3_user_id", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent3_username", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent3_display_name", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent3_avatar_url", "TEXT DEFAULT ''")
        _ensure_column_sqlite(conn, "tiktok_battles", "opponent3_score", "INTEGER DEFAULT 0")
        _ensure_column_sqlite(conn, "tiktok_battles", "streamer_rank", "INTEGER DEFAULT 0")

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_gift_events_streamer_date
                ON gift_events(streamer_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_gift_events_session
                ON gift_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_gift_events_sender
                ON gift_events(sender_username);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_gift_events_uid
                ON gift_events(event_uid) WHERE event_uid IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_stream_sessions_streamer
                ON stream_sessions(streamer_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_telegram_users_username
                ON telegram_users(username);
            CREATE INDEX IF NOT EXISTS idx_battles_streamer
                ON tiktok_battles(streamer_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_battles_battle_id
                ON tiktok_battles(battle_id);
            CREATE INDEX IF NOT EXISTS idx_battles_result
                ON tiktok_battles(result);
            CREATE INDEX IF NOT EXISTS idx_battles_opponent
                ON tiktok_battles(opponent_username);
            CREATE INDEX IF NOT EXISTS idx_page_views_created
                ON page_views(created_at);
            CREATE INDEX IF NOT EXISTS idx_page_views_path
                ON page_views(path);
            CREATE INDEX IF NOT EXISTS idx_page_views_visitor
                ON page_views(visitor_hash, created_at);
            CREATE INDEX IF NOT EXISTS idx_bot_sessions_type
                ON bot_sessions(session_type, created_at);
            CREATE INDEX IF NOT EXISTS idx_bot_sessions_telegram_id
                ON bot_sessions(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_streamer_created
                ON chat_messages(streamer_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_created
                ON chat_messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_username
                ON chat_messages(username);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_whale
                ON chat_messages(is_whale, streamer_id);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON chat_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_donor_crm_username
                ON donor_crm(username);
            CREATE INDEX IF NOT EXISTS idx_donor_crm_vip
                ON donor_crm(is_vip);
            CREATE INDEX IF NOT EXISTS idx_api_calls_created
                ON api_calls(created_at);
            CREATE INDEX IF NOT EXISTS idx_api_calls_endpoint
                ON api_calls(endpoint);
            CREATE INDEX IF NOT EXISTS idx_api_calls_external
                ON api_calls(is_external, created_at);
            CREATE INDEX IF NOT EXISTS idx_api_calls_status
                ON api_calls(status_code);
            """
        )


def init_db(force: bool = False) -> None:
    global _db_initialized
    with _db_init_lock:
        if _db_initialized and not force:
            return
        if config.is_mysql:
            _init_mysql_schema()
        else:
            _init_sqlite_schema()

        with get_db() as conn:
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (`key`, `value`) VALUES (?, ?)", (k, v)
                )

            # Initiale Admins/Whitelist-User aus der .env synchronisieren
            now = datetime.now().isoformat(timespec="seconds")
            for tg_id in config.env_allowed_telegram_ids:
                existing = conn.execute(
                    "SELECT id FROM telegram_users WHERE telegram_id = ?", (tg_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE telegram_users SET is_allowed = 1, role = 'admin' WHERE id = ?",
                        (existing["id"],),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO telegram_users (telegram_id, username, first_name, role, is_allowed, note, created_at, last_seen_at)
                        VALUES (?, '', 'ENV Admin', 'admin', 1, 'Aus .env geladen', ?, ?)
                        """,
                        (tg_id, now, now),
                    )

            for tg_uname in config.env_allowed_telegram_usernames:
                existing = conn.execute(
                    "SELECT id FROM telegram_users WHERE LOWER(username) = LOWER(?)",
                    (tg_uname,),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE telegram_users SET is_allowed = 1, role = 'admin' WHERE id = ?",
                        (existing["id"],),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO telegram_users (telegram_id, username, first_name, role, is_allowed, note, created_at, last_seen_at)
                        VALUES (NULL, ?, 'ENV Admin', 'admin', 1, 'Aus .env geladen', ?, ?)
                        """,
                        (tg_uname.lower(), now, now),
                    )
        _db_initialized = True
