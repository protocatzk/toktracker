# AGENTS.md – Codebasis-Leitfaden & Architekturübersicht

Dieses Dokument dient KI-Agenten und Entwicklern als schneller, präziser Leitfaden zum Verständnis der Codebasis, der Systemarchitektur, der Datenflüsse und der Entwicklungsrichtlinien.

---

## 1. Zweck des Projekts

**TokTracker (TikTok Live Earnings Tracker)** ist eine asynchrone Python-Anwendung (FastAPI), die TikTok-Livestreams in Echtzeit überwacht.

### Kernaufgaben
- **Live-Event-Tracking**: Erfassen von Geschenken (Coins, Diamonds), Zuschauerzahlen und Stream-Status via `TikTokLive`.
- **Finanzmetriken**: Präzise Berechnung von Brutto-Kaufwerten (Viewer-Ausgaben) und Netto-Creator-Auszahlungen in **USD ($)** und **EUR (€)**.
- **Web-Dashboard**: Modernes Web-Interface (Jinja2, CSS, Vanilla JS) für Admins und eine schlanke öffentliche Ansicht (`/public`).
- **Telegram-Bot Integration**: Automatisierte 24h-Reports, Streamer-Statistiken, Live-Status-Checks und interaktiver 2FA-/1-Click-Login für das Web-Admin-Panel.
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
| [`shared/`](file:///home/toktracker/toktrackerapp/shared) | **Monorepo Shared Package**: Beinhaltet `config.py`, `database.py`, `schemas.py`, `contracts.py`, `auth_store.py`, `monitor_client.py`, `bot_client.py` sowie die Bus-Abstraktionen (`shared/bus/redis_bus.py` und `memory_bus.py`). |
| [`services/api/`](file:///home/toktracker/toktrackerapp/services/api) / [`app.py`](file:///home/toktracker/toktrackerapp/app.py) | **Web-Dashboard & REST-API Service (FastAPI)**. Verwaltet Web-Routen (`/`, `/panel`, `/public`, `/login`, `/admin`), REST-API (`/api/*`), Auth und CSV-Exporte. Läuft in Produktion mit 2 Uvicorn-Workern und `uvloop`. |
| [`services/ingest/`](file:///home/toktracker/toktrackerapp/services/ingest) | **TikTokLive Ingest Worker**. Beinhaltet `coordinator.py` und `main.py`. Überwacht TikTokLive-Streams horizontal skalierbar über Redis-Leases (`tt:lease:*`) mit automatischem Reconcile & Failover. |
| [`services/bot/`](file:///home/toktracker/toktrackerapp/services/bot) | **Telegram-Bot Service**. Läuft als geschütztes Singleton mit Leader-Lock (`tt:lock:bot:leader`). Reagiert auf Bot-Befehle und verarbeitet RPC-Anfragen (z.B. Login-Codes an Admins senden) via Redis. |
| [`services/scheduler/`](file:///home/toktracker/toktrackerapp/services/scheduler) | **TokTracker Scheduler Service**. Verwaltet wiederkehrende Aufgaben: automatischen 24h-Report, periodisches Speicherplatz-Monitoring (alle 15 Min) sowie Chat-Cleanup und Cache-Refresh. |
| [`tiktok_service.py`](file:///home/toktracker/toktrackerapp/tiktok_service.py) | **TikTok-Monitoring-Engine**. Definiert `StreamerWorker` mit WebSocket-Eventhandlern (`ConnectEvent`, `GiftEvent`, etc.), Streak-Aggregation und uvloop-Unterstützung. |
| [`telegram_service.py`](file:///home/toktracker/toktrackerapp/telegram_service.py) | **Telegram-Bot-Implementierung**. Befehlshandler, Menüs, Inline-Keyboards und Report-Formatter. |
| [`docker-compose.yml`](file:///home/toktracker/toktrackerapp/docker-compose.yml) | **Produktions-Orchestrierung**. Definiert `redis`, `app` (Web/API), `ingest` (TikTok Worker), `bot` (Telegram), `scheduler`, `db` (MariaDB), `nginx-proxy` und `acme-companion` (SSL). |
| [`frontend/`](file:///home/toktracker/toktrackerapp/frontend) | **Vue 3 + TypeScript Frontend Suite (Vite & Pinia)**. Multi-Page SPA für Admin-Dashboard (`index.html`) und öffentliches Portal (`public.html`). Nutzt typisierte Pinia-Stores, Chart.js und wird via Docker Multi-Stage Build kompilationsfrei in Produktion ausgeliefert. |
| [`templates/`](file:///home/toktracker/toktrackerapp/templates) | **Jinja2-HTML-Templates**: `index.html` & `public.html` (Fallback-Templates), `login.html` (Web-Login mit Telegram-2FA). |
| [`static/`](file:///home/toktracker/toktrackerapp/static) | **Frontend-Assets**: Globale Icons, Stylesheet (`style.css`), Chart.js Bundle und Legacy-Fallback Skripte. |

---

## 4. Datenmodell & Datenbankarchitektur

Die Anwendung abstrahiert SQLite und MySQL über eigene Wrapper (`MySQLConnectionWrapper`, `DBRow`) in [`database.py`](file:///C:/Users/heliac/PycharmProjects/FlaskProject1/database.py). Alle Queries nutzen `?` als Platzhalter (wird für MySQL intern zu `%s` konvertiert).

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
   - Rollen- & Berechtigungstabelle (`user_id`, `username`, `role` [user/admin], `is_allowed` [1=erlaubt, 0=wartend, -1=gesperrt]).
6. **`admin_challenges`**:
   - Temporäre Login-Anfragen für das Web-Dashboard mit Status (`pending`, `approved`, `rejected`, `expired`).

---

## 5. Typische Datenflüsse

### A. TikTok-Live Überwachung
1. User fügt Streamer hinzu oder Anwendung startet (`monitor_manager.autostart_from_db()`).
2. Pro Streamer läuft ein `StreamerWorker` in einem separaten Thread.
3. Der Worker verbindet sich mit dem TikTok-WebSocket.
4. Bei Geschenken fängt `on_gift` die Events ab, puffert Combo-/Streak-Geschenke kurz (`_streak_watchdog_loop`) und persistiert sie über `record_gift_event()` in die Datenbank.
5. Geht ein Streamer offline, schaltet der Supervisor in den Polling-Modus (`_supervisor_loop`), bis der Streamer wieder online geht.

### B. Telegram-Bot 2FA Web-Login
1. Nutzer öffnet `/login` und fordert Login an.
2. `admin_auth_manager.create_challenge()` generiert eine Challenge-ID und einen 6-stelligen Zahlencode.
3. Der Bot sendet eine Push-Nachricht mit Inline-Buttons ("Zulassen" / "Ablehnen") an hinterlegte Telegram-Admins.
4. Klickt ein Admin auf "Zulassen" (oder tippt der Nutzer den 6-stelligen Code ein), autorisiert das Backend die Session und setzt das Cookie `toktracker_session`.

### C. Dashboard & Reporting
- Das Dashboard pollt `/api/overview?period=today` (oder `24h`, `7d`, `all`).
- [`database.py`](file:///C:/Users/heliac/PycharmProjects/FlaskProject1/database.py) aggregiert Gesamteinnahmen, Rechner-Kurse (EUR/USD), Top-Spender und Streamer-Rankings.
- Ein automatischer Telegram-Job (`_scheduled_24h_report_job`) sendet alle 24h eine Zusammenfassung in den konfigurierten Chat.

---

## 6. Richtlinien für KI-Agenten bei Änderungen

Beachte bei Änderungen an der Codebasis zwingend folgende Regeln:

1. **Dual-Database Kompatibilität wahren**:
   - Niemals SQLite-spezifische Syntax verwenden, die auf MySQL fehlschlägt (z.B. `INSERT OR REPLACE` vs. `ON DUPLICATE KEY UPDATE`). In [`database.py`](file:///C:/Users/heliac/PycharmProjects/FlaskProject1/database.py) existieren bereits Methoden wie `_init_sqlite_schema()` und `_init_mysql_schema()`.
   - Bei Tabellen- oder Spaltenänderungen **beide** Schemas und Migrationen pflegen.

2. **Threading & Asyncio Isolation**:
   - `tiktok_service.py` nutzt dedizierte Worker-Threads mit eigenen Event-Loops. Blockierende I/O-Operationen müssen vorsichtig gehandhabt werden.
   - Der Telegram-Bot läuft asynchron im Hauptprozess unter FastAPI. Niemals den Event-Loop mit synchronen Endlosschleifen blockieren.
   - DB-Zugriffe immer über den Kontextmanager `with get_db() as conn:` kapseln.

3. **API & Schemas**:
   - Neue Request/Response-Objekte in [`schemas.py`](file:///C:/Users/heliac/PycharmProjects/FlaskProject1/schemas.py) definieren.
   - API-Endpunkte in [`app.py`](file:///C:/Users/heliac/PycharmProjects/FlaskProject1/app.py) immer mit Dependency `verify_admin_or_api_key` absichern, es sei denn, sie sind explizit öffentlich (wie `/public` oder `/api/auth/*`).
   - Abwärtskompatibilität: Viele Endpunkte sind sowohl unter `/api/...` als auch `/api/v1/...` registriert.

4. **Fehlertoleranz**:
   - Wenn der Telegram-Bot nicht erreichbar ist (z.B. falscher Token), darf FastAPI nicht abstürzen. Das System ist fehlertolerant aufgebaut (`telegram_bot_service.start()` fängt Fehler isoliert ab).

---

## 7. Wichtige Befehle

### Anwendung starten
```powershell
# Virtuelle Umgebung aktivieren (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Server starten (Port 5000)
python app.py
# oder via Uvicorn direkt:
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

### Migration von SQLite zu MySQL
```powershell
python migrate_sqlite_to_mysql.py
```

### Tests ausführen (Ressourcensparend, Quotenfrei & Rückstandslos)
```bash
# Führt alle Tests im Container aus und löscht die Testdateien danach automatisch:
./run_tests.sh

# Oder direkt in der lokalen Python-Umgebung:
python tests/run_tests.py
```
