/*
 * TT-INTELLIGENCE – Zugriff, Whitelist & Rollen (/access).
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
        permissionUserId: null,
        permissionData: null,
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
            window.location.href = loginUrl();
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
                var directCount =
                    (u.permission_grants || []).length + (u.permission_denies || []).length;
                var directBadge = directCount
                    ? ' <span class="status-tag polling">' + directCount + " DIREKT</span>"
                    : "";
                return (
                    "<tr>" +
                    "<td>" + idCell(u) + "</td>" +
                    "<td>" + userCell(u) + "</td>" +
                    '<td><select class="sm" data-action="role" data-ident="' + ident + '" aria-label="Rolle ändern">' + roleOptions(u.role || "viewer") + "</select>" + directBadge + "</td>" +
                    '<td><span class="status-tag live">FREIGESCHALTET</span></td>' +
                    "<td>" + noteCell(u) + "</td>" +
                    "<td>" + lastSeenCell(u) + "</td>" +
                    '<td><div class="action-group">' +
                    '<button type="button" class="sm" data-action="permissions" data-id="' + esc(u.id) + '">Rechte</button>' +
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

    function permissionUserLabel(user) {
        if (user.username) return "@" + user.username;
        if (user.first_name) return user.first_name;
        return "ID " + (user.telegram_id || user.id);
    }

    function permissionRow(perm, data) {
        var key = perm.key;
        var inherited = (data.role_permissions || []).indexOf(key) !== -1;
        var effective =
            (data.effective_permissions || []).indexOf(key) !== -1
                ? '<span class="status-tag live">AKTIV</span>'
                : '<span class="muted">–</span>';
        var grantSelected = (data.grants || []).indexOf(key) !== -1 ? " selected" : "";
        var denySelected = (data.denies || []).indexOf(key) !== -1 ? " selected" : "";
        var inheritedLabel = inherited ? "Rolle (aktiv)" : "Rolle (inaktiv)";
        return (
            "<tr>" +
            '<td><strong>' + esc(perm.label) + '</strong><span class="access-perm-key mono muted">' + esc(key) + "</span></td>" +
            "<td>" + effective + "</td>" +
            '<td><select class="sm" data-perm-key="' + esc(key) + '" aria-label="' + esc(perm.label) + '">' +
            '<option value="inherit"' + (grantSelected || denySelected ? "" : " selected") + ">" + esc(inheritedLabel) + "</option>" +
            '<option value="grant"' + grantSelected + ">Erteilen</option>" +
            '<option value="deny"' + denySelected + ">Entziehen</option>" +
            "</select></td>" +
            "</tr>"
        );
    }

    function renderPermissionDialog() {
        var data = state.permissionData;
        if (!data) return;
        var user = data.user || {};
        var title = el("accessPermissionTitle");
        var sub = el("accessPermissionSub");
        if (title) title.textContent = "Rechte · " + permissionUserLabel(user);
        if (sub) {
            sub.textContent =
                "Rolle: " + (ROLE_LABELS[data.role] || data.role || "–") +
                " · Persönliche Overrides werden beim nächsten Request wirksam.";
        }

        var web = [];
        var bot = [];
        (data.permissions || []).forEach(function (perm) {
            if (perm.scope === "bot") bot.push(perm);
            else web.push(perm);
        });

        function table(titleText, items) {
            if (!items.length) return "";
            return (
                '<h3 class="access-subtitle">' + esc(titleText) + "</h3>" +
                '<div class="table-wrap"><table class="access-matrix access-permission-table">' +
                "<thead><tr><th>Capability</th><th>Effektiv</th><th>Persönlich</th></tr></thead>" +
                "<tbody>" +
                items
                    .map(function (perm) {
                        return permissionRow(perm, data);
                    })
                    .join("") +
                "</tbody></table></div>"
            );
        }

        var body = el("accessPermissionBody");
        if (body) {
            body.innerHTML = table("Web-Capabilities", web) + table("Bot-Capabilities", bot);
        }
        updatePermissionSummary();
    }

    function updatePermissionSummary() {
        var summary = el("accessPermissionSummary");
        if (!summary) return;
        var grants = 0;
        var denies = 0;
        document.querySelectorAll("#accessPermissionBody select[data-perm-key]").forEach(function (select) {
            if (select.value === "grant") grants += 1;
            else if (select.value === "deny") denies += 1;
        });
        summary.innerHTML =
            '<span class="status-tag live">' + grants + " ERTEILT</span> " +
            '<span class="status-tag danger">' + denies + " ENTZOGEN</span>" +
            ' <span class="muted">Alle anderen Rechte kommen aus der Rolle.</span>';
    }

    function collectPermissionOverrides() {
        var grants = [];
        var denies = [];
        document.querySelectorAll("#accessPermissionBody select[data-perm-key]").forEach(function (select) {
            var key = select.getAttribute("data-perm-key");
            if (select.value === "grant") grants.push(key);
            else if (select.value === "deny") denies.push(key);
        });
        return { grants: grants, denies: denies };
    }

    async function openPermissions(recordId) {
        state.permissionUserId = String(recordId);
        state.permissionData = await fetchJSON(
            "api/v1/telegram/users/" + encodeURIComponent(recordId) + "/permissions"
        );
        renderPermissionDialog();
        var dialog = el("accessPermissionDialog");
        if (dialog && typeof dialog.showModal === "function") dialog.showModal();
        else if (dialog) dialog.setAttribute("open", "open");
    }

    function closePermissions() {
        var dialog = el("accessPermissionDialog");
        if (dialog && typeof dialog.close === "function") dialog.close();
        else if (dialog) dialog.removeAttribute("open");
    }

    async function savePermissions(reset) {
        if (!state.permissionUserId) return;
        if (reset) {
            document.querySelectorAll("#accessPermissionBody select[data-perm-key]").forEach(function (select) {
                select.value = "inherit";
            });
            updatePermissionSummary();
        }
        var payload = collectPermissionOverrides();
        await fetchJSON(
            "api/v1/telegram/users/" + encodeURIComponent(state.permissionUserId) + "/permissions",
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            }
        );
        closePermissions();
        await load();
        showToast("Persönliche Rechte gespeichert.");
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

        var closePermissionsBtn = el("btnClosePermissions");
        if (closePermissionsBtn) {
            closePermissionsBtn.addEventListener("click", closePermissions);
        }
        var savePermissionsBtn = el("btnSavePermissions");
        if (savePermissionsBtn) {
            savePermissionsBtn.addEventListener("click", function () {
                savePermissions(false).catch(function (err) {
                    showToast(err.message, true);
                });
            });
        }
        var resetPermissionsBtn = el("btnResetPermissions");
        if (resetPermissionsBtn) {
            resetPermissionsBtn.addEventListener("click", function () {
                if (!window.confirm("Alle persönlichen Rechte dieses Kontos zurücksetzen?")) return;
                savePermissions(true).catch(function (err) {
                    showToast(err.message, true);
                });
            });
        }
        var permissionDialog = el("accessPermissionDialog");
        if (permissionDialog) {
            permissionDialog.addEventListener("close", function () {
                state.permissionUserId = null;
                state.permissionData = null;
            });
        }

        var saveMode = el("btnSaveAccessMode");
        if (saveMode) {            saveMode.addEventListener("click", async function () {
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
            if (!target) return;
            if (target.matches && target.matches("#accessPermissionBody select[data-perm-key]")) {
                updatePermissionSummary();
                return;
            }
            if (target.getAttribute("data-action") !== "role") return;
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
                } else if (action === "permissions") {
                    await openPermissions(button.getAttribute("data-id"));
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
