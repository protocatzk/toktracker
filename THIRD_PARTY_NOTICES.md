# Drittkomponenten & Lizenzen

Der **eigene Quellcode** dieses Projekts steht unter der [MIT-Lizenz](./LICENSE).
Dieses Dokument listet die Lizenzbedingungen der mitgelieferten bzw. benötigten
Drittkomponenten auf, damit Weitergabe und Betrieb rechtlich nachvollziehbar sind.

> **Kurzfassung:** Der eigene Code ist MIT. Die Kernabhängigkeit **TikTokLive
> steht jedoch unter AGPL-3.0** — wer ein daraus gebautes Gesamtpaket (z. B. ein
> Docker-Image) weitergibt, muss die AGPL-Bedingungen dieser Abhängigkeit
> einhalten. Der eigene Betrieb des Dienstes ist davon nicht betroffen, solange
> der Quellcode öffentlich verfügbar ist.

---

## 1. Maßgebliche Abhängigkeit: TikTokLive (AGPL-3.0)

| | |
| :--- | :--- |
| Paket | `TikTokLive` 7.0.1 |
| Lizenz | GNU Affero General Public License v3.0 (AGPL-3.0) |
| Quelle | https://github.com/isaackogan/TikTokLive |

`tiktok_service.py` bindet die Bibliothek per `import` ein; das Backend ist ohne
sie nicht funktionsfähig.

**Was das bedeutet:**

- **Eigener Betrieb (SaaS):** AGPL §13 verlangt, dass Nutzer eines Netzdienstes
  den Quellcode der AGPL-Komponenten erhalten können. Da dieses Repository
  öffentlich ist und TikTokLive öffentlich verfügbar ist, ist das erfüllt.
- **Weitergabe des Repositories:** Unproblematisch, solange die AGPL-Hinweise
  erhalten bleiben und die Bibliothek nicht verändert eingebettet wird.
- **Weitergabe als Docker-Image / Gesamtpaket:** Das Image enthält TikTokLive
  (beim Build via `pip install`), gilt also als Distribution eines
  kombinierten Werks. Die AGPL verlangt dann, dass der Quellcode des
  Gesamtwerks unter AGPL-kompatiblen Bedingungen verfügbar ist. Wer das
  Projekt so weitergibt, muss diese Bedingungen selbst erfüllen.
- **Änderungen an TikTokLive:** Falls die Bibliothek gepatcht wird (siehe
  Route-Patching in `tiktok_service.py`), sind die Änderungen nach AGPL §5
  offenzulegen.

Die MIT-Lizenz dieses Projekts erstreckt sich **nicht** auf TikTokLive und
schränkt deren Bedingungen nicht ein.

---

## 2. Python-Laufzeitabhängigkeiten

Alle Versionen sind in [`requirements.txt`](./requirements.txt) gepinnt.

| Paket | Lizenz | Hinweis |
| :--- | :--- | :--- |
| FastAPI | MIT | |
| Uvicorn | BSD-3-Clause | |
| Jinja2 | BSD-3-Clause | |
| HTTPX | BSD-3-Clause | |
| python-dotenv | BSD-3-Clause | |
| PyMySQL | MIT | |
| cryptography | Apache-2.0 **oder** BSD-3-Clause | Doppellizenz, Wahlrecht bei Nutzung |
| uvloop | MIT | nur auf Nicht-Windows-Systemen |
| redis (Python-Client) | MIT | |
| **python-telegram-bot** | **LGPL-3.0** | Wird als unveränderte Abhängigkeit genutzt. Bei Weitergabe eines Images muss der Empfänger die Bibliothek austauschen können (Quelle: https://github.com/python-telegram-bot/python-telegram-bot) |
| **TikTokLive** | **AGPL-3.0** | siehe Abschnitt 1 |

## 3. Eingebundene Frontend-Assets

| Asset | Lizenz |
| :--- | :--- |
| `static/chart.umd.min.js` (Chart.js 4.4.7) | MIT — Lizenzbanner ist in der Datei enthalten (`(c) 2024 Chart.js Contributors`) |
| `static/*.js`, `static/*.css`, `templates/*` | MIT (eigenes Projekt) |

Ein JavaScript-Build gibt es nicht; alle Assets werden unverändert ausgeliefert.

## 4. Infrastruktur-Images (Docker-Compose)

Diese Images werden nicht weitergegeben, sondern beim Deployment bezogen.
Die Lizenzangaben gelten für den jeweiligen Container.

| Image | Lizenz | Hinweis |
| :--- | :--- | :--- |
| `mariadb:11` | GPL-2.0 | Datenbank, separater Prozess |
| `redis:7-alpine` | ab 7.4: RSALv2 / SSPLv1 (source-available) | **Hinweis:** Redis ≤ 7.2.4 war BSD-3-Clause. Der Tag `7-alpine` liefert inzwischen 7.4+. Wer eine rein OSI-konforme Lizenzkette braucht, pinnt `redis:7.2-alpine` (BSD-3, aber ohne aktuelle Sicherheitsupdates) oder wechselt auf Valkey. |
| `nginxproxy/nginx-proxy:alpine` | MIT | |
| `nginxproxy/acme-companion:latest` | MIT | |
| `tecnativa/docker-socket-proxy:0.2` | Apache-2.0 | nur lesende Docker-API |

## 5. Marken und Inhalte

- Die MIT-Lizenz gewährt **keine Rechte an Namen oder Logos** („TokTracker",
  „toktracker"), weder ausdrücklich noch stillschweigend.
- Dieses Projekt ist **nicht mit TikTok, ByteDance oder verbundenen Unternehmen
  verbunden** und wird von diesen nicht unterstützt. „TikTok" ist eine Marke der
  jeweiligen Inhaber.
- Es werden keine TikTok-Inhalte, Geschenk-Kataloge oder Nutzerdaten
  mitgeliefert. Alle angezeigten Daten entstehen zur Laufzeit aus öffentlichen
  Live-Streams.

## 6. Lizenztexte selbst einsehen

```bash
# Python-Paket
pip show -f <paketname>            # Lizenzfeld + Dateien
python -c "import importlib.metadata as m; print(m.metadata('<paket>')['License'])"

# Im Container installierte Lizenzdateien
docker run --rm toktrackerapp-app sh -c \
  'cat /usr/local/lib/python3.11/site-packages/<paket>-*.dist-info/licenses/LICENSE*'

# Docker-Image
docker image inspect <image> --format '{{index .Config.Labels "org.opencontainers.image.licenses"}}'
```

---

*Stand: 2026-10-27. Bei Änderungen an Abhängigkeiten (siehe `requirements.txt`)
sollte diese Übersicht mitgepflegt werden.*
