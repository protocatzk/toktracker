# Streamer-Gruppen

Gruppen bündeln mehrere Streamer zu einem gemeinsamen Analyse-Scope. Ein
Streamer kann Mitglied in beliebig vielen Gruppen sein (Many-to-Many).

## Verwaltung

Im Admin-Panel unter **Streamer-Gruppen**:

- Gruppe anlegen (Name, optionale Beschreibung, optionale Akzentfarbe).
- Streamer per Mehrfachauswahl zuordnen und speichern.
- Stammdaten bearbeiten oder Gruppe löschen (die Streamer selbst bleiben erhalten).

Benötigte Rechte: `streamers.manage`. Die Gruppenliste ist bereits mit
`analytics.view` lesbar (für die Scope-Auswahl in den Graphen).

## Wirkung

| Bereich | Verhalten |
| :--- | :--- |
| Graphen & Analytics | Die Scope-Auswahl bietet Gruppen als `group:<id>` an. KPIs, Timeline, Ranking, Tageszeit, Geschenke, Spender und Sessions werden auf die Mitglieder begrenzt. |
| Bot `/chart` | Der Picker listet Gruppen vor den Streamern. Direkt: `/chart gruppe:<name> [24h|7d|30d] [eur|coins] [ansicht]`. |
| Bot `/overview` | `/overview [heute|24h|7d|30d|all] gruppe:<name>` filtert KPIs und Top-Streamer. |
| Bot `/report` | `/report [stunden] gruppe:<name>` erzeugt den Bericht nur für die Gruppe. Der automatische 24h-Report bleibt bewusst global. |
| CSV-Exporte | `GET /api/export/gifts.csv?group_id=<id>` und `.../battles.csv?group_id=<id>`. |
| REST-API | `GET /api/analytics?group_id=…`, `GET /api/overview?group_id=…`. |

Ein gesetzter `streamer_id` hat Vorrang vor `group_id`. Eine Gruppe ohne
Mitglieder liefert bewusst leere Ergebnisse.

## REST-Endpunkte

```text
GET    /api/streamer-groups                     (analytics.view)
POST   /api/streamer-groups                     (streamers.manage)
PUT    /api/streamer-groups/{id}                (streamers.manage)
DELETE /api/streamer-groups/{id}                (streamers.manage)
PUT    /api/streamer-groups/{id}/members        (streamers.manage)
```

Alle Endpunkte sind zusätzlich unter `/api/v1/...` registriert.

## Caching

Gruppenänderungen invalidieren den Overview-/Chart-Cache und den Cache der
zusätzlichen Chart-Ansichten, damit Änderungen sofort sichtbar sind.
