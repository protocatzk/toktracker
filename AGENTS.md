# AGENTS.md – Codebasis-Leitfaden & Architekturübersicht

Dieses Dokument dient KI-Agenten und Entwicklern als schneller, präziser Leitfaden zum Verständnis der Codebasis, der Systemarchitektur, der Datenflüsse und der Entwicklungsrichtlinien.

---

## 1. Zweck des Projekts

**TT-INTELLIGENCE (TikTok Live Earnings Tracker)** ist eine asynchrone Python-Anwendung (FastAPI), die TikTok-Livestreams in Echtzeit überwacht.

### Kernaufgaben
- **Live-Event-Tracking**: Erfassen von Geschenken (Coins, Diamonds), Zuschauerzahlen und Stream-Status via `TikTokLive`.
- **Finanzmetriken**: Präzise Berechnung von Brutto-Kaufwerten (Viewer-Ausgaben) und Netto-Creator-Auszahlungen in **USD ($)** und **EUR (€)**.
- **Web-Dashboard**: Modernes Web-Interface (Jinja2, CSS, Vanilla JS) für Admins und eine schlanke öffentliche Ansicht (`/public`).
- **Telegram-Bot Integration**: Automatisierte 24h-Reports, Streamer-Statistiken, Live-Status-Checks, Live-Alerts für einzelne Streamer in Gruppen und interaktiver 2FA-/1-Click-Login für das Web-Admin-Panel.
- **Dual-Database Engine**: Vollständige Unterstützung von **SQLite** (lokal mit WAL-Modus) und **MySQL / MariaDB** (Produktion).

---

## 2. Architektur & Komponenten (Microservices + Redis Bus)

```
                              ┌─────────────────────────┐
                              │    TikTok Livestreams   │
                              └────────────┬────────────┘
                                           │ WebSocket / Protobuf
                                           ▼
┌──────────────────────┐      ┌─────────────────────────┐      ┌──────────────────────┐
│     Telegram-Bot     │      │   TikTok Ingest Worker  │      │ TokTracker Scheduler │
│   (services/bot)     │      │   (services/ingest)     │      │ (services/scheduler) │
└──────────┬───────────┘      └────────────┬────────────┘      └──────────┬───────────┘
           │                               │                              │
           │                               │                              │
           ▼                               ▼                              ▼
    ┌────────────────────────────────────────────────────────────────────────────┐
    │                 Redis 7 (Message-Bus, Leases & Shared State)               │
    │  - tt:events (Streams)     - tt:cmd:* (PubSub)        - tt:rpc:bot (RPC)   │
    │  - tt:lease:* (Sharding)   - tt:diag:* (Telemetrie)   - tt:auth:* (Login)  │
    └────────────────────────────────────────────────────────────────────────────┘
                                           ▲
                                           │
┌──────────────────────┐      ┌────────────┴────────────┐
│      Nginx & SSL     │◄────►│   TokTracker Web & API  │
│  (Reverse Proxy/ACME)│      │     (services/api)      │
└──────────────────────┘      └────────────┬────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │  MariaDB / MySQL Engine │
                              │   (shared/database.py)  │
                              └─────────────────────────┘
```

---

## 3. Datei- & Modulübersicht

