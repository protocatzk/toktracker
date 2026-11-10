# TT-INTELLIGENCE

**Live Earnings Intelligence** – erfasst TikTok-Livestreams in Echtzeit, berechnet Brutto-/Netto-Einnahmen in USD und EUR, visualisiert sie in einem Web-Dashboard und liefert Reports über einen Telegram-Bot.

> Markenhinweis: Die sichtbare Oberfläche heißt **TT-INTELLIGENCE**. Technische
> Bezeichner (Cookies, localStorage-Keys, Redis-Prefixe, Docker-Services,
> Datenbank-Namen) bleiben aus Kompatibilitätsgründen unter `toktracker`.
> Die Marken-Konstanten liegen zentral in [`shared/branding.py`](./shared/branding.py).

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![MariaDB](https://img.shields.io/badge/MariaDB-11-003545?logo=mariadb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## Funktionsumfang

| Bereich | Funktionen |
| :--- | :--- |
| **Live-Tracking** | Geschenke (Coins/Diamonds) in Echtzeit, Combo-/Streak-Aggregation, Zuschauerzahlen, Stream-Sessions, Battle-Erkennung (1v1, 2v2, 1v1v1, 1v1v1v1) |
| **Finanzen** | Brutto-Kaufwert (Zuschauer) und Netto-Auszahlung (Creator) in USD und EUR, konfigurierbare Kurse, Periodenfilter (today/24h/7d/30d/all) |
| **Web-Oberfläche** | Öffentliche Infoseite (`/`), Öffentliches Read-Only-Panel (`/public`), Admin-Dashboard (`/admin`), Moderator-Statistiken (`/stats`), Analytics (`/site-analytics`), Spender-Radar (`/donor-radar`), Chat-Intelligence (`/chat-intelligence`), Telegram Mini-App (`/app`) |
| **Telegram-Bot** | 24h-Reports, Streamer-Statistiken, Live-Status (`/live`), Live-Alerts für einzelne Streamer in Gruppen (`/alert`), Whitelist-Verwaltung, Login per Telegram-Widget/OTP |
| **Sicherheit** | HMAC-signierte Sessions, Telegram-Signaturprüfung, Whitelist/Rollen, Rate-Limiting auf Auth-Endpunkten, Datenschutz-Maskierung auf öffentlichen Flächen |
| **Betrieb** | Microservices mit Redis-Bus, horizontales Ingest-Sharding über Leases, Leader-Locks, Healthchecks, Docker-Compose mit Nginx + Let's Encrypt |

### Live-Alerts im Telegram-Bot

In einer Gruppe kann ein Admin Live-Benachrichtigungen für einzelne Streamer abonnieren:

- `/alert @streamer` – Alert in diesem Chat aktivieren
- `/alert off @streamer` – Alert deaktivieren
- `/alert list` – aktive Alerts anzeigen

Der Streamer muss für das Auto-Monitoring markiert sein (z.B. per `/track @streamer`), damit TokTracker den Live-Gang erkennt. Der Bot verschickt den Alert an alle abonnierten Chats.

---

## Architektur

```
TikTok Live ──WebSocket──▶ ingest (Worker + Lease-Sharding) ─┐
                                                             ├─▶ Redis 7 (Bus, Leases, Rate-Limits)
api (FastAPI, Web + REST) ◀──PubSub/Streams──────────────────┤
bot (Telegram, Leader-Lock) ◀────────RPC─────────────────────┤
scheduler (Reports, Cleanup, Disk-Monitoring) ◀──────────────┘
                                                             │
                                              MariaDB / MySQL ◀─▶ SQLite (lokaler Fallback)
```

| Pfad | Rolle |
| :--- | :--- |
| `app.py` | FastAPI-App: Web-Routen, REST-API, Auth, Exports |
| `shared/` | Config, DB-Abstraktion (SQLite + MySQL), Schemas, Bus, Auth, Clients |
| `services/api`, `services/ingest`, `services/bot`, `services/scheduler` | Service-Einstiegspunkte |
| `tiktok_service.py` | TikTokLive-Worker, Event-Handler, Reconnect-Supervisor |
| `telegram_service.py` | Bot-Befehle, Menüs, Report-Formatter |
| `templates/`, `static/` | Jinja2-Templates und Frontend-Assets |
| `tests/` | Testsuite (isolierte SQLite-DB, optional Redis) |

Details für Entwicklung und Betrieb: [`AGENTS.md`](./AGENTS.md).

---

## Quickstart

```bash
# 1. Konfiguration anlegen
cp .env.example .env
#    Pflicht: DOMAIN_NAME, SSL_EMAIL, MYSQL_PASSWORD, TIKTOK_API_KEY,
#             TELEGRAM_BOT_TOKEN, SESSION_SECRET (32+ Zeichen)

python -c "import secrets; print(secrets.token_hex(32))"   # SESSION_SECRET erzeugen

# 2. Stack starten
docker compose up -d --build

# 3. Healthcheck prüfen
curl -f http://localhost:5000/api/health
```

Ohne Docker (nur API/UI, SQLite):

```bash
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

---

## Konfiguration

Alle Variablen liegen in `.env` (siehe [`.env.example`](./.env.example)). Die wichtigsten:

| Variable | Zweck |
| :--- | :--- |
| `SESSION_SECRET` | Signatur der Admin-Sessions (min. 32 Zeichen, Pflicht in Produktion) |
| `TIKTOK_API_KEY` | API-Key für externe Skripte (`X-API-Key`-Header) |
| `ADMIN_PASSWORD` | Optionaler Notfall-Login, falls Telegram nicht erreichbar ist |
| `DB_ENGINE` | `mysql` (Produktion) oder `sqlite` (lokal) |
| `REDIS_URL` | Aktiviert Bus, Leases und verteilte Rate-Limits |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_USERS` | Bot und Whitelist |
| `SESSION_COOKIE_SECURE` | `auto` (nur HTTPS), `1` oder `0` |
| `ENABLE_API_DOCS` | `/docs`, `/redoc`, `/openapi.json` freischalten (Default: `0`) |
| `ACCESS_GATE` | `whitelist` (Default): nur per Telegram freigeschaltete Nutzer/API-Key kommen an die App, alle anderen landen auf `/login`. `off` = öffentlicher Betrieb |
| `LANDING_PAGE_ENABLED` | `1` (Default): `/` zeigt die öffentliche Infoseite. `0`: `/` zeigt wieder das öffentliche Live-Panel (und unterliegt dem Gate) |
| `APP_BASE_PATH` | Optionaler URL-Prefix, z.B. `/track` für `https://domain/track`. Leer = Root-Betrieb. Setzt einen passenden Proxy mit `X-Forwarded-Prefix` voraus |
| `TIKTOK_SIGN_API_KEY` | Euler-Stream-Sign-Key; hebt das Sign-API-Rate-Limit und aktiviert den globalen Cooldown |
| `TIKTOK_WS_PROXY` | Optionaler Proxy nur für die TikTok-WebSocket-Verbindung. Leer = Fallback auf `TIKTOK_WEB_PROXY` |
| `TIKTOK_STALL_TIMEOUT_SECONDS` | Zeit ohne WebSocket-Frame, nach der der Worker die Verbindung zwangsweise neu aufbaut (Default: `120`) |
| `TIKTOK_RECONNECT_*` | Basis, Maximum und Jitter des Reconnect-Backoffs (`5`, `120`, `0.25`) |
| `TIKTOK_SIGN_COOLDOWN_SECONDS` | Mindest-Cooldown nach einem Sign-API-429, global über Redis (Default: `60`) |
| `TIKTOK_SESSION_GRACE_SECONDS` | Kurze Offline-Meldungen beenden die Stream-Session erst nach dieser Grace-Period (Default: `90`) |
| `LIVE_ALERT_MIN_OFFLINE_MINUTES` | Mindest-Offline-Zeit, bevor ein neuer Stream einen Telegram-Live-Alert auslöst (Default: `30`) |

### Betrieb unter einem Unterpfad

Für `https://positronium.dev/track` ist im Compose-Stack ein schlanker
Gateway (`positronium-track`, Config: [`nginx/positronium-track.conf`](./nginx/positronium-track.conf))
enthalten. Er bekommt von nginx-proxy den Pfad `/track` und setzt
`X-Forwarded-Prefix: /track`. Die App entfernt den Präfix intern wieder, sodass
alle Routen unverändert funktionieren. Voraussetzung:

- `APP_BASE_PATH=/track` in der App-Umgebung
- DNS von `positronium.dev` zeigt auf den Server
- Ports 80/443 sind für Let's Encrypt erreichbar

### Ingest-Robustheit & Runbook

Der Ingest-Worker erkennt drei Fehlerklassen selbstständig:

1. **Stall:** `state=connected`, aber seit `TIKTOK_STALL_TIMEOUT_SECONDS` kein
   WebSocket-Frame. Der Worker trennt die Verbindung, zählt
   `stall_reconnects` hoch und verbindet mit Backoff neu.
2. **Offline / Stream-Ende:** `state=polling_offline`. Kurze Offline-Meldungen
   behalten die Session für `TIKTOK_SESSION_GRACE_SECONDS` aktiv, damit ein
   TikTok-Aussetzer keinen neuen Stream anlegt.
3. **Sign-API-Rate-Limit:** Der Worker setzt einen globalen Redis-Cooldown
   (`tt:ratelimit:sign`). Alle Ingest-Instanzen warten, statt die Quote weiter
   zu belasten.

**Live-Alerts:** Ein neuer Stream löst nur dann einen Telegram-Alert aus, wenn
der Streamer zuvor mindestens `LIVE_ALERT_MIN_OFFLINE_MINUTES` (Default: 30)
offline war. Kurze Stream-Neustarts und Reconnects werden übersprungen. Bei
einem geordneten Ingest-Stopp bleibt die aktive Session offen und wird beim
nächsten Start wiederverwendet.

Sichtbare Diagnose pro Streamer im Dashboard und unter `/api/system`:

- `Frame Xs` – Alter des letzten WebSocket-Frames
- `Reconnects`, `Stalls`, `Rate-Limits`
- `last_disconnect_reason`, `close_code`
- `Retry HH:MM:SS` – nächster geplanter Verbindungsversuch

**Wenn alle verbundenen Worker im Stack keine Frames mehr liefern**, meldet der
Docker-Healthcheck den Ingest unhealthy. Docker Compose startet unhealthy
Container nicht automatisch neu; dann `docker compose restart ingest` ausführen.
Mit den zwei Compose-Replicas übernimmt die andere Instanz die Leases nach
spätestens 30 Sekunden.

**Wenn ein einzelner Streamer hängt:** zuerst `Frame`-Alter und
`last_disconnect_reason` prüfen. Der Watchdog sollte innerhalb von
`TIKTOK_STALL_TIMEOUT_SECONDS` selbst neu verbinden. Bleibt der Worker trotzdem
stehen, den Worker über das Dashboard stoppen/starten oder den Ingest-Container
neu starten.

---

## Sicherheit & Datenschutz

- **Zugriffssperre:** Mit `ACCESS_GATE=whitelist` (Default) ist die gesamte
  Anwendung — inklusive `/`, `/public` und aller Daten-APIs — nur für per
  Telegram freigeschaltete Nutzer und API-Key-Inhaber erreichbar. Öffentlich
  bleiben ausschließlich `/login`, die Login-Endpunkte, statische Assets,
  `/api/health` und die Mini-App-Seite (für den Telegram-Login).
  Nicht freigeschaltete Besucher werden auf `/login` umgeleitet, API-Aufrufe
  erhalten `401`. Zusätzlich sendet der Server `X-Robots-Tag: noindex` und
  `robots.txt` verbietet Crawler, solange die Sperre aktiv ist.
  Deaktivieren: `ACCESS_GATE=off` in der `.env` (danach Neustart).
- Sessions dauern während der Sperre **24 Stunden** (sonst 7 Tage), damit
  entzogene Freigaben schnell wirken.
- Admin-Zugriff nur über Telegram-Login (Widget/OTP) oder API-Key; Sessions sind HMAC-signiert und `HttpOnly`/`Secure` (hinter HTTPS).
- Auth-Endpunkte sind rate-limitiert; Login-Challenges werden nach 5 Fehlversuchen gesperrt.
- Rollen: `viewer` (nur öffentliche Inhalte), `user` (Whitelist: Radar und
  Chat-Intelligence), `moderator` (Statistiken, Exporte und Systemstatus lesen,
  keine Schreibrechte) und `admin` (voller Zugriff). Die Rechte-Matrix liegt
  zentral in `shared/permissions.py`; API-Keys gelten als `admin`.
- Bot-Befehle verwenden eigene `bot.*`-Capabilities (zentral in
  `BOT_COMMAND_PERMISSIONS`), damit Web- und Telegram-Rechte getrennt bleiben.
  Whitelist, Anfragen, Sperren und die Rechte-Matrix verwaltest du unter `/access`.
- Spender-Namen sind auf öffentlichen Flächen standardmäßig **maskiert** (`public_show_donors=0`, im Admin-Panel umschaltbar).
- Interne Rohdaten (`raw_data_json`) werden nie über öffentliche Endpunkte ausgeliefert.
- Besucher-IPs werden ausschließlich als salted Hash gespeichert.

---

## Entwicklung

```bash
pip install -r requirements.txt -r requirements-dev.txt

ruff check .     # Lint
mypy             # Typen (kuratierter Scope)
pytest -q        # Testsuite, ~3 s
./run_tests.sh   # Testsuite im laufenden Container (inkl. Redis-Pfade)
```

Die Tests laufen gegen eine temporäre SQLite-Datenbank (`tests/_bootstrap.py`) und berühren niemals Produktionsdaten. CI: `.github/workflows/ci.yml` (Ruff, Mypy, Pytest mit Redis-Service, JS-Syntaxcheck).

**Datenbank-Migrationen**

```bash
docker exec toktracker_app python migrate_money_to_decimal.py           # Dry-Run
docker exec toktracker_app python migrate_money_to_decimal.py --apply   # ausführen
```

Geldspalten sind in MySQL/MariaDB `DECIMAL(14,4)` (exakte Cent-Beträge), SQLite nutzt `REAL`.

---

## Rechtliche Hinweise

Dieses Projekt ist **nicht mit TikTok, ByteDance oder verbundenen Unternehmen
verbunden** und wird von diesen nicht unterstützt oder genehmigt. „TikTok" ist
eine Marke der jeweiligen Inhaber.

- Die Anwendung greift auf öffentliche Live-Streams über eine **inoffizielle
  Schnittstelle** (`TikTokLive`) zu. Die Nutzung erfolgt auf eigenes Risiko;
  die TikTok-Nutzungsbedingungen können automatisierte Zugriffe untersagen.
- Alle Einnahmen- und Währungsangaben sind **Schätzungen** auf Basis
  konfigurierbarer Kurse. Sie sind keine Finanz-, Steuer- oder Rechtsberatung
  und keine Grundlage für Buchhaltung oder Auszahlungen.
- Wer die Anwendung öffentlich betreibt, ist selbst **Verantwortlicher im Sinne der
  DSGVO** für die verarbeiteten Daten (u. a. Telegram-IDs, Chat-Nachrichten,
  Spender-Namen) und muss Impressum, Datenschutzerklärung und
  Löschkonzept bereitstellen.

## Lizenz

Der eigene Quellcode steht unter der **MIT-Lizenz** – siehe [LICENSE](./LICENSE).
Sie erlaubt Nutzung, Veränderung, Weitergabe und kommerziellen Einsatz ohne
Gegenleistung; die Software wird ohne Gewährleistung bereitgestellt.

**Ausnahme:** Die Kernabhängigkeit `TikTokLive` steht unter **AGPL-3.0**. Wer ein
daraus gebautes Gesamtpaket (z. B. ein Docker-Image) weitergibt, muss die
Bedingungen dieser Abhängigkeit einhalten. Details und die Lizenzen aller
weiteren Komponenten: [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
