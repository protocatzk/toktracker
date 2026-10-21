# Telegram Bot Bilder & Beschreibungen (@BotFather Vorlagen)

In diesem Ordner (`/pictures`) liegen alle Grafiken für deinen **TikTok Live Earnings Tracker** Telegram-Bot:

1. **`welcome_banner.jpg` (16:9)**
   - **Verwendung:** Welcome-Banner bei `/start` & `/help` (wird automatisch von `telegram_service.py` mitgesendet) sowie als **Description Picture** in `@BotFather` (`/setdescriptionpic` – Hinweis: BotFather akzeptiert dort 640x360 px / 16:9).
2. **`bot_avatar.jpg` (1:1)**
   - **Verwendung:** Profilbild / Avatar des Bots in `@BotFather` (`/setuserpic`).
3. **`daily_report_banner.jpg` (16:9)**
   - **Verwendung:** Header-Grafik für den automatischen **24h Streamer Analytics Report** und `/report` (wird von `telegram_service.py` als Bild-Header genutzt).

---

## 1. Bot-Name (`/setname` in @BotFather)
```text
TikTok Live Earnings Tracker 📊
```

---

## 2. Kurzbeschreibung / About-Text (`/setabouttext` in @BotFather – max. 120 Zeichen)
*(Erscheint in der Profil-Info des Bots und beim Teilen des Bot-Links)*
```text
📊 Echtzeit TikTok-Live Einnahmen-Tracker: Coins, Diamonds, EUR/USD-Payouts & automatische 24h-Streamer-Berichte.
```

---

## 3. Welcome-Beschreibung / „What can this bot do?“ (`/setdescription` in @BotFather – max. 512 Zeichen)
*(Erscheint gemeinsam mit `welcome_banner.jpg` im leeren Chat-Fenster, noch bevor der Nutzer auf „Starten“ klickt)*
```text
Willkommen beim TikTok Live Earnings Tracker! 🚀💎

Dieser Bot überwacht TikTok-Livestreams in Echtzeit und wertet alle empfangenen Geschenke (Coins & Diamonds) präzise in EUR (€) und USD ($) aus.

✨ Features:
• 🕒 Automatischer 24h-Gesamtbericht aller Streamer
• 🔍 Einzelabfragen pro Streamer (@username)
• 💰 Netto Creator-Payout & Brutto Shop-Kaufwert
• 🎁 Top-Geschenke, Top-Spender (Gifter) & Peak-Zuschauer

👇 Klicke unten auf „Starten“ (/start), um das Hauptmenü zu öffnen!
```

---

## 4. Befehlsliste für das Telegram-Menü (`/setcommands` in @BotFather)
*(Einfach komplett kopieren und bei `@BotFather` nach `/setcommands` einfügen)*
```text
start - Hauptmenü & Befehlsübersicht öffnen
report - 24h-Gesamtbericht aller überwachten Streamer abrufen
streamer - Einzelabfrage für einen Streamer (z.B. /streamer arbrita.a)
status - Laufzeit-Status aller aktiven TikTokLive-Worker prüfen
id - Eigene Telegram-ID & Berechtigungsstatus anzeigen
help - Hilfe & verfügbare Befehle anzeigen
add - [Admin] Streamer hinzufügen & Live-Worker starten
track - [Admin] Live-Überwachung für einen Streamer starten
stop - [Admin] Live-Überwachung für einen Streamer stoppen
allow - [Admin] Nutzer für den Bot freischalten (ID oder @username)
revoke - [Admin] Nutzer-Berechtigung entziehen / sperren
users - [Admin] Freigeschaltete Nutzer & offene Anfragen auflisten
mode - [Admin] Zugriffsmodus wechseln (whitelist oder public)
```
