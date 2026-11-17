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
/collage SELECT <ansichten> FROM <scope> WHERE <filter> GRID <raster> TITLE '<titel>'
```

Ohne Argumente oder mit `/collage help` zeigt der Bot die kompakte Hilfe mit
Beispielen aus der eigenen Instanz.

## SQL-Modus (empfohlen)

Die SQL-inspirierte Syntax wird vollständig auf die bestehenden sicheren
Kollagen-Parameter abgebildet. Es wird **kein SQL** an die Datenbank gesendet.

| Klausel | Bedeutung |
| :--- | :--- |
| `SELECT` | Chart-Ansichten / Kacheln |
| `FROM` | Streamer, Gruppe oder `ALL` |
| `WHERE` | Zeitraum und Metrik |
| `AS` | optionales Kachel-Label |
| `UNION ALL` | weitere Kacheln mit eigenem `FROM`/`WHERE` |
| `GRID` / `LAYOUT` | Raster, z. B. `2x2` (max. `3x3`) |
| `TITLE` | Kopfzeile |
| `REFRESH` | Caches umgehen |

### Scopes

```text
FROM @streamer
FROM STREAMER streamer
FROM GROUP "Team Name"
FROM gruppe:Team+Name
FROM ALL
```

### WHERE

```text
WHERE period=7d AND metric=eur
WHERE 7d AND eur
WHERE period = 7d UND metric = coins
```

Kurzform und deutsche Aliase (`UND`, `WO`, `VON`, `TITEL`, `RASTER`, `NEU`)
werden unterstützt.

### Beispiele

```text
/collage SELECT verlauf, streamer, tageszeit, geschenke FROM @alice WHERE 7d AND eur GRID 2x2 TITLE 'ALICE · 7T'
```

```text
/collage SELECT streamer, geschenke, spender FROM GROUP "Team Alpha" WHERE 30d AND coins
```

```text
/collage SELECT verlauf AS 'TOP 1' FROM @alice WHERE 24h AND eur UNION ALL SELECT verlauf AS 'TOP 2' FROM @bob WHERE 24h AND coins GRID 2x1
```

## Klassische Syntax

Die bisherige Syntax bleibt vollständig gültig:

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

## Schutzmechanismen

- maximal 9 Kacheln (`TELEGRAM_COLLAGE_MAX_TILES`, 1–9)
- Raster maximal `3x3`
- pro Nutzer gilt ein Cooldown (`TELEGRAM_COLLAGE_COOLDOWN_SECONDS`, Default 10)
- es läuft immer nur eine Kollage gleichzeitig pro Bot-Prozess
- Cache für fertige Kollagen: 5 Minuten (max. 32 Einträge)
