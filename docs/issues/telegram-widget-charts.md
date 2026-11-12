# Telegram HTML-Widget-Charts für Einnahmen, Radar & Live-Reports

**GitHub-Issue:** [#14](https://github.com/protocatzk/toktracker/issues/14)
**Status:** Phase A umgesetzt · Phasen B/C geplant (blockiert durch Telegram-Rollout)
**Bereich:** Telegram-Bot, Analytics
**Bot-API:** 10.4 (HTML-Widgets, veröffentlicht am 09.11.2026)
**Labels:** `enhancement`, `telegram`, `analytics`

---

## Kontext

Telegram hat mit **Bot API 10.4** „HTML Widgets“ eingeführt: kleine, interaktive
HTML-Dokumente direkt in der Message-Bubble. Sie laufen in einer **QuickJS-Sandbox**
auf dem Gerät, haben **keinen Netzwerkzugriff** und werden von der Telegram-App
mit dem Chat-Theme gerendert. Für Graphen ist das deutlich attraktiver als PNGs:
native Farben, Dark/Light, Tap-Interaktion und stille In-Place-Updates.

### Harte Grenzen (bestimmen das Design)

| Limit | Wert | Konsequenz |
|---|---|---|
| HTML | 32.768 Bytes | Template muss kompakt bleiben |
| HTML komprimiert | 4.096 Bytes (zlib-9) | keine Libraries, kein Chart.js |
| Code-Änderung | nicht möglich | HTML ist generischer Renderer, Daten liegen im State |
| `chat_data` / `public_data` | je 1.024 Bytes | Werte kompakt als uint16-Base64 |
| Request-/Antwort-Daten | 64 / 1.024 Bytes | nur für Detailabfragen sinnvoll |
| Produktions-Rollout | **nur Privatchat** | Gruppen/Inline/Forwards = Testserver-only |
| Canvas/SVG | vorhanden | Linien, Flächen, Balken, Text möglich |
| Kein Netzwerk | `fetch` etc. werfen | keine externen Daten/Libs |
| Kein Scrollen | Bubble 50–600 px hoch | Chart muss in ~230 px passen |

### Warum kein Chart.js / kein Bild

- Externe `<script src>` werden nicht geladen, Libraries sind nicht gebündelt.
- Server-gerenderte PNGs würden eine neue Bild-Pipeline (z. B. Pillow/Matplotlib)
  und mehr Container-Größe bedeuten.
- Ein eigener SVG-Renderer ist ~1,8 KB komprimiert und damit weit unter dem Limit.

---

## Umsetzungsstand

### Phase A – Privatchat-Chart (umgesetzt)

**Ziel:** `/chart` sendet im Privatchat ein interaktives Einnahmen-Widget mit
Zeitraum- und Metrik-Umschaltung; überall sonst ein sauberer Text-Fallback.

Umgesetzt:

- `shared/widget_chart.py`
  - **serverseitig gerendertes SVG** (kein JS-DOM-Rendering); die Grafik ist
    auch sichtbar, wenn die Widget-Sandbox JS/DOM einschränkt
  - Telegram-Theme-Variablen, deutsche Formatierung (`format_eur`,
    `format_coins`), Zeitlabels und Peak-Marker
  - optionale Progressive Enhancement: Tap auf den Chart zeigt den Bucket-Wert
  - Größenprüfung gegen 32 KB / 4 KB (`ensure_widget_limits`)
- `shared/db/analytics.py`
  - neue leichte `get_chart_timeline()`-Query (nur `gift_events`) mit
    optionalem Streamer-Filter und Kurzzeit-Cache: 30 s für Today/24h,
    2–5 Minuten für 7d/30d
  - Cache wird bei Revenue-/Migrationsänderungen über
    `invalidate_overview_cache()` mit geleert
- `telegram_service.py`
  - neuer Befehl `/chart [@streamer] [today|24h|7d|30d] [eur|coins]`
    (Aliase: `charts`, `graph`, `diagramm`); ohne Streamer global,
    mit `@username` auf einen Streamer gefiltert
  - Widget-Versand über `bot.do_api_request("sendWidget", …)`, weil PTB 22.8
    die Bot-API-10.4-Methoden noch nicht kennt
  - sofortige Chat-Action (`upload_photo`) als Lade-Feedback
  - Inline-Keyboard mit Zeitraum-, Metrik-, Refresh-, „📺 STREAMER“- und
    „🌐 ALLE“-Buttons
  - paginierter Streamer-Picker (8 Streamer pro Seite, ◀️/▶️, Abbrechen);
    Auswahl sendet den Streamer-Chart und räumt Picker + alten Chart auf
  - Callback `chart_view:<period>:<metric>:<refresh>` sendet ein neues Widget
    und löscht das alte (Widget-HTML ist unveränderlich; `chat_data` wird nicht
    benötigt)
  - **Fallback:** in Gruppen/Channels, bei deaktiviertem Feature-Flag oder bei
    API-Fehlern werden die Kennzahlen als Text gesendet
- `shared/permissions.py`
  - `chart` → `bot.analytics.view` (keine neue Capability nötig)
- `shared/config.py` + `.env.example`
  - `TELEGRAM_WIDGET_CHARTS=1` (Default an, per Env abschaltbar)
- `tests/test_widget_chart.py`
  - Größenbudgets, Offline-/Library-Freiheit, serverseitiges SVG,
    Theme-Nutzung, alle Zeiträume, leere Zeitreihe, Label-Escaping

**Bewusst nicht enthalten:**

- keine `allow_queries` / `widget_query`-Verarbeitung
- kein Gruppen-/Inline-/Forward-Versand
- kein Chart im automatischen 24h-Report (Zielchat ist in Produktion meist eine Gruppe)
- keine Balkendiagramme / Radar-Charts
- kein `chat_data`-State und kein `editMessageWidgetData` im Phase-A-Flow

**Akzeptanzkriterien (erfüllt):**

- `/chart` funktioniert im Privatchat und zeigt 24h/7d/30d/heute.
- `/chart @streamer` filtert die Zeitreihe auf einen Streamer; ein
  „🌐 ALLE“-Button führt zurück zur Gesamtansicht.
- Der „📺 STREAMER“-Button öffnet einen paginierten Picker (8 pro Seite);
  Auswahl und Abbruch funktionieren ohne Chat-Müll (Picker wird gelöscht).
- Periode und Metrik lassen sich über Buttons umschalten (neues Widget,
  altes wird entfernt).
- Das Chart ist auch ohne funktionierendes Widget-JS sichtbar (SVG im HTML).
- In Gruppen erscheint ein verständlicher Text statt eines Fehlers.
- Bei API-Fehlern bricht der Befehl nicht ab.
- Widget-HTML bleibt unter 4.096 Bytes komprimiert.
- Die Datenabfrage liegt nach dem Umbau bei ~0,3–2 s statt 22–55 s.
- `pytest`/`unittest` der Bot-, Config- und Widget-Tests ist grün.

---

## Geplante Phasen

### Phase B – Detail-Taps im Chart (`widget_query`)

**Nutzen:** Tap auf einen Datenpunkt fragt serverseitig Details ab, z. B.
„Top-Gift dieser Stunde“, „Spender mit dem größten Anteil“ oder
„Streamer-Breakdown des Tages“.

**Umsetzung:**

1. Widget mit `allow_queries=True` senden.
2. `TelegramWidget.request('bucket:14')` im Tap-Handler des Renderers.
3. Bot-seitig `widget_query`-Updates verarbeiten:
   - PTB 22.8 kennt den Update-Typ nicht; er landet in `update.api_kwargs`.
   - `TypeHandler(Update, …)` als Catch-all registrieren.
   - `allowed_updates` beim Polling um `widget_query` und
     `shared_widget_query` erweitern (sonst filtert PTB sie weg).
4. Antwort mit `answerWidgetQuery` (max. 1.024 Bytes) und/oder stilles
   `editMessageWidgetData` für den sichtbaren Zustand.
5. Rate-Limits beachten: 5 Requests / 5 s / User+Bot, 15 s Antwortzeit,
   ein Request gleichzeitig.

**Risiken:** Mehr bewegliche Teile im Update-Pfad; ohne sorgfältige Tests
können unbekannte Updates verloren gehen. Deshalb erst nach Phase A und mit
eigenen Tests für `api_kwargs`/`TypeHandler`.

### Phase C – Gruppen, Shared Widgets & Live-Ticker

**Blockiert durch Telegram:** In Produktion sind Widgets derzeit nur im
Privatchat verfügbar. Gruppen, Inline-Modus und Forwards funktionieren nur auf
dem Testserver.

**Umsetzung, sobald freigegeben:**

1. Chat-Typ prüfen (`private`, `group`, `supergroup`) und Gruppen freischalten.
2. `is_shared=True` für einen zentralen Chart nutzen:
   - ein Widget-Objekt, viele Nachrichten (auch via `sendSharedWidget`)
   - `public_data` enthält die gemeinsam genutzte Zeitreihe
   - `editSharedWidgetData` mit `cache_time` (5–3600 s, max. 1 Edit/s)
3. `watchPublicData()` im Renderer, damit sichtbare Widgets den Live-Ticker
   automatisch aktualisieren.
4. Chart an den automatischen 24h-Report anhängen, **wenn** der Zielchat ein
   Privatchat ist; sonst beim Text bleiben.
5. Optional: Inline-Modus (`InputSharedWidgetMessageContent`) für `/chart` in
   beliebigen Chats.

**Voraussetzung:** Testserver-Bot-Token (`TELEGRAM_TEST_ENV`) und ein
gesonderter Testchat, damit Experimente nicht in Produktionsgruppen landen.

### Phase D – Weitere Chart-Typen

- Top-Streamer als horizontale Balken (CSS-Balken, kein SVG nötig)
- Spender-Radar (Whale/Shark/Dolphin-Verteilung)
- Gift-Verteilung (Top-Geschenke)
- Zuschauer-/Peak-Verlauf pro Session (sofern eine Zeitreihe verfügbar ist)

Alle Typen können denselben Renderer erweitern; der Chart-Typ steckt im
`chat_data`-Feld (`k`), das HTML bleibt unverändert.

---

## Technische Notizen

### PTB-Kompatibilität

- Installiert: `python-telegram-bot==22.8`; `send_widget` existiert dort nicht.
- `Bot.do_api_request(endpoint, api_kwargs=…)` ist der offizielle PTB-Weg für
  neue Methoden und gibt das rohe `result` zurück.
- `Update.ALL_TYPES` enthält `widget_query` nicht. Für Phase A unkritisch, weil
  keine Queries genutzt werden. Für Phase B zwingend erweitern.

### Datenfluss Phase A

```text
/chart @streamer 7d coins
  → get_chart_timeline(period="7d", streamer_id=…)   # leicht, gecacht
  → timeline (EUR net / Coins) + totals
  → serverseitiges SVG + Labels
  → sendWidget(html, caption, height, reply_markup)
  → Callback chart_view:<streamer_id>:30d:eur:0
  → build_chart_widget() (Cache)
  → sendWidget(neues Chart) + deleteMessage(altes Chart)
```

Zusätzlich öffnet der Button „📺 STREAMER“ den Picker über
`chart_pick:<period>:<metric>`. Die Seitenwechsel laufen über
`chart_page:<page>:<period>:<metric>:<chart_id>`, die Auswahl über
`chart_stream:<streamer_id>:<period>:<metric>:<chart_id>`; danach werden
Picker und altes Chart gelöscht.

Die normale `get_analytics_data()`-Aggregation wird für Charts **nicht** mehr
verwendet: Sie berechnet zusätzlich Top-Spender, Sessions, Streamer-Rankings
und braucht auf Produktionsdaten 22 s (24h) bis 55 s (30d). Die neue
`get_chart_timeline()` aggregiert nur `gift_events` und liegt bei 0,3–2 s
(cold) bzw. ~0 s (Cache-Hit).

### Sicherheit & Datenschutz

- Keine Secrets, Tokens oder Nutzernamen im Widget-HTML.
- Labels stammen aus DB-generierten Zeitbucket-Labels, keine freien
  Nutzereingaben; sie werden HTML-escaped.
- Caption ist immer gesetzt und enthält Summe + Peak (Notifications, Suche,
  Clients ohne Widget-Support).
- Widgets sind nicht kopierbar/forwardbar (Produktion).

### Betrieb

- `TELEGRAM_WIDGET_CHARTS=0` deaktiviert den Widget-Pfad sofort; `/chart`
  antwortet dann mit einem Hinweis.
- Fehler werden geloggt (`Chart-Widget fehlgeschlagen: …`) und führen zum
  Text-Fallback, nie zu einem stillen Verlust der Antwort.
- Der Chart-Cache läuft per TTL aus (30 s für Today/24h, 2–5 Minuten für
  7d/30d); der 🔄-Button erzwingt mit `force_refresh` frische Daten. Bei
  Revenue-Profil-/Migrationsänderungen wird er über
  `invalidate_overview_cache()` mit geleert.
- Jeder Perioden-/Metrikwechsel sendet eine neue Widget-Nachricht und löscht
  die alte. Das zählt als gesendete Nachricht, ist aber durch die
  Cache-Trefferquote selten und schnell.

---

## Offene Fragen

1. Soll der 24h-Report künftig automatisch einen Chart enthalten, sobald
   Gruppen-Widgets in Produktion verfügbar sind?
2. Welche Detailansicht ist für Phase B am wertvollsten: Top-Gift pro Stunde,
   Top-Spender pro Tag oder Streamer-Breakdown?
3. Sollen die Chart-Farben stärker an `brand.css` angelehnt werden, obwohl
   Widgets nur die Telegram-Theme-Variablen zuverlässig auflösen?
4. Brauchen wir einen separaten Testserver-Bot für Phase C?

---

## Referenzen

- Bot API Changelog 10.4: <https://core.telegram.org/bots/api-changelog>
- Widgets-Guide: <https://core.telegram.org/bots/widgets>
- `sendWidget`: <https://core.telegram.org/bots/api/methods/sendwidget>
- `editMessageWidgetData`: <https://core.telegram.org/bots/api/methods/editmessagewidgetdata>
- Projekt: `shared/widget_chart.py`, `telegram_service.py`, `tests/test_widget_chart.py`
