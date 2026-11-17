# Migrationsplan: MariaDB/SQLite → PostgreSQL

Status: Plan (kein Code geändert). Ziel: PostgreSQL als **einzige** Engine für Dev,
Tests und Produktion. Hauptmotivation: JSONB für OpenAPI-kompatible Endpoints
(`raw_data_json`, `details_json`, Chat-Intelligence, Web-Analytics) und Wegfall
des handgebauten Dialekt-Übersetzers.

---

## 1. Status Quo (Belege)

| Baustein | Ist-Zustand | Datei |
| :--- | :--- | :--- |
| Dialekt-Layer | `MySQLConnectionWrapper._translate_sql()`: `?`→`%s`, `INSERT OR IGNORE`→`INSERT IGNORE`, `INSERT OR REPLACE`→`REPLACE INTO`, `MAX(last_fan_tickets, %s)`→`GREATEST(...)` | `shared/db/_base.py:106-122` |
| Zeilen-Abstraktion | `DBRow` (dict + Index-Zugriff, Decimal→float-Normalisierung), `MySQLCursorWrapper` (sqlite3-kompatible API) | `shared/db/_base.py:49-93` |
| Connection-Pool | Thread-sicherer `MySQLConnectionPool` (25 Verb., ping/reconnect) | `shared/db/_base.py:139-190` |
| Schema | **Zwei parallele CREATE-Table-Blöcke** (SQLite ab Zeile ~86, MySQL ab ~489), 16 Tabellen je Dialekt, handgeführte Migrationen via `_ensure_column_*`/`_ensure_index_mysql` gegen `INFORMATION_SCHEMA` | `shared/db/schema.py` |
| Query-Module | 16 Module, 8.197 Zeilen, schreiben rohes SQL im "SQLite-Dialekt" (`?`-Platzhalter) | `shared/db/*.py` |
| Config | `DB_ENGINE` (sqlite/mysql), `DATABASE_URL` (mysql://-Parsing), `MYSQL_*`-Variablen | `shared/config.py:95-110, 201-213` |
| JSON-Persistenz | `raw_data_json MEDIUMTEXT` (battles, api_calls), `details_json TEXT` (page_views, chat) — JSON als String, kein Query-Zugriff auf Felder | `shared/db/schema.py:242, 317, 625, 680` |
| Migrations-Skripte | `migrate_sqlite_to_mysql.py`, `migrate_money_to_decimal.py`, `migrate_revenue_model.py` | Repo-Root |
| Tests | 41 Testdateien, laufen gegen temp. SQLite (`tests/_bootstrap.py`), Redis opt-in | `run_tests.sh` |
| Deployment | `mariadb:11`-Service + `mariadb_data`-Volume, 4× `DB_ENGINE=mysql` in compose | `docker-compose.yml:70,116,150,186,208,218,295` |
| CI | GitHub Actions (`ci.yml`), Tests im App-Container | `.github/workflows/ci.yml` |

MySQL-spezifische Konstrukte im Codebestand: ~100 Stellen (`INSERT IGNORE`,
`ENGINE=InnoDB`, `utf8mb4`, `AUTO_INCREMENT`, `UNIX_TIMESTAMP`, `NOW()`,
`ON DUPLICATE`, `REPLACE INTO`, `INFORMATION_SCHEMA`-Abfragen).

---

## 2. Zielbild

- **Ein** Dialekt: Postgres. Der `MySQLConnectionWrapper`-Übersetzer und der
  SQLite-Pfad in `schema.py` entfallen ersatzlos.
- Driver: `psycopg[binary]` (psycopg3), Thread-safe, Server-Side-Prepared-Params.
- JSON-Spalten werden `JSONB` und damit feldweise abfragbar (`->`, `->>`, `@>`,
  GIN-Indizes) — das ist der eigentliche Gewinn für OpenAPI-Endpoint-Workloads.
- Dev = Prod: identischer Dialekt, identische Typsemantik (kein "bei SQLite läuft
  es, bei MariaDB nicht" mehr). Dev-DB läuft im compose-Override oder per Podman.

### 2.1 Dialekt-Übersetzungstabelle (Referenz für Umsetzung)

| SQLite/MySQL (Ist) | PostgreSQL (Ziel) |
| :--- | :--- |
| `?` / `%s` Platzhalter | `%s` (psycopg3) |
| `INSERT OR IGNORE INTO` / `INSERT IGNORE INTO` | `INSERT ... ON CONFLICT DO NOTHING` |
| `INSERT OR REPLACE INTO` / `REPLACE INTO` | `INSERT ... ON CONFLICT <key> DO UPDATE` (je Statement prüfen!) |
| `MAX(a, b)` (2-Arg-Semantik) | `GREATEST(a, b)` |
| `AUTO_INCREMENT` | `GENERATED ALWAYS AS IDENTITY` / `BIGSERIAL` |
| `UNIX_TIMESTAMP()` / `FROM_UNIXTIME()` | `EXTRACT(EPOCH FROM ...)` / `to_timestamp(...)` |
| `NOW()` | `now()` |
| `MEDIUMTEXT`/`TEXT` (JSON) | `JSONB` |
| `INFORMATION_SCHEMA.COLUMNS/STATISTICS` (Hand-Migration) | `information_schema.columns` / `pg_indexes` — oder `CREATE INDEX IF NOT EXISTS` |
| `lastrowid` | `INSERT ... RETURNING id` |
| `PRAGMA table_info` | `information_schema.columns` |
| `utf8mb4 COLLATE ...` | entfällt (UTF-8 Default, `ICU`-Collations optional) |
| `ENGINE=InnoDB` | entfällt |
| Backtick-Quoting `` ` `` | Double-Quote `"` oder unquoted |

**Kritischer Punkt:** `REPLACE INTO` hat DELETE+INSERT-Semantik (löscht Fremd-
Verweise, setzt AUTO_INCREMENT hoch). `ON CONFLICT DO UPDATE` verhält sich
anders. Jede der betroffenen Stellen muss einzeln geprüft werden, nicht
mechanisch ersetzt.

---

## 3. Phasenplan

### Phase 0 — Vorbereitung (0,5 Tag)

- [ ] `psycopg[binary]` in `requirements.txt` pinnen, `PyMySQL` **nicht** entfernen
      (wird erst in Phase 6 raus, `migrate_mysql_to_postgres.py` braucht es).
- [ ] `docs/postgres-migration.md` (dieses Dokument) reviewen.
- [ ] Postgres 17-Testinstanz lokal hochziehen (docker compose override),
      `mariadb:11`-Dump als Referenz besorgen.

### Phase 1 — Config & Verbindungsschicht (1 Tag)

- [ ] `shared/config.py`: `DB_ENGINE` → `postgres` (`DATABASE_URL=postgresql://...`
      Parsing analog zum jetzigen mysql-Block in `__post_init__`, Zeilen 201-213);
      `POSTGRES_HOST/PORT/USER/PASSWORD/DATABASE` bzw. nur `DATABASE_URL`.
      `is_mysql` → `is_postgres`; `db_path` nur noch als Legacy-Fallback lesbar.
- [ ] `shared/db/_base.py`:
  - `PostgresConnectionWrapper` (psycopg3, `%s`-Params, `DBRow` bleibt,
    Decimal-Normalisierung bleibt).
  - `PostgresConnectionPool` (psycopg `ConnectionPool` ersetzt den Hand-Pool;
    `queue.Queue`-Konstruk entfällt).
  - `get_db()`/`init_db()` auf Postgres umstellen; Healthcheck
    (`shared/healthcheck.py`) anpassen.
- [ ] `DB_ENGINE=postgres` in allen Services (compose, Dockerfile-ENV,
      `run_tests.sh`).

### Phase 2 — Schema (1,5 Tage)

- [ ] `schema.py`: **ein** CREATE-Block. Pro Tabelle:
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
  - `INTEGER` (Unix-Timestamps) prüfen: beibehalten (einfacher) **oder**
    `TIMESTAMPTZ` (sauberer, aber berührt jede Zeit-Query — Empfehlung:
    vorerst Unix-Integer beibehalten, separater Follow-up).
  - `raw_data_json`, `details_json` → `JSONB` (+ GIN-Index wo abgefragt wird).
  - MySQL-Block (Zeilen ~489-935) komplett löschen, SQLite-Block wird
    Postgres-Block.
  - `_ensure_column_mysql`/`_ensure_index_mysql` → Postgres-Varianten
    (`information_schema`, `CREATE INDEX IF NOT EXISTS`).
- [ ] Bestehende Datensätze: JSONB-Spalten beim Import mit
      `NULLIF(raw_data_json, '')::jsonb` normalisieren (leere Strings sind in
      JSONB ungültig — häufiger MariaDB-Stolperstein).

### Phase 3 — Query-Module (3-4 Tage, der Kern)

- [ ] 16 Module in `shared/db/` durchgehen (`analytics.py` 1.335 Z. und
      `battles.py` 869 Z. zuerst, dann `donors.py`, `web_analytics.py`,
      `chat.py`, `users.py`, `streamers.py`, `groups.py`, `revenue.py`,
      `gifts.py`, `alerts.py`, `settings.py`, `sqlite_import.py`).
  Pro Modul: Dialekt-Tabelle oben abarbeiten, `REPLACE INTO`-Stellen
  einzeln semantisch prüfen, `lastrowid`-Nutzungen auf `RETURNING` umstellen.
- [ ] `is_mysql`-Verzweigungen in `app.py`, `routers/*`, `services/*`,
      `system_service.py` auflösen (grep `is_mysql`, `db_engine`).
- [ ] Neue JSONB-Abfragen dort, wo sie sofort Nutzen stiften:
      Chat-Intelligence und Web-Analytics Feld-Zugriffe statt Python-JSON-
      Parse (optionaler Schritt, kann auch nach dem Cutover kommen).

### Phase 4 — Migrationsskript & Tests (2 Tage)

- [ ] `migrate_mysql_to_postgres.py` (analog `migrate_sqlite_to_mysql.py`):
      Tabellenweise `SELECT` aus MariaDB → `COPY`-Batch-Insert nach Postgres,
      JSON-Spalten casten, Zeilen-/Checksummen-Vergleich am Ende.
- [ ] `tests/_bootstrap.py`: temp. SQLite → Postgres. Zwei Optionen:
  - **a)** Test-Postgres per compose-Service (`postgres:17-alpine`), DB pro
    Testrun eindeutig (`toktracker_test_$PID`), danach droppen.
  - **b)** `pg_tmp`/Ephemeral-Container in CI.
    Empfehlung: a — gleicher Pfad wie der bestehende Redis-Service.
