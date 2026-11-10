# TT-INTELLIGENCE – Design-System & Styling Guide

Dieser Guide beschreibt, wie Seiten und Komponenten im TT-INTELLIGENCE-Frontend
aussehen und gebaut werden. Er ist die verbindliche Referenz für neue Seiten und
für Änderungen an bestehenden Ansichten.

**Source of Truth ist [`static/brand.css`](../static/brand.css).** Tokens und
Komponenten werden dort gepflegt. Dieser Guide erklärt die Verwendung, dupliziert
aber keine vollständigen Token-Tabellen.

---

## 1. Designprinzipien

TT-INTELLIGENCE ist **modern-industrial**, nicht verspielt:

- **Harte Kanten:** Radien maximal `2px`; Kreise nur für Status-Punkte.
- **Dünne Rahmen:** `1px`-Linien strukturieren Flächen, `2px` markieren
  Primärflächen oder aktive Zustände.
- **Mono-Labels:** Kennzahlen, Metadaten, Eyebrows und Status laufen in
  JetBrains Mono, Fließtext in Inter.
- **Klare Hierarchie:** Eine Hauptaktion pro Bereich, ruhige Sekundäraktionen.
- **Ein grüner Akzent:** `--accent` ist die primäre Markenfarbe. Modul-Farben
  sind nur dezente Kennfarben.
- **Flach statt glänzend:** Keine Verläufe, keine Glows, keine großen Schatten.
- **Dichte vor Dekoration:** Informationen und Abstände tragen das Layout,
  nicht Effekte.

### Modul-Kennfarben

| Modul | Token | Einsatz |
| :--- | :--- | :--- |
| Standard / Aktionen | `--accent` | Primärbuttons, aktive Tabs, Live-Status |
| Spender-Radar | `--module-radar` | KPI-Oberkanten, Radar-Tags, Whale-Hinweise |
| Chat-Intelligence | `--module-chat` | KPI-Oberkanten, Wortwolke, Chat-Tags |
| Web-Analytics | `--module-analytics` | KPI-Oberkanten, Charts, Analytics-Tags |
| Zugriff & Rollen | `--module-access` | Access-Karten, Rollen-Tags |

Kennfarben nie flächig einsetzen. Erlaubt sind Oberkanten, Rahmen, kleine
Badges und einzelne Akzenttexte.

---

## 2. Tokens

Die wichtigsten Token-Gruppen in `brand.css`:

```css
--bg, --surface, --surface-2, --surface-3, --surface-hover
--border, --border-subtle, --border-strong, --border-input
--text, --text-strong, --muted, --inverse
--accent, --warn, --danger, --info
--module-radar, --module-chat, --module-analytics, --module-access
--sans, --mono
--space-1 … --space-7
--radius-sm, --radius-md, --radius-lg
--line, --line-subtle, --line-strong
--shadow-sm, --shadow-md
--wrap
--chart-1 … --chart-5, --chart-grid
```

Ältere Seiten-CSS-Dateien verwenden weiterhin die Legacy-Aliase
(`--bg-surface`, `--border-color`, `--text-muted`, …). Diese werden in
`brand.css` auf die neuen Tokens gemappt und sollen bei Gelegenheit ersetzt
werden.

**Regel:** Keine hardcodierten Hex-Farben in Seiten-CSS oder Templates, außer
für Canvas-/Chart-Fallbacks, die keine CSS-Variablen auflösen können.

---

## 3. Typografie

| Rolle | Font | Größe / Stil |
| :--- | :--- | :--- |
| Fließtext | Inter | `13.5px`, `line-height: 1.5` |
| Seiten-/Panel-Titel | JetBrains Mono | `12–13px`, uppercase, `letter-spacing` |
| Kennzahlen | JetBrains Mono | `21–26px`, `700`, tabular nums |
| Eyebrow | JetBrains Mono | `10px`, uppercase, `letter-spacing: 1.4px` |
| Metadaten / Pills | JetBrains Mono | `9.5–10.5px`, uppercase |
| Buttons | JetBrains Mono | `10.5px`, uppercase |

