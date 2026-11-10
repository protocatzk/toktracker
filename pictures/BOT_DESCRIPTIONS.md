# TT-INTELLIGENCE – Bot-Assets & @BotFather-Vorlagen

Alle Grafiken liegen in `/pictures` und werden im Industrial-Look der
Startseite gehalten: `#0d1117`-Hintergrund, feines Raster, Mono-Typografie,
harte Kanten und ein einzelner grüner Akzent (`#3fb950`).

1. **`welcome_banner.jpg` (16:9, 1280×720)**
   - Verwendung: `/start` & `/help` sowie als Description-Picture in
     `@BotFather` (`/setdescriptionpic`, empfohlen 640×360 px / 16:9).
2. **`bot_avatar.jpg` (1:1, 1024×1024)**
   - Verwendung: Profilbild des Bots (`/setuserpic`).
3. **`daily_report_banner.jpg` (16:9, 1280×720)**
   - Verwendung: Header des automatischen 24h-Reports und `/report`.

---

## 1. Bot-Name (`/setname`)

```text
TT-INTELLIGENCE
```

---

## 2. Kurzbeschreibung (`/setabouttext`, max. 120 Zeichen)

```text
Live Earnings Intelligence: TikTok-Geschenke, Coins, Zuschauer und Netto-Payouts in Echtzeit.
```

---

## 3. Welcome-Beschreibung (`/setdescription`, max. 512 Zeichen)

```text
TT-INTELLIGENCE überwacht TikTok-Livestreams in Echtzeit.

// GESCHENKE · COINS · ZUSCHAUER
// NETTO-PAYOUTS IN EUR & USD
// 24H-REPORTS · SPENDER-RADAR · MINI-APP

Starte mit /start das Hauptmenü.
```

---

## 4. Befehlsliste (`/setcommands`)

```text
start - Hauptmenü & Befehlsübersicht
overview - Finanz-Dashboard (Heute, 24h, 7d, 30d, Gesamt)
radar - Spender-Radar nach Tiers
whales - Ticker der neuesten Großspenden
donor - Spender-Dossier & Stammkanal (<username>)
vip - VIP-Watchlist anzeigen oder Spender markieren
loyalty - Frontenwechsler & Streamer-Überschneidungen
streamers - Alle Kanäle mit Live-Status
gifts - Gift-Ticker der letzten Geschenke
streamer - Einzelabfrage für einen Streamer (<username>)
report - Gesamtbericht aller überwachten Streamer
status - Laufzeit-Status der TikTokLive-Worker
app - Mini-App: Live-Matches & Einnahmen
id - Eigene Telegram-ID, Gruppen-ID & Berechtigung
login - [Admin] Einmal-Code für das Web-Panel
add - [Admin] Streamer anlegen & Live-Worker starten
track - [Admin] Live-Überwachung starten
stop - [Admin] Live-Überwachung stoppen
allow - [Admin] Nutzer freischalten
revoke - [Admin] Nutzer-Berechtigung entziehen
users - [Admin] Nutzer & offene Anfragen auflisten
mode - [Admin] Zugriffsmodus (whitelist | public)
alert - [Admin] Live-Alert in diesem Chat verwalten
```

---

## Gestaltungsregeln der Bot-Texte

- Eyebrow: `// TT-INTELLIGENCE · 01 / TITEL` in `<code>`.
- Kennzahlen: ausgerichtete `<pre>`-Tabelle, Breite ≤ 34 Zeichen.
- Menü-Kategorien und Buttons: ein Emoji als Icon (📊 🎯 🐋 🏆 ⚙️ …).
- Status: farbige Emojis für bessere Sichtbarkeit — `🟢 LIVE` / `⚪ OFFLINE`,
  `✅` freigeschaltet, `⏳` wartend, `🚫` gesperrt, `🟡` verbindet/Backoff,
  `🔴` Fehler.
- Trenner: `────────────────────────`.
- Footer: `TT-I · TT.MM.JJJJ HH:MM`.
- Keine Emoji-Ketten; maximal ein Icon pro Zeile/Button.