| Datei / Verzeichnis | Rolle & Hauptaufgaben |
| :--- | :--- |
| [`shared/`](./shared) | **Monorepo Shared Package**: Beinhaltet `config.py`, `schemas.py`, `contracts.py`, `auth_store.py`, `monitor_client.py`, `bot_client.py`, `privacy.py`, `ratelimit.py` sowie die Bus-Abstraktionen (`shared/bus/redis_bus.py`, `memory_bus.py`). |
| [`shared/db/`](./shared/db) | **Datenbank-Paket**: `_base` (Pool, Wrapper, `get_db`), `schema`, `settings`, `users`, `streamers`, `gifts`, `battles`, `donors`, `analytics`, `chat`, `web_analytics`, `sqlite_import`. [`shared/database.py`](./shared/database.py) ist nur noch Re-Export-Fassade. |
| [`services/api/`](./services/api) / [`app.py`](./app.py) | **Web-Dashboard & REST-API Service (FastAPI)**. Verwaltet Web-Routen (`/`, `/panel`, `/public`, `/login`, `/admin`), REST-API (`/api/*`), Auth und CSV-Exporte. Läuft in Produktion mit 2 Uvicorn-Workern und `uvloop`. |
| [`services/ingest/`](./services/ingest) | **TikTokLive Ingest Worker**. Beinhaltet `coordinator.py` und `main.py`. Überwacht TikTokLive-Streams horizontal skalierbar über Redis-Leases (`tt:lease:*`) mit automatischem Reconcile & Failover. |
| [`services/bot/`](./services/bot) | **Telegram-Bot Service**. Läuft als geschütztes Singleton mit Leader-Lock (`tt:lock:bot:leader`). Reagiert auf Bot-Befehle und verarbeitet RPC-Anfragen (z.B. Login-Codes an Admins senden) via Redis. |
| [`services/scheduler/`](./services/scheduler) | **TokTracker Scheduler Service**. Verwaltet wiederkehrende Aufgaben: automatischen 24h-Report, periodisches Speicherplatz-Monitoring (alle 15 Min) sowie Chat-Cleanup und Cache-Refresh. |
| [`tiktok_service.py`](./tiktok_service.py) | **TikTok-Monitoring-Engine**. Definiert `StreamerWorker` mit WebSocket-Eventhandlern (`ConnectEvent`, `GiftEvent`, etc.), Streak-Aggregation und uvloop-Unterstützung. |
| [`telegram_service.py`](./telegram_service.py) | **Telegram-Bot-Implementierung**. Befehlshandler, Menüs, Inline-Keyboards und Report-Formatter. |
| [`shared/bot_format.py`](./shared/bot_format.py) | **Bot-Textsystem**. Einheitliche Eyebrows, `<pre>`-Kennzahlen, Status-Glyphen und Message-Chunking im Industrial-Stil. |
| [`docker-compose.yml`](./docker-compose.yml) | **Produktions-Orchestrierung**. Definiert `redis`, `app` (Web/API), `ingest` (TikTok Worker), `bot` (Telegram), `scheduler`, `db` (MariaDB), `docker-socket-proxy` (nur lesende Docker-API) sowie `nginx-proxy` und `acme-companion` (SSL). |
| [`templates/`](./templates) | **Jinja2-HTML-Templates**: `landing.html` (öffentliche Infoseite unter `/`), `index.html` (Admin-Dashboard), `stats.html` (read-only Moderator-Statistiken), `access.html` (Whitelist, Anfragen & Rollen), `login.html` (Web-Login mit Telegram-2FA), `public.html` (Öffentliche Streamer-Übersicht). |
| [`static/`](./static) | **Frontend-Assets**: `brand.css` (Industrial-Design-System, Tokens, Dark/Light, lokale Fonts unter `static/fonts/`), `style.css` (gemeinsame App-Komponenten), `landing.css` (öffentliche Infoseite), `dashboard.js` (Dashboard-Logik, Polling, Charts), `stats.js` (read-only Statistik-Seite), `access.js`/`access.css` (Zugriffsverwaltung), `public.js` (öffentliche Tabelle). |

---

## 4. Datenmodell & Datenbankarchitektur

Die Anwendung abstrahiert SQLite und MySQL über eigene Wrapper (`MySQLConnectionWrapper`, `DBRow`) in [`shared/db/_base.py`](./shared/db/_base.py). Alle Queries nutzen `?` als Platzhalter (wird für MySQL intern zu `%s` konvertiert).