- Zahlen in Tabellen und KPIs immer mit `font-variant-numeric: tabular-nums`.
- Lange IDs, Hex-Werte und Zeitstempel in `.mono`.
- Keine zusätzlichen Font-Familien einführen. Inter und JetBrains Mono werden
  lokal aus `static/fonts/` geladen.

---

## 4. Layout & Responsive

- Standardbreite: `--wrap` (`1360px`).
- Hauptinhalt: `<main class="container">` oder eine modulspezifische
  Container-Klasse mit denselben Paddings.
- Abstände über `--space-*`, nicht über Magic Numbers.
- Breakpoints:
  - `1100px`: breite Split-Layouts einspaltig
  - `900px`: Header/Navigation umbrechen
  - `768px`: Tabellen und Toolbars kompakter
  - `640px`: mobile Karten, einspaltige KPIs
  - `480px`: Brand-Subtitle ausblenden, kleinste Schriftstufe

Mobile Tabellen immer in `.table-wrap` oder `.table-responsive` kapseln, damit
horizontal gescrollt werden kann.

---

## 5. Shell: Header, Navigation, Footer

Jede App-Seite erbt von `base.html`. `brand.css` wird dort global geladen;
Seiten-CSS kommt danach.

### Header-Macro

```jinja
{% from "partials/app_header.html" import app_header with context %}

{% call app_header('MEIN MODUL', 'KURZE · MONO · UNTERZEILE', 'analytics', 'mein-modul', 'analytics') %}
    <span class="pill">Rolle: <strong>{{ role }}</strong></span>
    <span class="pill">Status: <strong>AKTIV</strong></span>
{% endcall %}
```

Parameter:

| Parameter | Bedeutung |
| :--- | :--- |
| `mode` | Text im Mode-Tag, z. B. `ADMIN CONSOLE` |
| `subtitle` | Mono-Unterzeile |
| `module` | `default`, `public`, `radar`, `chat`, `analytics`, `access` |
| `href` | Ziel des Brand-Links |
| `active` | aktiver Navigationspunkt |

Der Caller-Block enthält die seitenspezifischen Status-Pills. Die Navigation
selbst wird zentral im Macro gerendert und respektiert `is_admin` sowie
`permissions`.

### Footer

```jinja
{% include "partials/footer.html" %}
```

Der Footer enthält Marke, Version/Tagline, Modul-Links und – wenn eine Session
existiert – den Logout-Link.

### Eigene Header vermeiden

Neue Seiten bringen **keinen eigenen Header-Markup** mit. Ausnahmen sind nur
bewusst eigenständige Oberflächen wie Landingpage, Mini-App oder eine
Login-/Locked-Seite.

---

## 6. Komponenten

### Panels und Boxen

```html
<section class="box">
    <div class="box-header">
        <h2>Bereich</h2>
        <span class="mono muted">Meta</span>
    </div>
    …
</section>
```

- `.box` / `.panel`: Standardfläche mit Oberkante.
- `.box-header`: Titelzeile mit Trennlinie.
- `.panel-title`: Mono-Titel innerhalb einer Custom-Komponente.
- `.eyebrow`: `// 01 / BEREICH`.
- `.section-hint`: erklärender Hilfetext.

### KPI-Karten

```html
<div class="kpi-grid">
    <div class="kpi-card analytics">
        <span class="kpi-label">Views</span>
        <strong class="kpi-value">12.480</strong>
        <span class="kpi-sub">+4,2 % zum Vortag</span>
    </div>
</div>
```

Modulklassen: `.accent`, `.radar`, `.chat`, `.analytics`.

### Buttons

