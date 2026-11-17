# Bot-Bilderkollagen (`/collage`)

`/collage` kombiniert mehrere Chart-Ansichten zu einem PNG. Die Einzelkacheln
werden weiterhin über `shared/chart_image.build_chart_image` gerendert und
nutzen damit dieselben Daten- und Bild-Caches wie `/chart`.

## Berechtigung

Der Befehl benötigt die Bot-Capability `bot.collage.render`
(`PERM_BOT_COLLAGE_RENDER`). Sie ist standardmäßig ausschließlich in der Rolle
`admin` enthalten. Über die Rechte-Matrix unter `/access` kann sie Admins
gezielt an einzelne Konten vergeben oder entzogen werden.

## Aufruf

```text
/collage [optionen] [kacheln]
```

Ohne Argumente oder mit `/collage help` zeigt der Bot die kompakte Hilfe.

### Globale Optionen

| Option | Bedeutung |
| :--- | :--- |
| `scope=@name` | Streamer-Scope |
| `scope=gruppe:Name` | Streamer-Gruppe (Leerzeichen als `+`) |
| `scope=all` | Globaler Scope |
| `period=today\|24h\|7d\|30d` | Zeitraum |
| `metric=eur\|coins` | Metrik |
| `layout=SPALTENxZEILEN` | Raster, z. B. `2x2` (max. `3x3`) |
| `views=...` | Komma-getrennte Kacheln |
| `title=...` | Optionaler Kopfzeilentitel |
| `refresh=1` | Caches für diese Kollage umgehen |

Positional werden `@streamer`, `gruppe:Name`, Zeitraum, Metrik und Layout
ebenfalls erkannt.

### Kachel-Syntax

```text
ansicht|scope|zeitraum|metrik|label=...
```

Nicht gesetzte Felder erben die globalen Optionen. Beispiel:

```text
/collage views="verlauf|@alice|24h|eur,streamer|@bob|7d|coins,geschenke|all|30d|eur|label=Q4"
```

## Beispiele

Die Beispiele unter `/collage help` werden dynamisch aus den tatsächlich
vorhandenen Streamern und Gruppen der Instanz erzeugt. Die folgenden Aufrufe
zeigen die Syntax unabhängig von konkreten Daten:

```text
/collage @alice 7d eur 2x2
/collage scope=gruppe:Team period=30d metric=coins views=verlauf,streamer,geschenke
/collage title="Wochenreport" views=verlauf,streamer,tageszeit,geschenke,spender
```

## Schutzmechanismen

- maximal 9 Kacheln (`TELEGRAM_COLLAGE_MAX_TILES`, 1–9)
- Raster maximal `3x3`
- pro Nutzer gilt ein Cooldown (`TELEGRAM_COLLAGE_COOLDOWN_SECONDS`, Default 10)
- es läuft immer nur eine Kollage gleichzeitig pro Bot-Prozess
- Cache für fertige Kollagen: 5 Minuten (max. 32 Einträge)