**Geldbeträge:** In MySQL/MariaDB sind `usd_net`, `eur_net`, `usd_gross`, `eur_gross` (Tabellen `gift_events`, `tiktok_battles`) als `DECIMAL(14,4)` definiert; `DBRow` normalisiert `Decimal` beim Lesen zentral zu `float`, damit beide Engines identische Typen liefern. SQLite speichert `REAL` (kein echtes DECIMAL). Migration bestehender Installationen: `python migrate_money_to_decimal.py [--apply]`.

### Kern-Tabellen:
1. **`streamers`**:
   - `id`, `username`, `display_name`, `avatar_url`, `is_live`, `follower_count`, `current_viewers`, `peak_viewers`, `total_diamonds`, `is_tracking`, `auto_monitor`, `last_seen_live`.
2. **`stream_sessions`**:
   - `id`, `streamer_id`, `start_time`, `end_time`, `peak_viewers`, `diamonds_collected`, `status`.
3. **`gift_events`**:
   - `id`, `streamer_id`, `session_id`, `gift_name`, `diamond_count`, `repeat_count`, `total_diamonds`, `sender_username`, `sender_nickname`, `source`, `timestamp`.
4. **`settings`**:
   - Key-Value Store für Währungskurse (`usd_per_diamond`, `gross_usd_per_coin`, `usd_to_eur_rate`, `currency_primary`), Polling-Intervalle, API-Keys und Zugriffsmodi.
5. **`telegram_users`**:
   - Rollen- & Berechtigungstabelle (`user_id`, `username`, `role` [viewer/user/moderator/admin], `is_allowed` [1=erlaubt, 0=wartend, -1=gesperrt]).
6. **`streamer_alerts`**:
   - Live-Alert-Abos pro Streamer und Telegram-Chat (`streamer_id`, `chat_id`, `chat_title`, `created_by_*`, `enabled`, `last_notified_session_id`). Eindeutig pro Streamer/Chat.
7. **`admin_challenges`**:
   - Temporäre Login-Anfragen für das Web-Dashboard mit Status (`pending`, `approved`, `rejected`, `expired`).

---

## 5. Typische Datenflüsse

### A. TikTok-Live Überwachung
1. User fügt Streamer hinzu oder Anwendung startet (`monitor_manager.autostart_from_db()`).
2. Pro Streamer läuft ein `StreamerWorker` in einem separaten Thread.
3. Der Worker verbindet sich mit dem TikTok-WebSocket.
4. Bei Geschenken fängt `on_gift` die Events ab, puffert Combo-/Streak-Geschenke kurz (`_streak_watchdog_loop`) und persistiert sie über `record_gift_event()` in die Datenbank.
5. Geht ein Streamer offline, schaltet der Supervisor in den Polling-Modus (`_supervisor_loop`), bis der Streamer wieder online geht.
6. Bei einer neuen Live-Session veröffentlicht `on_connect` ein `live_status`-Event auf `tt:event:live_status`. Der Bot liest die Abos aus `streamer_alerts` und sendet je Chat einen Live-Alert (dedupliziert über `last_notified_session_id`).

### B. Telegram-Bot 2FA Web-Login
1. Nutzer öffnet `/login` und fordert Login an.
2. `admin_auth_manager.create_challenge()` generiert eine Challenge-ID und einen 6-stelligen Zahlencode.
3. Der Bot sendet eine Push-Nachricht mit Inline-Buttons ("Zulassen" / "Ablehnen") an hinterlegte Telegram-Admins.
4. Klickt ein Admin auf "Zulassen" (oder tippt der Nutzer den 6-stelligen Code ein), autorisiert das Backend die Session und setzt das Cookie `toktracker_session`.

### C. Dashboard & Reporting
- Das Dashboard pollt `/api/overview?period=today` (oder `24h`, `7d`, `all`).
- [`shared/db/analytics.py`](./shared/db/analytics.py) aggregiert Gesamteinnahmen, Rechner-Kurse (EUR/USD), Top-Spender und Streamer-Rankings.
- Ein automatischer Telegram-Job (`_scheduled_24h_report_job`) sendet alle 24h eine Zusammenfassung in den konfigurierten Chat.