- [ ] `tests/test_sql_dialect.py` auf Postgres-Dialekt umschreiben (prüft
      aktuell die Übersetzungs-Regexes — entfällt/ersetzt durch
      Roundtrip-Tests der kritischen Statements).
- [ ] `run_tests.sh` + `ci.yml`: Postgres-Service ergänzen.

### Phase 5 — Deployment (0,5 Tag)

- [ ] `docker-compose.yml`: `mariadb`-Service → `postgres:17-alpine`
      (Healthcheck `pg_isready`), `mariadb_data`-Volume → `postgres_data`.
- [ ] `Dockerfile`: `libpq`-Abhängigkeiten prüfen (psycopg-binary braucht
      keines, aber Alpine-Python-Wheel verifizieren).
- [ ] README/AGENTS/docs-Badges und Architekturdiagramm aktualisieren.

### Phase 6 — Cutover & Abräumen (0,5 Tag + Betrieb)

- [ ] Prod-Dump ziehen, `migrate_mysql_to_postgres.py` laufen lassen,
      Services auf `DB_ENGINE=postgres` umstellen, kurzer Stop-Window
      (Ingest-Worker pausieren, damit keine Events verloren gehen).
- [ ] 1-2 Wochen Parallelbetrieb der MariaDB-Container (nur lesbar als
      Fallback), danach entfernen.
