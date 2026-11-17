# Coverage-Baseline

Stand: 2026-11-16, nach dem Router-Split (`routers/revenue.py`, `exports.py`,
`system.py`, `access.py`).

## Aufruf

```bash
pip install -r requirements-dev.txt
pytest --cov=shared --cov=app --cov=routers \
       --cov=telegram_service --cov=tiktok_service --cov-report=term
```

`pytest-cov` ist seit diesem Stand Teil von `requirements-dev.txt`. Coverage ist
**kein CI-Gate**: Die Zahlen dienen als Entscheidungshilfe, wo Tests fehlen.

## Kennzahlen

| Modul | Statements | Coverage | Einordnung |
| :--- | ---: | ---: | :--- |
| `shared/access_gate.py` | 25 | 100 % | vollständig |
| `shared/api_deps.py` | 67 | 94 % | neu, Auth-Pfade gut abgedeckt |
| `shared/permissions.py` | 131 | 84 % | Matrix + Overrides getestet |
| `shared/db/analytics.py` | 407 | 85 % | Kernaggregate getestet |
| `shared/db/groups.py` | 158 | 85 % | Gruppen-Scope getestet |
| `routers/exports.py` | 50 | 94 % | CSV-Pfade getestet |
| `routers/access.py` | 81 | 78 % | Rechte-Endpunkte getestet |
| `routers/revenue.py` | 37 | 32 % | Zuordnung/Bearbeitung ungetestet |
| `routers/system.py` | 67 | 42 % | Demo-Endpunkte ungetestet |
| `app.py` | 1219 | 56 % | Legacy-Shell, sinkt mit jedem Router |
| `shared/db/_base.py` | 179 | 45 % | Pool-Pfade brauchen einen Stub-Test |
| `shared/db/battles.py` | 283 | 43 % | Detail-/Timeline-Abfragen offen |
| `shared/db/schema.py` | 197 | 42 % | DDL läuft nur beim Bootstrap |
| `shared/db/donors.py` | 360 | 19 % | CRM, Whale-Alerts, Loyalty |
| `shared/db/chat.py` | 228 | 19 % | Chat-Intelligence-Abfragen |
| `telegram_service.py` | 1825 | 22 % | **größte Lücke** |
| `tiktok_service.py` | 1545 | 31 % | **zweitgrößte Lücke** |
| **Gesamt** | **9888** | **50 %** | |

Die Vermutung aus der Codebasis-Prüfung bestätigt sich: Die beiden
Monolith-Dateien mit dem meisten Code haben die niedrigste Abdeckung.

## Nächste sinnvolle Testziele

1. **`telegram_service.py` – Formatierung & Befehle** (rein, ohne Netzwerk):
   `bot_format`-Ausgaben, Report-Formatter, Berechtigungs-Auflösung pro Befehl.
   Die Handler sind über `BOT_COMMAND_PERMISSIONS` bereits strukturell geprüft;
   fehlt nur die Ausgabe-/Randfall-Abdeckung.
2. **`tiktok_service.py` – Streak-Aggregation**: `on_gift`/`_streak_watchdog_loop`
   mit Fake-Events, ohne echte WebSocket-Verbindung.
3. **`routers/revenue.py` + `routers/system.py`**: ein Test je Endpunkt
   (Zuordnung, ungültige IDs, Demo-Seed/-Clear).
4. **`shared/db/_base.py`**: MySQL-Pool mit gestubbtem `pymysql`, damit
   Timeout-/Reconnect-Pfade nicht nur in Produktion laufen.
5. **`shared/db/_base.py`**: Verbindungsaufbau/Paramstyle-Bindung als Unit-Test.

Nicht sinnvoll ist es, die Coverage-Zahl um ihrer selbst willen zu heben:
Die 50 % enthalten viele Admin-/Legacy-Pfade, die nur mit erhöhtem
Fixture-Aufwand erreichbar wären.
