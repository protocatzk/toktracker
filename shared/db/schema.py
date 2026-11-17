"""
TokTracker - Schema-Initialisierung und Migrationen für MariaDB/MySQL.
"""

import logging
import re
import threading
from datetime import datetime

from shared.config import config
from shared.db._base import DEFAULT_SETTINGS, MariaDBConnection, _open_connection, get_db

logger = logging.getLogger("toktracker.schema")

_db_init_lock = threading.Lock()


_db_initialized: bool = False


def _ensure_column(conn: MariaDBConnection, table: str, column: str, col_def: str) -> None:
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


def _ensure_index(conn: MariaDBConnection, table: str, index_name: str, columns_sql: str, unique: bool = False) -> None:
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


def _init_schema() -> None:
    # 1. Datenbank anlegen, falls sie noch nicht existiert
    try:
        bootstrap_conn = _open_connection(include_db=False)
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

    raw_conn = _open_connection(include_db=True)
    conn = MariaDBConnection(raw_conn)
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
            CREATE TABLE IF NOT EXISTS revenue_profiles (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(191) NOT NULL UNIQUE,
                gross_region VARCHAR(16) NOT NULL DEFAULT 'DE',
                creator_region VARCHAR(16) NOT NULL DEFAULT 'DE',
                coin_price_usd DECIMAL(14,8) NOT NULL DEFAULT 0.01050000,
                creator_share_pct DECIMAL(6,4) NOT NULL DEFAULT 0.5000,
                agency_share_pct DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
                payout_fee_pct DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
                tax_pct DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
                coin_price_uncertainty_pct DECIMAL(6,4) NOT NULL DEFAULT 0.1000,
                creator_share_uncertainty_pct DECIMAL(6,4) NOT NULL DEFAULT 0.0500,
                agency_share_max_pct DECIMAL(6,4) NOT NULL DEFAULT 0.1000,
                tax_max_pct DECIMAL(6,4) NOT NULL DEFAULT 0.2000,
                fx_rate DECIMAL(14,8) NOT NULL DEFAULT 0.92000000,
                fx_uncertainty_pct DECIMAL(6,4) NOT NULL DEFAULT 0.0200,
                is_default TINYINT DEFAULT 0,
                valid_from VARCHAR(64) NOT NULL,
                created_at VARCHAR(64) NOT NULL
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
                usd_net DECIMAL(14,4) NOT NULL,
                eur_net DECIMAL(14,4) NOT NULL,
                usd_gross DECIMAL(14,4) NOT NULL,
                eur_gross DECIMAL(14,4) NOT NULL,
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
            CREATE TABLE IF NOT EXISTS telegram_user_permissions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                permission VARCHAR(64) NOT NULL,
                effect VARCHAR(8) NOT NULL DEFAULT 'grant',
                created_by VARCHAR(191) DEFAULT '',
                created_at VARCHAR(64) NOT NULL,
                UNIQUE KEY uq_telegram_user_permission (user_id, permission),
                KEY idx_telegram_user_permissions_user (user_id),
                CONSTRAINT fk_tg_user_permissions_user
                    FOREIGN KEY (user_id) REFERENCES telegram_users(id) ON DELETE CASCADE
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
                usd_net DECIMAL(14,4) DEFAULT 0.0000,
                eur_net DECIMAL(14,4) DEFAULT 0.0000,
                usd_gross DECIMAL(14,4) DEFAULT 0.0000,
                eur_gross DECIMAL(14,4) DEFAULT 0.0000,
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
            CREATE TABLE IF NOT EXISTS streamer_alerts (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                streamer_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                chat_title VARCHAR(255) DEFAULT '',
                created_by_telegram_id BIGINT NULL,
                created_by_username VARCHAR(191) DEFAULT '',
                enabled TINYINT DEFAULT 1,
                last_notified_session_id BIGINT NULL,
                last_notified_at VARCHAR(64),
                created_at VARCHAR(64) NOT NULL,
                UNIQUE KEY uq_streamer_alert (streamer_id, chat_id),
                CONSTRAINT fk_streamer_alerts_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS streamer_groups (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(191) NOT NULL UNIQUE,
                description VARCHAR(512) DEFAULT '',
                color VARCHAR(16) DEFAULT '',
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS streamer_group_members (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                group_id BIGINT NOT NULL,
                streamer_id BIGINT NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                UNIQUE KEY uq_group_streamer (group_id, streamer_id),
                CONSTRAINT fk_group_members_group FOREIGN KEY (group_id) REFERENCES streamer_groups(id) ON DELETE CASCADE,
                CONSTRAINT fk_group_members_streamer FOREIGN KEY (streamer_id) REFERENCES streamers(id) ON DELETE CASCADE
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

        _ensure_column(conn, "tiktok_battles", "battle_mode", "VARCHAR(32) DEFAULT '1v1'")
        _ensure_column(conn, "tiktok_battles", "teammate_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "teammate_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "teammate_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "teammate_avatar_url", "TEXT")
        _ensure_column(conn, "tiktok_battles", "teammate_score", "BIGINT DEFAULT 0")
        _ensure_column(conn, "tiktok_battles", "opponent2_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent2_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent2_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent2_avatar_url", "TEXT")
        _ensure_column(conn, "tiktok_battles", "opponent2_score", "BIGINT DEFAULT 0")
        _ensure_column(conn, "tiktok_battles", "opponent3_user_id", "VARCHAR(128) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent3_username", "VARCHAR(191) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent3_display_name", "VARCHAR(255) DEFAULT ''")
        _ensure_column(conn, "tiktok_battles", "opponent3_avatar_url", "TEXT")
        _ensure_column(conn, "tiktok_battles", "opponent3_score", "BIGINT DEFAULT 0")
        _ensure_column(conn, "tiktok_battles", "streamer_rank", "INT DEFAULT 0")

        _ensure_column(conn, "streamers", "revenue_profile_id", "BIGINT NULL")
        _ensure_column(conn, "gift_events", "revenue_profile_id", "BIGINT NULL")
        _ensure_column(conn, "gift_events", "revenue_model", "VARCHAR(32) DEFAULT 'legacy'")
        _ensure_column(conn, "gift_events", "coin_price_usd", "DECIMAL(14,8) NULL")
        _ensure_column(conn, "gift_events", "creator_share_pct", "DECIMAL(6,4) NULL")
        _ensure_column(conn, "gift_events", "agency_share_pct", "DECIMAL(6,4) NULL")
        _ensure_column(conn, "gift_events", "payout_fee_pct", "DECIMAL(6,4) NULL")
        _ensure_column(conn, "gift_events", "tax_pct", "DECIMAL(6,4) NULL")
        _ensure_column(conn, "gift_events", "fx_rate", "DECIMAL(14,8) NULL")
        _ensure_column(conn, "gift_events", "usd_net_low", "DECIMAL(14,4) NULL")
        _ensure_column(conn, "gift_events", "usd_net_high", "DECIMAL(14,4) NULL")
        _ensure_column(conn, "gift_events", "eur_net_low", "DECIMAL(14,4) NULL")
        _ensure_column(conn, "gift_events", "eur_net_high", "DECIMAL(14,4) NULL")

        _ensure_index(conn, "gift_events", "idx_gift_events_streamer_date", "streamer_id, created_at")
        _ensure_index(conn, "gift_events", "idx_gift_events_session", "session_id")
        _ensure_index(conn, "gift_events", "idx_gift_events_sender", "sender_username")
        _ensure_index(conn, "gift_events", "idx_gift_events_streamer_gift", "streamer_id, gift_name, total_coins, repeat_count")
        _ensure_index(conn, "gift_events", "idx_gift_events_streamer_sender", "streamer_id, sender_username, total_coins")
        _ensure_index(conn, "gift_events", "idx_gift_events_created", "created_at")
        _ensure_index(
            conn,
            "gift_events",
            "idx_gift_events_created_streamer_sender",
            "created_at, streamer_id, sender_username, total_coins",
        )
        _ensure_index(
            conn,
            "gift_events",
            "idx_gift_events_created_streamer_counts",
            "created_at, streamer_id, repeat_count",
        )
        _ensure_index(
            conn,
            "gift_events",
            "idx_gift_events_created_streamer_gift",
            "created_at, streamer_id, gift_name, total_coins, repeat_count",
        )
        _ensure_index(
            conn,
            "gift_events",
            "idx_gift_events_revenue_cover",
            "streamer_id, created_at, total_coins, usd_net, eur_net, usd_gross, eur_gross, "
            "usd_net_low, usd_net_high, eur_net_low, eur_net_high",
        )
        _ensure_index(conn, "stream_sessions", "idx_stream_sessions_streamer", "streamer_id, started_at")
        _ensure_index(conn, "telegram_users", "idx_telegram_users_username", "username")
        _ensure_index(conn, "tiktok_battles", "idx_battles_streamer", "streamer_id, created_at")
        _ensure_index(conn, "tiktok_battles", "idx_battles_battle_id", "battle_id")
        _ensure_index(conn, "tiktok_battles", "idx_battles_result", "result")
        _ensure_index(conn, "tiktok_battles", "idx_battles_opponent", "opponent_username")
        _ensure_index(conn, "streamer_alerts", "idx_streamer_alerts_chat", "chat_id")
        _ensure_index(conn, "streamer_group_members", "idx_group_members_group", "group_id")
        _ensure_index(conn, "streamer_group_members", "idx_group_members_streamer", "streamer_id")
        _ensure_index(conn, "page_views", "idx_page_views_created", "created_at")
        _ensure_index(conn, "page_views", "idx_page_views_path", "path")
        _ensure_index(conn, "page_views", "idx_page_views_visitor", "visitor_hash, created_at")
        _ensure_index(conn, "bot_sessions", "idx_bot_sessions_type", "session_type, created_at")
        _ensure_index(conn, "bot_sessions", "idx_bot_sessions_telegram_id", "telegram_id")
        _ensure_index(conn, "chat_messages", "idx_chat_messages_streamer_created", "streamer_id, created_at")
        _ensure_index(conn, "chat_messages", "idx_chat_messages_created", "created_at")
        _ensure_index(conn, "chat_messages", "idx_chat_messages_username", "username")
        _ensure_index(conn, "chat_messages", "idx_chat_messages_whale", "is_whale, streamer_id")
        _ensure_index(conn, "chat_messages", "idx_chat_messages_session", "session_id")
        _ensure_index(conn, "donor_crm", "idx_donor_crm_username", "username")
        _ensure_index(conn, "donor_crm", "idx_donor_crm_vip", "is_vip")
        _ensure_index(conn, "api_calls", "idx_api_calls_created", "created_at")
        _ensure_index(conn, "api_calls", "idx_api_calls_endpoint", "endpoint")
        _ensure_index(conn, "api_calls", "idx_api_calls_external", "is_external, created_at")
        _ensure_index(conn, "api_calls", "idx_api_calls_status", "status_code")


        # Bestehende Legacy-Zeilen ohne Bandbreite: exakter Wert als Unter-/Obergrenze.
        conn.execute(
            """
            UPDATE gift_events
            SET usd_net_low = COALESCE(usd_net_low, usd_net),
                usd_net_high = COALESCE(usd_net_high, usd_net),
                eur_net_low = COALESCE(eur_net_low, eur_net),
                eur_net_high = COALESCE(eur_net_high, eur_net),
                revenue_model = COALESCE(revenue_model, 'legacy')
            WHERE usd_net_low IS NULL
               OR usd_net_high IS NULL
               OR eur_net_low IS NULL
               OR eur_net_high IS NULL
               OR revenue_model IS NULL
            """
        )
        conn.commit()
    finally:
        raw_conn.close()


def init_db(force: bool = False) -> None:
    global _db_initialized
    with _db_init_lock:
        if _db_initialized and not force:
            return
        _init_schema()

        with get_db() as conn:
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT IGNORE INTO settings (`key`, `value`) VALUES (?, ?)", (k, v)
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

        # Default-Revenue-Profile anlegen und Streamer ohne Profil zuordnen.
        # Mehrere Container können init_db() parallel ausführen; MySQL kann
        # dabei mit "Record has changed since last read" (1020) antworten.
        # Das ist unkritisch, weil ein anderer Prozess die Zuordnung abschließt.
        from shared.db.revenue import ensure_revenue_profiles

        try:
            ensure_revenue_profiles()
        except Exception as exc:
            logger.warning("Revenue-Profile konnten nicht vollständig initialisiert werden: %s", exc)
        _db_initialized = True
