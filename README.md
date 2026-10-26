# 🚀 TokTracker

<div align="center">

# 📊 TokTracker — Real-Time TikTok Live Analytics & Earnings Suite 🪙

**Verfolge TikTok-Livestreams, Diamanten, Einnahmen und Top-Spender in Echtzeit — vollautomatisiert, skalierbar und mit Telegram 2FA.**

---

<!-- Offizielle Tech & Status Badges -->
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Microservices-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![MariaDB](https://img.shields.io/badge/MariaDB-11-003545?style=for-the-badge&logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_&_2FA-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![TikTokLive](https://img.shields.io/badge/TikTokLive-WebSocket_Stream-FE2C55?style=for-the-badge&logo=tiktok&logoColor=white)](https://github.com/isaackogan/TikTokLive)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

<!-- Witzige Community & Projekt Badges -->
[![Fueled by Coffee](https://img.shields.io/badge/Fueled_by-☕_Kaffee_&_Schlafmangel-orange?style=for-the-badge)](#)
[![Money Printer](https://img.shields.io/badge/Money_Printer-BRRRRR_💸-brightgreen?style=for-the-badge)](#)
[![TikTok Drama](https://img.shields.io/badge/TikTok_Drama-100%25-red?style=for-the-badge)](#)
[![Coins Dropping](https://img.shields.io/badge/Coins-🪙_Rain_Incoming-gold?style=for-the-badge)](#)
[![Bugs](https://img.shields.io/badge/Bugs-Features_in_Disguise-blueviolet?style=for-the-badge)](#)

<br/>

[✨ Features](#-features) • [🏗 Architektur](#-architektur) • [⚡ Schnellstart](#-schnellstart-mit-docker) • [⚙️ Konfiguration](#️-konfiguration) • [🤖 Telegram Bot](#-telegram-bot--2fa) • [📊 Dashboard](#-dashboard--ui)

</div>

---

## 🌟 Was ist TokTracker?

**TokTracker** ist ein High-Performance Live-Monitoring-System für TikTok-Streams. Die Plattform fängt Geschenke, Viewer-Zahlen und Stream-Sessions in Echtzeit ab, rechnet Diamanten präzise in **Creator-Netto-Auszahlungen** und **Viewer-Brutto-Ausgaben** (EUR/USD) um und visualisiert alles in einem modernen Dark-Mode Dashboard.

Ob du Streamer analysieren willst, Wal-Spender (Whales) im **Donor-Radar** aufspüren möchtest oder per **Telegram-Bot** automatische 24h-Reports & 1-Klick-Logins erhalten willst: TokTracker hat dir den Rücken freigehalten.

---

## ✨ Features

- ⚡ **Echtzeit TikTokLive-Ingestion**: WebSocket-Verbindung mit automatischem Streak-/Combo-Watchdog und Reconnect-Supervisor.
- 💶 **Dual-Währungsrechner (EUR / USD)**:
  - **Netto-Creator-Auszahlung** (Diamonds ➔ USD ➔ EUR).
  - **Brutto-Viewer-Kaufwert** (Coins ➔ EUR mit Staffelpreisen & Rabatten).
- 🎯 **Donor-Radar & Spender-Spionage**: Verfolge Whales und Top-Gifter über mehrere Streamer hinweg.
- 🛡️ **Ultra-Secure Telegram 2FA**:
  - Kein Passwort-Stress: Login-Anfragen im Web-Dashboard landen direkt als Push-Notification mit **"Zulassen / Ablehnen"**-Buttons auf deinem Handy.
  - Alternativ mit 6-stelligem Fallback-PIN.
- 🤖 **Telegram-Bot Companion**:
  - Tägliche automatisierte 24h-Performance-Reports.
  - On-Demand Statusabfragen (`/report`, `/streamer <name>`, `/live`).
  - Streamer direkt im Chat starten/stoppen.
- 🌐 **Dual Web-Interface**:
  - **Admin-Dashboard (`/`)**: Volle Kontrolle, Streamer-Verwaltung, Live-Event-Logs, Chart.js Analysen, CSV-Export.
  - **Public Dashboard (`/public`)**: Öffentliche, read-only Rangliste für deine Community.
- 🐳 **Skalierbare Microservice-Architektur**:
  - Getrennte Docker-Container für Web (`app`), TikTok-Streamer-Daemon (`worker`) und Telegram (`bot`).
  - Uvicorn Multi-Worker Support für minimale Latenz (~100ms Response Time).
- 🔄 **Dual-Database Engine**:
  - MariaDB / MySQL 11 für den stabilen 24/7 Produktionsbetrieb.
  - SQLite für blitzschnelle lokale Entwicklung ohne externe Abhängigkeiten.
- 🔒 **Zero-Config SSL**: Integrierter Nginx Reverse Proxy mit automatischem Let's Encrypt Zertifikats-Handling (`acme-companion`).

---

## 🏗 Architektur

TokTracker ist als entkoppeltes Multi-Container-System aufgebaut, um auch bei dutzenden gleichzeitigen Livestreams maximale UI-Performance zu garantieren:

```
                                  ┌───────────────────────────┐
                                  │    TikTok Livestreams     │
                                  └─────────────┬─────────────┘
                                                │ WebSocket (Protobuf)
                                                ▼
┌───────────────────────────┐     ┌───────────────────────────┐
│       toktracker_bot      │     │     toktracker_worker     │
│   (Telegram Bot & 2FA)    │     │   (TikTokLive & Ingestion)│
│       Port: 5002          │     │        Port: 5001         │
└─────────────┬─────────────┘     └─────────────┬─────────────┘
              │                                 │
              │         MariaDB 11              │
              └───────────────► ┌───────────────┴───────────┐
                                │       toktracker_db       │
              ┌───────────────► │    (Ereignisse, Sessions, │
              │                 │      Settings, Users)     │
┌─────────────┴─────────────┐   └───────────────────────────┘
│       toktracker_app      │
│     (FastAPI Web + API)   │
│         Port: 5000        │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│      toktracker_nginx     │◄──── Let's Encrypt (toktracker_ssl)
│    (Nginx Reverse Proxy)  │
│      Ports: 80 / 443      │
└───────────────────────────┘
              │
              ▼
   🌍 Öffentliches Internet (HTTPS)
```

---

## ⚡ Schnellstart mit Docker

### 1. Repository klonen

```bash
git clone https://github.com/protocatzk/toktracker.git
cd toktracker
```

### 2. Konfiguration anlegen

Kopiere die Vorlage und trage deine Zugangsdaten ein:

```bash
cp .env.example .env
nano .env
```

> **Wichtig:** Setze mindestens deinen `DOMAIN_NAME`, `SSL_EMAIL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` und sichere Datenbank-Passwörter.

### 3. Container starten

```bash
docker compose up -d --build
```

Fertig! Dein Dashboard ist nach wenigen Sekunden unter `https://deinedomain.de` mit automatischem SSL-Zertifikat online. 🚀

---

## ⚙️ Konfiguration (.env)

| Variable | Beschreibung | Standard / Beispiel |
| :--- | :--- | :--- |
| `DOMAIN_NAME` | Deine Domain für Nginx Reverse Proxy & SSL | `tracker.deinedomain.de` |
| `SSL_EMAIL` | E-Mail-Adresse für Let's Encrypt Zertifikate | `admin@deinedomain.de` |
| `DB_ENGINE` | Datenbank-Typ (`mysql` oder `sqlite`) | `mysql` |
| `MYSQL_DATABASE` | MariaDB Datenbankname | `toktracker` |
| `MYSQL_USER` | MariaDB Benutzer | `toktracker_user` |
| `MYSQL_PASSWORD` | MariaDB Passwort | `dein_geheimes_passwort` |
| `TIKTOK_SESSION_ID` | Eigene TikTok Session-ID (optional, umgeht Captchas) | `your_session_id` |
| `TIKTOK_SIGN_API_KEY`| EulerStream Signing Key (für hohe Abfrageraten) | `dein_eulerstream_key` |
| `TELEGRAM_BOT_TOKEN` | BotFather Token für Benachrichtigungen & 2FA | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | Ziel-Chat/Gruppe für 24h-Reports | `-100123456789` |
| `TELEGRAM_ALLOWED_USERS`| Whitelist für 2FA & Bot-Admins (IDs oder @usernames) | `123456789,@mein_user` |

---

## 🤖 Telegram Bot & 2FA

TokTracker verwandelt dein Smartphone in ein Admin-Cockpit:

### 🔐 1-Click 2FA Login
1. Öffne `/login` im Web-Browser.
2. Der Bot sendet dir sofort eine Push-Nachricht mit zwei Buttons:
   - `[ ✅ Zulassen ]`
   - `[ ❌ Ablehnen ]`
3. Ein Klick auf **"Zulassen"** loggt dich im Browser automatisch ein!

### 💬 Wichtige Bot-Befehle
| Befehl | Aktion |
| :--- | :--- |
| `/start` | Begrüßung & Status deines Telegram-Accounts |
| `/report` | Manueller Einnahmen-Report aller Streamer (Heute / 24h) |
| `/streamer <name>` | Detaillierte Live-Statistik eines Streamers abfragen |
| `/live` | Schnelle Übersicht aller aktuell aktiven Livestreams |
| `/track <name>` | Streamer zur Überwachung hinzufügen |
| `/untrack <name>`| Überwachung für Streamer pausieren |

---

## 📊 Dashboard & UI

### 🖥️ Admin-Panel (`/`)
- **Live-Kennzahlen**: Gesamt-Einnahmen (€/$), Brutto-Viewer-Ausgaben, Diamanten & aktive Viewer.
- **Streamer-Grid**: Schnelles Umschalten zwischen Streamern mit Live-Badge, Viewer-Graph und Diamanten-Zähler.
- **Donor Radar**: Wer sind die Top-Gifter? Erkennung von Walen und automatische Zuordnung.
- **Live Gift Feed**: Reale Geschenke flattern in Echtzeit mit Animationen ins Log.
- **CSV-Export**: Buchhaltung leicht gemacht mit 1-Klick-Export für Steuer und Statistiken.

### 👥 Public Leaderboard (`/public`)
- Schlanke, elegante und mobile-optimierte Rangliste.
- Kein Login erforderlich.
- Perfekt für Moderatoren, Community-Mitglieder oder Partner.

---

## 🛠️ Lokale Entwicklung (ohne Docker)

TokTracker unterstützt auch den direkten Betrieb mit lokaler SQLite-Datenbank:

```bash
# 1. Virtuelle Umgebung erstellen & aktivieren
python -m venv .venv
source .venv/bin/activate  # Unter Windows: .\.venv\Scripts\Activate.ps1

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. .env auf SQLite einstellen
echo "DB_ENGINE=sqlite" >> .env

# 4. Server starten
uvicorn app:app --host 127.0.0.1 --port 5000 --reload
```

---

## 🚢 Service Management (Docker)

```bash
# Logs in Echtzeit ansehen (alle Services)
docker compose logs -f

# Logs eines bestimmten Services ansehen
docker compose logs -f worker   # TikTok-Streaming Logs
docker compose logs -f bot      # Telegram-Bot Logs
docker compose logs -f app      # FastAPI Web Logs

# Einzelnen Service neustarten
docker compose restart worker

# Status aller Container prüfen
docker compose ps
```

---

## 🤝 Contributing & License

Pull Requests sind herzlich willkommen! Bei größeren Änderungen öffne bitte zuerst ein Issue, um die Ideen zu diskutieren.

Entwickelt mit ❤️, ☕ und ein bisschen TikTok-Drama.

Lizenziert unter der [MIT License](LICENSE).

<div align="center">
<sub>TokTracker is an independent open-source project and is not affiliated, associated, authorized, endorsed by, or in any way officially connected with TikTok, ByteDance, or any of their subsidiaries.</sub>
</div>
