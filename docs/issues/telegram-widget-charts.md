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
  - statischer SVG-Renderer (`WIDGET_HTML`) mit Telegram-Theme-Variablen
  - kompakte uint16-Base64-Kodierung der Zeitreihe (`encode_series`)
  - `chat_data`-State inkl. Labels, Summe, Peak und Metrik
  - Größenprüfung gegen 32 KB / 4 KB / 1 KB (`ensure_widget_limits`)
  - deutsche Formatierung (`format_eur`, `format_coins`)
- `telegram_service.py`
  - neuer Befehl `/chart [today|24h|7d|30d] [eur|coins]` (Aliase: `charts`,
    `graph`, `diagramm`)
  - Widget-Versand über `bot.do_api_request("sendWidget", …)`, weil PTB 22.8
    die Bot-API-10.4-Methoden noch nicht kennt
  - Inline-Keyboard mit Zeitraum-, Metrik- und Refresh-Buttons
  - Callback `chart_view:<period>:<metric>` aktualisiert das Widget still über
    `editMessageWidgetData` + `edit_message_reply_markup`
  - **Fallback:** in Gruppen/Channels, bei deaktiviertem Feature-Flag oder bei
    API-Fehlern werden die Kennzahlen als Text gesendet
- `shared/permissions.py`
  - `chart` → `bot.analytics.view` (keine neue Capability nötig)
- `shared/config.py` + `.env.example`
  - `TELEGRAM_WIDGET_CHARTS=1` (Default an, per Env abschaltbar)
- `tests/test_widget_chart.py`
  - Größenbudgets, Offline-/Library-Freiheit, Theme-Nutzung, Encoder-Roundtrip,
    State-Limit, alle Zeiträume, leere Zeitreihe

**Bewusst nicht enthalten:**

- keine `allow_queries` / `widget_query`-Verarbeitung
- kein Gruppen-/Inline-/Forward-Versand
- kein Chart im automatischen 24h-Report (Zielchat ist in Produktion meist eine Gruppe)
- keine Balkendiagramme / Radar-Charts

**Akzeptanzkriterien (erfüllt):**

- `/chart` funktioniert im Privatchat und zeigt 24h/7d/30d/heute.
- Periode und Metrik lassen sich ohne neue Nachricht umschalten.
- In Gruppen erscheint ein verständlicher Text statt eines Fehlers.
- Bei API-Fehlern bricht der Befehl nicht ab.
- Widget-HTML bleibt unter 4.096 Bytes komprimiert; State unter 1.024 Bytes.
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
/chart 7d coins
  → get_analytics_data(period="7d")
  → timeline (EUR net / Coins) + totals
  → encode_series() → uint16-Base64
  → chat_data (JSON, < 1 KB)
  → sendWidget(html=WIDGET_HTML, caption, height, reply_markup)
  → Callback chart_view:30d:eur
  → build_chart_widget()
  → editMessageWidgetData(chat_data=…)
```

### Sicherheit & Datenschutz

- Keine Secrets, Tokens oder Nutzernamen im Widget-HTML oder State.
- Labels stammen aus DB-generierten Zeitbucket-Labels, keine freien
  Nutzereingaben.
- Caption ist immer gesetzt (Notifications, Suche, Clients ohne Widget-Support).
- Widgets sind nicht kopierbar/forwardbar (Produktion), State ist öffentlich
  behandelbar.

### Betrieb

- `TELEGRAM_WIDGET_CHARTS=0` deaktiviert den Widget-Pfad sofort; `/chart`
  antwortet dann mit einem Hinweis.
- Fehler werden geloggt (`Chart-Widget fehlgeschlagen: …`) und führen zum
  Text-Fallback, nie zu einem stillen Verlust der Antwort.
- `editMessageWidgetData` zählt als gesendete Nachricht; im Phase-A-Flow
  entsteht nur bei Button-Klicks ein Edit.

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