| Klasse | Einsatz |
| :--- | :--- |
| `.btn` | Standardaktion |
| `.btn.primary` | eine Hauptaktion pro Bereich |
| `.btn.danger` | destruktive Aktion |
| `.btn.ghost` | ruhige Tertiäraktion |
| `.btn.sm` | kompakte Toolbar |
| `.btn-link` | Navigation/Inline-Aktion in Kopfzeilen |
| `.btn-link.primary` | hervorgehobener Navigationslink |

Buttons sind eckig, Mono, uppercase. Keine Icons ohne Textlabel.

### Navigation & Tabs

- Hauptnavigation: zentrales Macro, nicht pro Seite duplizieren.
- Bereichsnavigation: `.nav-bar` + `.tab-list` + `.tab-btn`.
- Aktiver Tab: `.tab-btn.active` (grüne Unterkante).
- Zähler: `.tab-badge`.

### Tabellen

```html
<div class="table-wrap">
    <table>
        <thead>…</thead>
        <tbody>…</tbody>
    </table>
</div>
```

- Kopfzeile sticky, Mono, uppercase.
- Zahlen rechtsbündig mit `.num` / `.num-col`.
- Zeilen-Hover über Tokens, keine eigenen Farben.

### Formulare

- Labels in `.field-group` mit Mono-Label.
- `.form-grid` für Raster, `.inline-form` für kompakte Zeilen.
- Inputs/Selects nutzen die globalen Styles aus `brand.css`.
- Fokus immer sichtbar (`:focus-visible` oder `border-color` + Soft-Ring).
- Validierungsfehler semantisch mit `--danger`, nie nur über Farbe allein:
  zusätzlich Text oder Icon.

### Badges, Tags, Status

- `.badge` / `.tag`: neutrale Kennzeichnung.
- `.accent`, `.radar`, `.chat`, `.analytics`, `.danger`: semantische Varianten.
- `.status-dot` für Live-/Offline-/Warn-Zustände.
- `.pill` für kompakte Statusleisten im Header.

### Empty States, Toasts, Modals

- Leere Zustände: `.empty-state` mit klarer nächster Aktion.
- Toasts: `.toast` bzw. modulspezifische Toast-Klassen, rechts unten.
- Modals: eigener Overlay + `.modal-content-box` / `.insp-modal-content`;
  Fokusführung und `aria-modal` nicht vergessen.

---

## 7. Dark- und Light-Mode

- Dark ist der primäre Modus.
- Light wird über `[data-theme="light"]` in `brand.css` vollständig unterstützt.
- Theme-Schalter: `data-theme-toggle` am Button; `common.js` übernimmt
  Umschaltung, Label und `localStorage`.
- Keine `prefers-color-scheme`-Sonderlogik in Seiten-CSS.
- Jede neue Seite muss in beiden Modi geprüft werden.
- Die Mini-App bleibt bewusst dark-only.

---

## 8. Icons und Emojis

Emojis sind erlaubt und Teil der Oberfläche. Regeln:

- Immer mit Textlabel kombinieren, nie als einzige Bedeutung.
- Einheitlich über `<span class="icon" aria-hidden="true">…</span>` ausrichten.
- Nicht als Ersatz für semantische Statusfarben verwenden.
- Keine externen Icon-Bibliotheken einführen.

---

## 9. Accessibility

- Fokuszustände nie entfernen.
- Kontraste in Dark und Light prüfen.
- Klickziele mindestens `32px` hoch.
- Status nicht nur über Farbe transportieren.
- `aria-label` für icon-only Buttons und Navigationen.
- `prefers-reduced-motion` respektieren (global in `brand.css`).
- Skip-Link auf Seiten mit umfangreicher Navigation.

---

## 10. Neue Seite: Checkliste

1. Template erbt von `base.html`.
2. Header-Macro `app_header` importieren und korrekt konfigurieren.
3. Footer-Partial einbinden.
4. Seiten-CSS separat anlegen und mit Versionsquery laden:
   ```jinja
   {% block head %}
       <link rel="stylesheet" href="static/meine-seite.css?v=1.0.0" />
   {% endblock %}
   ```
