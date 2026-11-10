/*!
 * TT-INTELLIGENCE - gemeinsame Frontend-Helfer.
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

    /**
     * Liefert den konfigurierten Unterpfad (z.B. "/track") ohne trailing slash.
     * Basis ist das <base href="...">-Tag, das der Server pro Request setzt.
     */
    function appBasePath() {
        var base = document.querySelector("base");
        if (!base) return "";
        try {
            var path = new URL(base.href, window.location.href).pathname || "/";
            path = path.replace(/\/+$/, "");
            return path === "/" ? "" : path;
        } catch (e) {
            return "";
        }
    }

    /** Aktueller App-Pfad inkl. Query, aber ohne einen gesetzten Unterpfad. */
    function currentAppPath() {
        var path = window.location.pathname || "/";
        var base = appBasePath();
        if (base && (path === base || path.indexOf(base + "/") === 0)) {
            path = path.slice(base.length) || "/";
        }
        return path + (window.location.search || "");
    }

    /**
     * Macht einen serverseitig gelieferten absoluten Pfad (z.B. "/admin")
     * relativ zum <base>-Tag. So funktioniert die App sowohl unter "/" als
     * auch unter einem Unterpfad wie "/track". Ein bereits enthaltener
     * Unterpfad wird entfernt, damit er nicht doppelt angehängt wird.
     */
    function appUrl(path) {
        if (!path) return path;
        var value = String(path);
        if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(value) || value.charAt(0) === "#") {
            return value;
        }
        var base = appBasePath();
        if (base && (value === base || value.indexOf(base + "/") === 0)) {
            value = value.slice(base.length) || "/";
        }
        return value.replace(/^\/+/, "");
    }

    /**
     * Baut eine Login-URL, die nach erfolgreicher Anmeldung zum aktuellen
     * (oder einem explizit übergebenen) App-Pfad zurückspringt.
     */
    function loginUrl(nextPath) {
        return "login?next=" + encodeURIComponent(nextPath || currentAppPath());
    }

    /** Setzt das Theme und aktualisiert vorhandene Theme-Schalter. */
    function applyTheme(theme) {
        var normalized = theme === "light" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", normalized);
        try {
            localStorage.setItem("toktracker_theme", normalized);
        } catch (e) {}
        var label = normalized === "dark" ? "Theme: DARK" : "Theme: LIGHT";
        var btn = document.getElementById("btnThemeToggle");
        if (btn) btn.textContent = label;
        var toggles = document.querySelectorAll("[data-theme-toggle]");
        for (var i = 0; i < toggles.length; i += 1) {
            toggles[i].textContent = label;
        }
        var meta = document.getElementById("metaThemeColor");
        if (meta) meta.setAttribute("content", normalized === "light" ? "#f2f5f8" : "#0b0e13");
    }

    /** Einheitlicher Theme-Schalter für alle Seiten (data-theme-toggle). */
    document.addEventListener("click", function (event) {
        var target = event.target.closest ? event.target.closest("[data-theme-toggle]") : null;
        if (!target) return;
        var current = document.documentElement.getAttribute("data-theme") || "dark";
        applyTheme(current === "dark" ? "light" : "dark");
    });

    document.addEventListener("DOMContentLoaded", function () {
        var current = document.documentElement.getAttribute("data-theme") || "dark";
        applyTheme(current);
    });

    global.escapeHtml = escapeHtml;
    global.fmtEUR = fmtEUR;
    global.fmtUSD = fmtUSD;
    global.fmtNum = fmtNum;
    global.applyTheme = applyTheme;
    global.appBasePath = appBasePath;
    global.currentAppPath = currentAppPath;
    global.appUrl = appUrl;
    global.loginUrl = loginUrl;
})(window);
