/*
 * TokTracker – Zugriff, Whitelist & Rollen (/access).
 *
 * Die Seite nutzt ausschliesslich die bestehenden, serverseitig durch
 * users.manage geschuetzten API-Endpunkte. Die Rechte-Matrix selbst ist
 * statisch und wird in shared/permissions.py gepflegt.
 */
(function () {
    "use strict";

    var state = {
        users: [],
        accessMode: "whitelist",
    };

    var ROLE_LABELS = {
        viewer: "Gast / Zuschauer",
        user: "Nutzer / Mitglied",
        moderator: "Moderator",
        admin: "Administrator",
    };

    function el(id) {
        return document.getElementById(id);
    }

    function esc(value) {
        return window.escapeHtml ? window.escapeHtml(value) : String(value == null ? "" : value);
    }

    function showToast(message, isError) {
        var node = el("accessToast");
        if (!node) return;
        node.textContent = message;
        node.classList.toggle("error", !!isError);
        node.classList.add("show");
        window.clearTimeout(showToast._timer);
        showToast._timer = window.setTimeout(function () {
            node.classList.remove("show");
        }, 3500);
    }

    async function fetchJSON(url, options) {
        var opts = options || {};
        var headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
        var res = await fetch(url, Object.assign({}, opts, { headers: headers }));
        if (res.status === 401) {
            window.location.href = "login?next=/access";
            throw new Error("Nicht angemeldet");
        }
        var data = null;
        try {
            data = await res.json();
        } catch (ignore) {
            data = null;
        }
        if (!res.ok) {
            var detail = data && data.detail ? data.detail : "HTTP " + res.status;
            throw new Error(detail);
        }
        return data;
    }

    function roleOptions(currentRole) {
        return Object.keys(ROLE_LABELS)
            .map(function (role) {
                var selected = role === currentRole ? " selected" : "";
                return '<option value="' + role + '"' + selected + ">" + esc(ROLE_LABELS[role]) + "</option>";
            })
            .join("");
    }

    function identOf(user) {
        if (user.telegram_id) return String(user.telegram_id);
        if (user.username) return "@" + user.username;
        return String(user.id);
    }

    function userCell(user) {
        var username = user.username ? "@" + user.username : "wird bei Nachricht verknüpft";
        var name = user.first_name ? ' <span class="muted">(' + esc(user.first_name) + ")</span>" : "";
        return "<strong>" + esc(username) + "</strong>" + name;
    }

    function idCell(user) {
        return user.telegram_id
            ? '<span class="mono">' + esc(user.telegram_id) + "</span>"
            : '<span class="muted">–</span>';
    }

    function lastSeenCell(user) {
        var value = (user.last_seen_at || "").replace("T", " ");
        return value ? '<span class="mono muted">' + esc(value) + "</span>" : '<span class="muted">–</span>';
    }

    function noteCell(user) {
        return '<span class="mono muted">' + esc(user.note || "–") + "</span>";
    }

    function partitionUsers() {
        return {
            pending: state.users.filter(function (u) {
                return parseInt(u.is_allowed, 10) === 0;
            }),
            allowed: state.users.filter(function (u) {
                return parseInt(u.is_allowed, 10) === 1;
            }),
            blocked: state.users.filter(function (u) {
                return parseInt(u.is_allowed, 10) < 0;
            }),
        };
    }

    function renderPending(rows) {
        var tbody = el("accessPendingBody");
        var meta = el("accessPendingMeta");
        if (meta) meta.textContent = rows.length + " Einträge";
        if (!tbody) return;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="access-empty">Keine offenen Anfragen.</td></tr>';
            return;
        }
        tbody.innerHTML = rows
            .map(function (u) {
                var ident = esc(identOf(u));
                var status = state.accessMode === "public" ? "PUBLIC-GAST" : "ANFRAGE OFFEN";
                return (
                    "<tr>" +
                    "<td>" + idCell(u) + "</td>" +
                    "<td>" + userCell(u) + "</td>" +
                    '<td><span class="status-tag polling">' + status + "</span><br>" + noteCell(u) + "</td>" +
                    "<td>" + lastSeenCell(u) + "</td>" +
                    '<td><div class="action-group">' +
                    '<select class="sm" data-role-select="true" aria-label="Rolle">' + roleOptions(u.role || "user") + "</select>" +
                    '<button type="button" class="sm primary" data-action="approve" data-ident="' + ident + '">Freischalten</button>' +
                    '<button type="button" class="sm danger" data-action="block" data-ident="' + ident + '">Ablehnen</button>' +
                    "</div></td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function renderAllowed(rows) {
        var tbody = el("accessAllowedBody");
        var meta = el("accessAllowedMeta");
        if (meta) meta.textContent = rows.length + " Einträge";
        if (!tbody) return;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="access-empty">Noch niemand freigeschaltet.</td></tr>';
            return;
        }
        tbody.innerHTML = rows
            .map(function (u) {
                var ident = esc(identOf(u));
                return (
                    "<tr>" +
                    "<td>" + idCell(u) + "</td>" +
                    "<td>" + userCell(u) + "</td>" +
                    '<td><select class="sm" data-action="role" data-ident="' + ident + '" aria-label="Rolle ändern">' + roleOptions(u.role || "viewer") + "</select></td>" +
                    '<td><span class="status-tag live">FREIGESCHALTET</span></td>' +
                    "<td>" + noteCell(u) + "</td>" +
                    "<td>" + lastSeenCell(u) + "</td>" +
                    '<td><div class="action-group">' +
                    '<button type="button" class="sm danger" data-action="block" data-ident="' + ident + '">Sperren</button>' +
                    '<button type="button" class="sm" data-action="delete" data-id="' + esc(u.id) + '">Entfernen</button>' +
                    "</div></td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function renderBlocked(rows) {
        var tbody = el("accessBlockedBody");
        var meta = el("accessBlockedMeta");
        if (meta) meta.textContent = rows.length + " Einträge";
        if (!tbody) return;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="access-empty">Keine gesperrten Nutzer.</td></tr>';
            return;
        }
        tbody.innerHTML = rows
            .map(function (u) {
                var ident = esc(identOf(u));
                return (
                    "<tr>" +
                    "<td>" + idCell(u) + "</td>" +
                    "<td>" + userCell(u) + "</td>" +
                    "<td>" + esc(ROLE_LABELS[u.role] || u.role || "–") + "</td>" +
                    "<td>" + noteCell(u) + "</td>" +
                    '<td><div class="action-group">' +
                    '<button type="button" class="sm primary" data-action="unblock" data-ident="' + ident + '" data-role="' + esc(u.role || "user") + '">Entsperren</button>' +
                    '<button type="button" class="sm" data-action="delete" data-id="' + esc(u.id) + '">Entfernen</button>' +
                    "</div></td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function renderCounters(parts) {
        var adminCount = state.users.filter(function (u) {
            return parseInt(u.is_allowed, 10) === 1 && u.role === "admin";
        }).length;
        if (el("accessPendingCount")) el("accessPendingCount").textContent = parts.pending.length;
        if (el("accessAllowedCount")) el("accessAllowedCount").textContent = parts.allowed.length;
        if (el("accessBlockedCount")) el("accessBlockedCount").textContent = parts.blocked.length;
        if (el("accessAdminCount")) el("accessAdminCount").textContent = adminCount;
    }

    function renderMode() {
        var pill = el("accessModePill");
        var badge = el("accessModeBadge");
        var select = el("accessModeSelect");
        if (pill) pill.textContent = state.accessMode.toUpperCase();
        if (badge) {
            badge.textContent = state.accessMode.toUpperCase();
            badge.className = "status-tag " + (state.accessMode === "public" ? "polling" : "live");
        }
        if (select && document.activeElement !== select) select.value = state.accessMode;
    }

    function render() {
        var parts = partitionUsers();
        renderMode();
        renderCounters(parts);
        renderPending(parts.pending);
        renderAllowed(parts.allowed);
        renderBlocked(parts.blocked);
        var stamp = el("accessLastUpdate");
        if (stamp) stamp.textContent = new Date().toLocaleTimeString("de-DE");
    }

    async function load() {
        var data = await fetchJSON("api/v1/telegram/users");
        state.users = data.users || [];
        state.accessMode = data.access_mode || "whitelist";
        render();
    }

    async function updateUser(identifier, isAllowed, role) {
        await fetchJSON("api/v1/telegram/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                identifier: String(identifier),
                is_allowed: isAllowed,
                role: role || "user",
            }),
        });
        await load();
    }

    async function deleteUser(recordId) {
        if (!window.confirm("Diesen Eintrag wirklich entfernen?")) return;
        await fetchJSON("api/v1/telegram/users/" + encodeURIComponent(recordId), { method: "DELETE" });
        await load();
    }

    function bindEvents() {
        var refresh = el("btnAccessRefresh");
        if (refresh) {
            refresh.addEventListener("click", function () {
                load().catch(function (err) {
                    showToast(err.message, true);
                });
            });
        }

        var saveMode = el("btnSaveAccessMode");
        if (saveMode) {
            saveMode.addEventListener("click", async function () {
                var select = el("accessModeSelect");
                if (!select) return;
                try {
                    await fetchJSON("api/settings", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ telegram_access_mode: select.value }),
                    });
                    state.accessMode = select.value;
                    render();
                    showToast("Zugriffsmodus gespeichert.");
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        }

        var form = el("formAddAccessUser");
        if (form) {
            form.addEventListener("submit", async function (event) {
                event.preventDefault();
                var identifier = el("accessNewIdentifier");
                var name = el("accessNewName");
                var role = el("accessNewRole");
                try {
                    await fetchJSON("api/v1/telegram/users", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            identifier: identifier.value,
                            first_name: name.value || null,
                            role: role.value,
                            is_allowed: 1,
                            note: "Über /access freigeschaltet",
                        }),
                    });
                    identifier.value = "";
                    name.value = "";
                    await load();
                    showToast("Person freigeschaltet.");
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        }

        document.addEventListener("change", async function (event) {
            var target = event.target;
            if (!target || target.getAttribute("data-action") !== "role") return;
            try {
                await updateUser(target.getAttribute("data-ident"), 1, target.value);
                showToast("Rolle aktualisiert.");
            } catch (err) {
                showToast(err.message, true);
            }
        });

        document.addEventListener("click", async function (event) {
            var button = event.target && event.target.closest ? event.target.closest("button[data-action]") : null;
            if (!button) return;
            var action = button.getAttribute("data-action");
            var ident = button.getAttribute("data-ident");
            try {
                if (action === "approve") {
                    var row = button.closest("tr");
                    var select = row ? row.querySelector("[data-role-select]") : null;
                    await updateUser(ident, 1, select ? select.value : "user");
                    showToast("Anfrage freigeschaltet.");
                } else if (action === "block") {
                    await updateUser(ident, -1, "viewer");
                    showToast("Zugriff gesperrt.");
                } else if (action === "unblock") {
                    await updateUser(ident, 1, button.getAttribute("data-role") || "user");
                    showToast("Zugriff wiederhergestellt.");
                } else if (action === "delete") {
                    await deleteUser(button.getAttribute("data-id"));
                    showToast("Eintrag entfernt.");
                }
            } catch (err) {
                showToast(err.message, true);
            }
        });

        var themeBtn = el("btnThemeToggle");
        if (themeBtn) {
            var syncTheme = function () {
                themeBtn.textContent =
                    document.documentElement.getAttribute("data-theme") === "light" ? "Theme: LIGHT" : "Theme: DARK";
            };
            themeBtn.addEventListener("click", function () {
                var next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
                if (window.applyTheme) window.applyTheme(next);
                syncTheme();
            });
            syncTheme();
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindEvents();
        load().catch(function (err) {
            showToast(err.message, true);
        });
    });
})();
