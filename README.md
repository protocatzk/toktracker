# TokTracker

**TikTok Live Earnings Tracker** – erfasst TikTok-Livestreams in Echtzeit, berechnet Brutto-/Netto-Einnahmen in USD und EUR, visualisiert sie in einem Web-Dashboard und liefert Reports über einen Telegram-Bot.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![MariaDB](https://img.shields.io/badge/MariaDB-11-003545?logo=mariadb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)

---

## Funktionsumfang

| Bereich | Funktionen |
| :--- | :--- |
| **Live-Tracking** | Geschenke (Coins/Diamonds) in Echtzeit, Combo-/Streak-Aggregation, Zuschauerzahlen, Stream-Sessions, Battle-Erkennung (1v1, 2v2, 1v1v1, 1v1v1v1) |
| **Finanzen** | Brutto-Kaufwert (Zuschauer) und Netto-Auszahlung (Creator) in USD und EUR, konfigurierbare Kurse, Periodenfilter (today/24h/7d/30d/all) |
| **Web-Oberfläche** | Öffentliches Read-Only-Panel (`/`), Admin-Dashboard (`/admin`), Analytics (`/site-analytics`), Spender-Radar (`/donor-radar`), Chat-Intelligence (`/chat-intelligence`), Telegram Mini-App (`/app`) |
| **Telegram-Bot** | 24h-Reports, Streamer-Statistiken, Live-Status, Whitelist-Verwaltung, Login per Telegram-Widget/OTP |
| **Sicherheit** | HMAC-signierte Sessions, Telegram-Signaturprüfung, Whitelist/Rollen, Rate-Limiting auf Auth-Endpunkten, Datenschutz-Maskierung auf öffentlichen Flächen |
| **Betrieb** | Microservices mit Redis-Bus, horizontales Ingest-Sharding über Leases, Leader-Locks, Healthchecks, Docker-Compose mit Nginx + Let's Encrypt |

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

---

## Sicherheit & Datenschutz

- Admin-Zugriff nur über Telegram-Login (Widget/OTP) oder API-Key; Sessions sind HMAC-signiert und `HttpOnly`/`Secure` (hinter HTTPS).
- Auth-Endpunkte sind rate-limitiert; Login-Challenges werden nach 5 Fehlversuchen gesperrt.
- Rollen: `admin` (voller Zugriff) vs. `user` (Whitelist: Radar und Chat-Intelligence).
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

Die Tests laufen gegen eine temporäre SQLite-Datenbank (`tests/_bootstrap.py`) und berühren niemals Produktionsdaten. CI: `.github/workflows/ci.yml` (Ruff, Mypy, Pytest mit Redis-Service).

---

## Lizenz

Privates Projekt – alle Rechte vorbehalten.