5. Ausschließlich Tokens und vorhandene Komponenten verwenden.
6. Keine Inline-Styles, keine Gradients, keine hardcodierten Farben.
7. Dark und Light prüfen.
8. Responsive bei `360`, `768`, `1024` und `1440` px prüfen.
9. Keine sichtbaren Legacy-Namen (`toktracker`, `TokTracker`); technische
   Identifier bleiben unverändert.
10. Tests laufen lassen:
    ```bash
    ./run_tests.sh
    ```
11. Bei CSS-/JS-Änderungen die `?v=`-Version in den Templates erhöhen.

### Skelett

```jinja
{% extends "base.html" %}
{% from "partials/app_header.html" import app_header with context %}

{% block title %}{{ brand_name }} – Mein Modul{% endblock %}

{% block head %}
    <link rel="stylesheet" href="static/mein-modul.css?v=1.0.0" />
{% endblock %}

{% block content %}
{% call app_header('MEIN MODUL', 'KURZE · MONO · UNTERZEILE', 'analytics', 'mein-modul', 'stats') %}
    <span class="pill">Rolle: <strong>{{ role }}</strong></span>
{% endcall %}

<main class="container">
    <section class="box">
        <div class="box-header">
            <h2>Übersicht</h2>
        </div>
        <div class="kpi-grid">
            <div class="kpi-card analytics">
                <span class="kpi-label">Kennzahl</span>
                <strong class="kpi-value">0</strong>
                <span class="kpi-sub">Beschreibung</span>
            </div>
        </div>
    </section>
</main>

{% include "partials/footer.html" %}
{% endblock %}
```

---

## 11. Anti-Patterns

| Nicht verwenden | Stattdessen |
| :--- | :--- |
| `style="..."` im Template | CSS-Klasse in der Seiten-CSS |
| `border-radius: 12px` | `var(--radius-md)` oder `0` |
| `linear-gradient(...)` | flache `--surface-*` / Modul-Soft-Farbe |
| `box-shadow: 0 0 20px #a855f7` | kein Glow; höchstens `var(--shadow-md)` |
| `#0d1117`, `#f0f6fc`, `#a855f7` | passende Tokens |
| eigener Header-Markup | `app_header`-Macro |
| eigene Farbschemata pro Modul | eine Modul-Kennfarbe |
| Emoji ohne Text | Emoji + Label |
| `TokTracker` im sichtbaren UI | `brand_name` / `brand_wordmark` |
| neue Font-Familie | Inter / JetBrains Mono |

---

## 12. Tests und Absicherung

Relevante Guards:

- [`tests/test_branding.py`](../tests/test_branding.py): Markenkonstanten,
  `brand.css`, Light-Tokens, lokale Fonts, keine sichtbaren Legacy-Namen,
  Nutzung des gemeinsamen Headers.
- [`tests/test_frontend_assets.py`](../tests/test_frontend_assets.py): alle
  Templates erben von `base.html`, referenzierte Assets existieren, keine
  Inline-`<style>`-Blöcke, Chart-Lib nur einmal pro Seite.
- [`tests/test_base_path.py`](../tests/test_base_path.py): Betrieb unter
  `/track`.

Neue Seiten sollten mindestens durch `test_frontend_assets.py` und
`test_branding.py` abgedeckt sein.

---

## 13. Änderungen am Design-System

Wenn ein neues Token oder eine neue Kernkomponente nötig ist:

1. Zuerst prüfen, ob eine bestehende Komponente erweitert werden kann.
2. Token/Komponente in `brand.css` ergänzen – nicht in einer Seiten-CSS.
3. Dark- und Light-Werte definieren.
4. Legacy-Alias nur ergänzen, wenn bestehende Seiten ihn benötigen.
5. Guide und ggf. `AGENTS.md` aktualisieren.
6. Tests erweitern, wenn die Änderung verbindlich abgesichert werden soll.

Ziel ist eine kleine, stabile Bibliothek aus Tokens und Primitiven – keine
Sammlung einseitiger Sonderlösungen.