- [ ] Aufräumen: `PyMySQL` aus `requirements.txt`, `migrate_sqlite_to_mysql.py`
      ins `docs/`-Archiv, `DB_ENGINE`-Legacy-Werte ablehnen, `sqlite_import.py`
      entfernen oder als Import-Tool für bestehende SQLite-Exports behalten.

---

## 4. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
| :--- | :--- | :--- |
| `REPLACE INTO`-Semantik | Datenverlust/verwaiste FKs | Jede Stelle einzeln prüfen (grep `INSERT OR REPLACE`), Tests mit FK-Kind-Zeilen |
| Leere Strings in JSON-Spalten | Import bricht ab | `NULLIF(...,'')::jsonb` + Pre-Flight-Check im Migrationsskript |
| Unix-Timestamp vs. TIMESTAMPTZ | Zeitzonen-Bugs (TZ=Europe/Berlin, `apply_timezone`) | Vorerst Integer-Timestamps beibehalten; TIMESTAMPTZ als separater Follow-up |
| `lastrowid`-Nutzungen | falsche IDs nach Multi-Insert | `RETURNING id`, gezielt getestet |
| Test-Infra braucht Postgres | CI langsamer/komplexer | compose-Service wie Redis; `pg_tmp` als Fallback |
| Ingest-Ausfall beim Cutover | verlorene Gift-Events | Combox-Stop-Window, Redis-Bus puffert kurzzeitig, danach Replay prüfen |
| `MAX(a,b)`-Regex-Hack | falsche Übersetzung | Im Zielcode direkt `GREATEST` schreiben, kein Regex nötig |

## 5. Aufwand

| Phase | Aufwand |
| :--- | :--- |
| 0-1 (Vorbereitung, Config, Pool) | ~1,5 Tage |
| 2 (Schema) | ~1,5 Tage |
| 3 (Query-Module, Kern) | ~3-4 Tage |
| 4 (Migration + Tests) | ~2 Tage |
| 5-6 (Deployment + Cutover) | ~1 Tag + Parallelbetrieb |
| **Gesamt** | **~9-10 Personen-Tage** |

## 6. Abnahmekriterien

- Alle 41 Testdateien grün gegen eine frische Postgres-DB (keine SQLite-Pfade).
- `grep -r "mysql\|sqlite3\|pymysql" --include="*.py"` liefert nur noch
  Archiv-/Import-Referenzen.
- `migrate_mysql_to_postgres.py` validiert Prod-Dump zeilengenau (Checksummen).
- JSONB-Feldabfrage in Chat-Intelligence oder Web-Analytics demonstriert
  (das ursprüngliche Motiv).
- Compose-Hochfahren von Null (leere Volumes) liefert ein lauffähiges System.