---

## 5b. Zugriffssperre (ACCESS_GATE)

Standard ist `ACCESS_GATE=whitelist`: Die Zugriffssperre in `app.py`
(`access_gate_middleware`, Logik in `shared/access_gate.py`) lässt jede gültige,
nicht gesperrte Session bzw. Inhaber des API-Keys durch. Öffentlich bleiben nur
Login-Seite/Login-Endpunkte, `/static`, `/pictures`, `/api/health`, `/robots.txt`
und die Mini-App-Seite. Abgewiesene Aufrufe erzeugen keine Analytics-Einträge
(Gate liegt außerhalb der Analytics-Middleware) und tragen `X-Robots-Tag: noindex`.

Die **feingranulare Rechte-Matrix** liegt in [`shared/permissions.py`](./shared/permissions.py):

| Rolle | Rechte (Kurzform) |
| :--- | :--- |
| `viewer` | Nur öffentliche Seiten/APIs (`public.view`) |
| `user` | Zusätzlich Spender-Radar, Chatlogs & Chat-Intelligence (`radar.view`, `chatintel.view`) |
| `moderator` | Zusätzlich interne Statistiken, Exporte & Systemstatus (`analytics.view`, `export.download`, `system.view`) – **keine Schreibrechte** |
| `admin` | Alle Rechte inkl. CRM, Streamer-Verwaltung, Geschenk-Buchung, Einstellungen, Nutzerverwaltung und System-Management |

API-Keys werden intern als `admin` behandelt. Endpunkte sichern sich über
`require_permission(<capability>)` ab; `verify_admin_or_api_key` bleibt der
Admin-only-Fallback. Neue geschützte Endpunkte müssen ein passendes Recht
verwenden, statt pauschal `verify_admin_or_api_key` zu nehmen.

### Bot-Rechte (`bot.*`)

Telegram-Befehle sind ebenfalls an die Rechte-Matrix gekoppelt, nutzen aber
eigene `bot.*`-Capabilities. Dadurch lässt sich die Bot-Oberfläche unabhängig
von den Web-Modulen steuern. Die zentrale Zuordnung liegt in
[`shared/permissions.py`](./shared/permissions.py) in
`BOT_COMMAND_PERMISSIONS` / `BOT_COMMAND_ALIASES`.

Jeder neue Bot-Befehl muss dort eingetragen und im Handler über
`_authorize(..., require_permission=PERM_BOT_*)` geprüft werden. Die Tests in
[`tests/test_bot_permissions.py`](./tests/test_bot_permissions.py) erzwingen,
dass jeder registrierte `CommandHandler` eine Capability besitzt und der
Handler sie tatsächlich prüft. `/id` bleibt bewusst ohne Prüfung, weil der
Befehl nur den eigenen Status anzeigt.

Die dedizierte Verwaltungsoberfläche unter `/access` bündelt Whitelist, offene
Anfragen, Sperren und die Rollen-/Rechte-Matrix. Sie erfordert
`users.manage`; Änderungen laufen über die bestehenden Telegram-Nutzer-APIs.

Die öffentliche Infoseite unter `/` wird über `LANDING_PAGE_ENABLED=1`
(Default) aktiviert und ist bewusst für alle erreichbar. Bei `0` liefert `/`
wieder das öffentliche Live-Panel und unterliegt dem Gate. `/public` und
`/panel` bleiben in beiden Fällen eigenständige Live-Panel-Routen.

Neue öffentliche Endpunkte müssen bewusst in `shared/access_gate.py`
(`EXEMPT_PATHS`) eingetragen werden — sonst sind sie automatisch gesperrt.

### Betrieb unter einem Unterpfad (`APP_BASE_PATH`)

Die App kann zusätzlich unter einem URL-Prefix wie `https://positronium.dev/track`
laufen. Dafür sind drei Dinge nötig:

1. `APP_BASE_PATH=/track` in der App-Umgebung setzen.
2. Der Reverse-Proxy sendet `X-Forwarded-Prefix: /track` und reicht den Pfad
   unverändert durch.
3. Ein vorgeschalteter Gateway-Service routet den Prefix auf die App
   (`nginx/positronium-track.conf` + Compose-Service `positronium-track`).

Die Middleware `base_path_middleware` in `app.py` entfernt den Präfix vor dem
Routing, setzt `root_path` und ergänzt ihn wieder in `Location`-Headern.
Templates verwenden `<base href="{{ request.state.base_path }}/">` und relative
Asset-/API-Pfade; JavaScript nutzt für serverseitige Redirect-Pfade `appUrl()`.
Tests in [`tests/test_base_path.py`](./tests/test_base_path.py) decken Root- und
Prefix-Betrieb ab.

## 6. Richtlinien für KI-Agenten bei Änderungen

Beachte bei Änderungen an der Codebasis zwingend folgende Regeln:

1. **Dual-Database Kompatibilität wahren**:
   - Niemals SQLite-spezifische Syntax verwenden, die auf MySQL fehlschlägt (z.B. `INSERT OR REPLACE` vs. `ON DUPLICATE KEY UPDATE`). In [`shared/db/schema.py`](./shared/db/schema.py) existieren bereits Methoden wie `_init_sqlite_schema()` und `_init_mysql_schema()`.
   - Bei Tabellen- oder Spaltenänderungen **beide** Schemas und Migrationen pflegen.

2. **Threading & Asyncio Isolation**:
   - `tiktok_service.py` nutzt dedizierte Worker-Threads mit eigenen Event-Loops. Blockierende I/O-Operationen müssen vorsichtig gehandhabt werden.
   - Der Telegram-Bot läuft asynchron im Hauptprozess unter FastAPI. Niemals den Event-Loop mit synchronen Endlosschleifen blockieren.
   - DB-Zugriffe immer über den Kontextmanager `with get_db() as conn:` kapseln.
   - Neue DB-Funktionen im passenden Modul unter `shared/db/` ergänzen und in `shared/db/__init__.py` re-exportieren.

3. **API & Schemas**:
   - Neue Request/Response-Objekte in [`schemas.py`](./schemas.py) definieren.
   - API-Endpunkte in [`app.py`](./app.py) immer mit Dependency `verify_admin_or_api_key` absichern, es sei denn, sie sind explizit öffentlich (wie `/public` oder `/api/auth/*`).
   - Abwärtskompatibilität: Viele Endpunkte sind sowohl unter `/api/...` als auch `/api/v1/...` registriert.

4. **Fehlertoleranz**:
   - Wenn der Telegram-Bot nicht erreichbar ist (z.B. falscher Token), darf FastAPI nicht abstürzen. Das System ist fehlertolerant aufgebaut (`telegram_bot_service.start()` fängt Fehler isoliert ab).

---

## 7. Wichtige Befehle

### Anwendung starten
```bash
# Kompletter Stack (Produktion)
docker compose up -d --build

# Nur Web/API-Service neu bauen und starten
docker compose build app && docker compose up -d app

# Lokal ohne Docker (Port 5000)
python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

### Migration von SQLite zu MySQL
```bash
docker exec toktracker_app python migrate_sqlite_to_mysql.py
# oder lokal:
python migrate_sqlite_to_mysql.py
```

### Qualitätssicherung
```bash
ruff check .          # Lint
mypy                  # Typen (kuratierter Scope, siehe pyproject.toml)
pytest -q             # Testsuite (isolierte SQLite-DB)
./run_tests.sh        # Testsuite im laufenden Container (inkl. Redis-Pfade)
```

### Tests ausführen (Ressourcensparend, Quotenfrei & Rückstandslos)
```bash
# Führt alle Tests im Container aus und löscht die Testdateien danach automatisch:
./run_tests.sh

# Oder direkt in der lokalen Python-Umgebung:
python tests/run_tests.py
```
