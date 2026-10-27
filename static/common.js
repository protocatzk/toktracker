/*!
 * TokTracker - gemeinsame Frontend-Helfer.
 *
 * Wird in allen Seiten im <head> geladen und stellt die Funktionen global bereit,
 * damit die bestehenden Seiten-Skripte (Vanilla JS, kein Build-Step) sie nutzen
 * können. Vorher waren escapeHtml/fmtEUR/fmtUSD/fmtNum/applyTheme in bis zu
 * sechs Dateien dupliziert.
 */
(function (global) {
    "use strict";

    /**
     * Escaped einen Wert für die Einbettung in HTML-Text oder Attribute.
     * Bewusst defensiv (auch einfache Anführungszeichen), da die Seiten viele
     * Werte in Templates-Strings innerhalb von Attributen rendern.
     */
    function escapeHtml(value) {
        if (!value) return "";
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function fmtEUR(value) {
        return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(value || 0);
    }

    function fmtUSD(value) {
        return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value || 0);
    }

    /** Ganzzahl-Formatierung (de-DE); rundet, damit auch Fließkomma-Reste sauber aussehen. */
    function fmtNum(value) {
        return new Intl.NumberFormat("de-DE").format(Math.round(value || 0));
    }

    /** Setzt das Theme und aktualisiert einen vorhandenen Theme-Button. */
    function applyTheme(theme) {
        var normalized = theme === "light" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", normalized);
        try {
            localStorage.setItem("toktracker_theme", normalized);
        } catch (e) {}
        var btn = document.getElementById("btnThemeToggle");
        if (btn) {
            btn.textContent = normalized === "dark" ? "Theme: DARK" : "Theme: LIGHT";
        }
    }

    global.escapeHtml = escapeHtml;
    global.fmtEUR = fmtEUR;
    global.fmtUSD = fmtUSD;
    global.fmtNum = fmtNum;
    global.applyTheme = applyTheme;
})(window);
