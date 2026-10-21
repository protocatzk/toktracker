let currentPeriod = "all";
let cachedStreamers = [];
let cachedGifts = [];
let cachedWorkers = [];
let cachedTgLogs = [];

function fmtEUR(v) {
    return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(v || 0);
}

function fmtUSD(v) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v || 0);
}

function fmtNum(v) {
    return new Intl.NumberFormat("de-DE").format(v || 0);
}

function applyTheme(theme) {
    const normalized = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", normalized);
    try {
        localStorage.setItem("toktracker_theme", normalized);
    } catch (e) {}
    const btn = document.getElementById("btnThemeToggle");
    if (btn) {
        btn.textContent = normalized === "dark" ? "Theme: DARK" : "Theme: LIGHT";
    }
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === tabId);
    });
}

async function loadOverview() {
    try {
        const res = await fetch(`/api/overview?period=${encodeURIComponent(currentPeriod)}`);
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        const data = await res.json();

        const t = data.totals || {};
        document.getElementById("sumNetEur").textContent = fmtEUR(t.eur_net);
        document.getElementById("sumNetUsd").textContent = `${fmtUSD(t.usd_net)} USD`;
        document.getElementById("sumCoins").textContent = fmtNum(t.total_coins);
        document.getElementById("sumStreamersSub").textContent =
            `${fmtNum(t.streamer_count)} Streamer (${fmtNum(t.live_count)} LIVE)`;
        document.getElementById("sumGrossEur").textContent = fmtEUR(t.eur_gross);
        document.getElementById("sumGrossUsd").textContent = `${fmtUSD(t.usd_gross)} USD`;
        document.getElementById("sumGiftsSent").textContent = fmtNum(t.total_gifts_sent);
        document.getElementById("sumGiftEvents").textContent = `${fmtNum(t.gift_events_count)} Transaktionen`;

        document.getElementById("badgeStreamers").textContent = fmtNum(t.streamer_count || 0);
        document.getElementById("badgeGifts").textContent = fmtNum(t.gift_events_count || 0);
        document.getElementById("badgeTgUsers").textContent = fmtNum((data.telegram_users || []).length);

        if (data.system) {
            document.getElementById("sysWorkerInfo").textContent =
                `${data.system.workers_running} aktiv (${data.system.workers_connected} verbunden)`;

            const tg = data.system.telegram_bot;
            if (tg) {
                const tgLabel = tg.bot_username
                    ? `${tg.state.toUpperCase()} (${tg.bot_username})`
                    : tg.state.toUpperCase();
                document.getElementById("sysTelegramInfo").textContent = tgLabel;
                if (tg.access_mode) {
                    document.getElementById("sysTelegramMode").textContent = tg.access_mode.toUpperCase();
                }
            }
            cachedWorkers = data.system.workers || [];
            cachedTgLogs = tg ? tg.logs || [] : [];
            renderServiceLogs();
        }

        if (data.settings) {
            const activeEl = document.activeElement;
            if (!activeEl || !activeEl.id.startsWith("set")) {
                document.getElementById("setUsdPerDiamond").value = data.settings.usd_per_diamond;
                document.getElementById("setGrossUsdPerCoin").value = data.settings.gross_usd_per_coin;
                document.getElementById("setUsdToEur").value = data.settings.usd_to_eur_rate;
                document.getElementById("setPollInterval").value = data.settings.poll_interval_seconds;
            }
            const modeSel = document.getElementById("selectTelegramMode");
            if (modeSel && activeEl !== modeSel && data.settings.telegram_access_mode) {
                modeSel.value = data.settings.telegram_access_mode;
            }
        }

        cachedStreamers = data.streamers || [];
        cachedGifts = data.recent_gifts || [];

        renderStreamerTable();
        renderGiftLog();
        renderTelegramUsers(
            data.telegram_users || [],
            data.settings ? data.settings.telegram_access_mode : "whitelist"
        );
        populateSimulatorSelect(cachedStreamers);
    } catch (e) {
        console.error("Fehler beim Laden:", e);
    }
}

function renderStreamerTable() {
    const tbody = document.getElementById("streamerTableBody");
    const filterVal = (document.getElementById("inputStreamerFilter")?.value || "").trim().toLowerCase();

    const filtered = cachedStreamers.filter((s) => {
        if (!filterVal) return true;
        const u = (s.username || "").toLowerCase();
        const d = (s.display_name || "").toLowerCase();
        return u.includes(filterVal) || d.includes(filterVal);
    });

    document.getElementById("streamerTableMeta").textContent =
        `${filtered.length} von ${cachedStreamers.length} Streamern`;

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="muted">Keine passenden Streamer vorhanden.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered
        .map((s) => {
            const diag = s.worker_diagnostics;
            const state = diag ? diag.state : (s.is_live ? "live" : "stopped");
            let tagClass = "";
            if (state === "connected" || s.is_live) tagClass = "live";
            else if (state === "polling_offline" || state === "connecting" || state === "backoff") tagClass = "polling";

            const isAutoMarked = Boolean(s.auto_monitor || s.is_tracking);
            const autoBadge = isAutoMarked
                ? `<span class="status-tag live" title="In Datenbank für automatische Aufzeichnung beim Programmstart markiert">AUTO-START</span>`
                : `<span class="status-tag" title="Kein Auto-Start beim Programmstart">MANUELL</span>`;

            const topGift = s.top_gift
                ? `${s.top_gift.gift_name} (${fmtNum(s.top_gift.coins)})`
                : "-";
            const topGifter = s.top_gifter
                ? `@${s.top_gifter.sender_username} (${fmtNum(s.top_gifter.coins)})`
                : "-";

            const trackBtnText = s.is_tracking_active ? "Stop" : "Start";

            return `
                <tr>
                    <td class="mono muted">#${s.id}</td>
                    <td>
                        <strong><a href="#" onclick="showStreamerDetail(${s.id}); return false;">${s.display_name || s.username}</a></strong>
                        <div class="mono muted">@${s.username}${s.room_id ? ` · Room ${s.room_id}` : ""}</div>
                    </td>
                    <td>
                        <div style="display:flex; gap:4px; flex-wrap:wrap; align-items:center;">
                            <span class="status-tag ${tagClass}">${state.toUpperCase()}</span>
                            ${autoBadge}
                        </div>
                        <div class="mono muted" style="margin-top:3px;">${s.monitor_status || ""}</div>
                        ${s.last_error ? `<div class="mono err-text">${s.last_error}</div>` : ""}
                    </td>
                    <td class="num-col">
                        <strong>${fmtNum(s.current_viewers || 0)}</strong>
                        <div class="muted">${fmtNum(s.follower_count || 0)} Follower</div>
                    </td>
                    <td class="num-col">
                        <strong>${fmtNum(s.total_coins)}</strong>
                        <div class="muted">${fmtNum(s.total_gifts_sent)} Gifts / ${s.unique_gifters} Gifter</div>
                    </td>
                    <td class="num-col"><strong>${fmtEUR(s.eur_net)}</strong></td>
                    <td class="num-col">${fmtUSD(s.usd_net)}</td>
                    <td class="num-col">${fmtEUR(s.eur_gross)}</td>
                    <td class="mono">
                        <div>Gift: ${topGift}</div>
                        <div class="muted">Spender: ${topGifter}</div>
                    </td>
                    <td>
                        <div class="action-group">
                            <button type="button" class="sm" onclick="toggleWorker(${s.id})">${trackBtnText}</button>
                            <button type="button" class="sm" onclick="showStreamerDetail(${s.id})">Details</button>
                            <button type="button" class="sm" onclick="refreshStreamer(${s.id})" title="TikTok Profil aktualisieren">Sync</button>
                            <a class="btn-link sm mono" href="/api/v1/streamers/${encodeURIComponent(s.username)}/report?hours=24" target="_blank">JSON</a>
                            <button type="button" class="sm danger" onclick="deleteStreamer(${s.id}, '${s.username}')">X</button>
                        </div>
                    </td>
                </tr>
            `;
        })
        .join("");
}

function renderGiftLog() {
    const tbody = document.getElementById("giftLogBody");
    const filterVal = (document.getElementById("inputGiftFilter")?.value || "").trim().toLowerCase();

    const filtered = cachedGifts.filter((g) => {
        if (!filterVal) return true;
        return (
            (g.streamer_username || "").toLowerCase().includes(filterVal) ||
            (g.sender_username || "").toLowerCase().includes(filterVal) ||
            (g.sender_nickname || "").toLowerCase().includes(filterVal) ||
            (g.gift_name || "").toLowerCase().includes(filterVal)
        );
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="muted">Keine Geschenke im gewählten Zeitraum.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered
        .map((g) => {
            const ts = (g.created_at || "").replace("T", " ");
            return `
                <tr>
                    <td class="mono muted">${ts}</td>
                    <td class="mono"><strong>@${g.streamer_username}</strong></td>
                    <td>
                        ${g.sender_nickname || g.sender_username}
                        <span class="mono muted">(@${g.sender_username})</span>
                        ${g.is_super_fan ? `<span class="status-tag polling">SUPERFAN</span>` : ""}
                    </td>
                    <td><strong>${g.repeat_count}x</strong> ${g.gift_name}</td>
                    <td class="num-col"><strong>${fmtNum(g.total_coins)}</strong></td>
                    <td class="num-col"><strong>${fmtEUR(g.eur_net)}</strong></td>
                    <td class="num-col">${fmtUSD(g.usd_net)}</td>
                    <td class="mono muted">${g.source}</td>
                </tr>
            `;
        })
        .join("");
}

function renderTelegramUsers(users, accessMode) {
    const tbody = document.getElementById("telegramUsersBody");
    if (!tbody) return;
    if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="muted">Noch keine Telegram-Nutzer hinterlegt. Trage oben eine Telegram-ID oder einen @username ein oder sende <code>/start</code> an den Bot.</td></tr>`;
        return;
    }

    tbody.innerHTML = users
        .map((u) => {
            const allowed = parseInt(u.is_allowed || 0, 10);
            let statusHtml = "";
            if (allowed === 1) {
                statusHtml = `<span class="status-tag live">FREIGESCHALTET</span>`;
            } else if (allowed === 0) {
                statusHtml =
                    accessMode === "public"
                        ? `<span class="status-tag polling">PUBLIC-GAST</span>`
                        : `<span class="status-tag polling">ANFRAGE OFFEN</span>`;
            } else {
                statusHtml = `<span class="status-tag danger">GESPERRT</span>`;
            }

            const roleBadge = u.role === "admin" ? `<strong>ADMIN</strong>` : `Nutzer`;
            const ident = u.telegram_id ? String(u.telegram_id) : `@${u.username}`;
            const unameStr = u.username ? `@${u.username}` : "-";
            const fnameStr = u.first_name ? ` (${u.first_name})` : "";
            const lastSeen = (u.last_seen_at || "").replace("T", " ");

            return `
                <tr>
                    <td class="mono">${u.telegram_id || `<span class="muted">wird bei Nachricht verknüpft</span>`}</td>
                    <td><strong>${unameStr}</strong>${fnameStr}</td>
                    <td class="mono">${roleBadge}</td>
                    <td>${statusHtml}</td>
                    <td class="mono muted">${u.note || "-"}</td>
                    <td class="mono muted">${lastSeen}</td>
                    <td>
                        <div class="action-group">
                            ${
                                allowed !== 1
                                    ? `<button type="button" class="sm primary" onclick="updateTgUser('${ident}', 1, '${u.role || "user"}')">Freischalten</button>`
                                    : `<button type="button" class="sm" onclick="updateTgUser('${ident}', -1, 'user')">Sperren</button>`
                            }
                            ${
                                u.role !== "admin"
                                    ? `<button type="button" class="sm" onclick="updateTgUser('${ident}', 1, 'admin')">→ Admin</button>`
                                    : `<button type="button" class="sm" onclick="updateTgUser('${ident}', 1, 'user')">→ Nutzer</button>`
                            }
                            <button type="button" class="sm danger" onclick="deleteTgUser(${u.id})">X</button>
                        </div>
                    </td>
                </tr>
            `;
        })
        .join("");
}

async function updateTgUser(identifier, isAllowed, role) {
    await fetch("/api/v1/telegram/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            identifier: String(identifier),
            is_allowed: isAllowed,
            role: role,
        }),
    });
    loadOverview();
}

async function deleteTgUser(recordId) {
    if (!confirm("Diesen Telegram-Eintrag wirklich entfernen?")) return;
    await fetch(`/api/v1/telegram/users/${recordId}`, { method: "DELETE" });
    loadOverview();
}

function renderServiceLogs() {
    const box = document.getElementById("workerLogBox");
    const sourceFilter = document.getElementById("selectLogSource")?.value || "all";
    const lines = [];

    if (sourceFilter === "all" || sourceFilter === "TikTok") {
        cachedWorkers.forEach((w) => {
            (w.logs || []).forEach((l) => {
                lines.push(`${l.timestamp} [TikTok:@${w.username}] [${l.level}] ${l.message}`);
            });
        });
    }
    if (sourceFilter === "all" || sourceFilter === "TelegramBot") {
        cachedTgLogs.forEach((l) => {
            lines.push(`${l.timestamp} [TelegramBot] [${l.level}] ${l.message}`);
        });
    }

    lines.sort().reverse();
    box.innerHTML = lines.length > 0 ? lines.slice(0, 45).join("<br/>") : "Keine Service-Logs für diese Auswahl vorhanden.";
}

function populateSimulatorSelect(streamers) {
    const sel = document.getElementById("simStreamerSelect");
    const prev = sel.value;
    sel.innerHTML =
        `<option value="">Streamer wählen</option>` +
        streamers.map((s) => `<option value="${s.id}">@${s.username}</option>`).join("");
    if (prev && streamers.some((s) => String(s.id) === String(prev))) {
        sel.value = prev;
    } else if (streamers.length > 0) {
        sel.value = streamers[0].id;
    }
}

async function showStreamerDetail(streamerId) {
    const res = await fetch(`/api/streamers/${streamerId}?period=${encodeURIComponent(currentPeriod)}`);
    if (!res.ok) return;
    const data = await res.json();
    const s = data.streamer;

    document.getElementById("detailTitle").textContent =
        `Auswertung: ${s.display_name || s.username} (@${s.username})`;
    document.getElementById("detailSubtitle").textContent =
        `Netto: ${fmtEUR(data.summary.eur_net)} (${fmtUSD(data.summary.usd_net)}) · Coins: ${fmtNum(data.summary.total_coins)} · Brutto: ${fmtEUR(data.summary.eur_gross)}`;

    const giftsBody = document.getElementById("detailGiftsBody");
    giftsBody.innerHTML =
        data.gift_breakdown.length === 0
            ? `<tr><td colspan="4" class="muted">Keine Geschenke aufgezeichnet.</td></tr>`
            : data.gift_breakdown
                  .map(
                      (g) => `
                <tr>
                    <td><strong>${g.gift_name}</strong> <span class="mono muted">(${g.diamond_count})</span></td>
                    <td class="num-col">${fmtNum(g.total_quantity)}x</td>
                    <td class="num-col">${fmtNum(g.total_coins)}</td>
                    <td class="num-col"><strong>${fmtEUR(g.eur_net)}</strong></td>
                </tr>`
                  )
                  .join("");

    const giftersBody = document.getElementById("detailGiftersBody");
    giftersBody.innerHTML =
        data.top_gifters.length === 0
            ? `<tr><td colspan="4" class="muted">Keine Spender aufgezeichnet.</td></tr>`
            : data.top_gifters
                  .map(
                      (tg) => `
                <tr>
                    <td><strong>@${tg.sender_username}</strong> ${tg.is_super_fan ? `<span class="status-tag polling">SF</span>` : ""}</td>
                    <td class="num-col">${fmtNum(tg.gifts_sent)}</td>
                    <td class="num-col">${fmtNum(tg.total_coins)}</td>
                    <td class="num-col"><strong>${fmtEUR(tg.eur_net)}</strong></td>
                </tr>`
                  )
                  .join("");

    const sessBox = document.getElementById("detailSessionsList");
    sessBox.innerHTML =
        (data.sessions || []).length === 0
            ? "Noch keine aufgezeichneten Live-Sessions."
            : data.sessions
                  .map(
                      (ss) =>
                          `#${ss.id} [${ss.status.toUpperCase()}] Start: ${ss.started_at} | Peak Viewers: ${fmtNum(ss.peak_viewers)} | Coins: ${fmtNum(ss.session_coins)} (${fmtEUR(ss.eur_net)})`
                  )
                  .join("<br/>");

    const box = document.getElementById("streamerDetailBox");
    box.style.display = "block";
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function toggleWorker(streamerId) {
    const autoReconnect = document.getElementById("checkAutoReconnect").checked;
    await fetch(`/api/streamers/${streamerId}/track`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "toggle", auto_reconnect: autoReconnect }),
    });
    loadOverview();
}

async function refreshStreamer(streamerId) {
    await fetch(`/api/streamers/${streamerId}/refresh`, { method: "POST" });
    loadOverview();
}

async function deleteStreamer(streamerId, username) {
    if (!confirm(`Streamer @${username} wirklich löschen?`)) return;
    await fetch(`/api/streamers/${streamerId}`, { method: "DELETE" });
    loadOverview();
}

document.addEventListener("DOMContentLoaded", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(currentTheme);

    const themeBtn = document.getElementById("btnThemeToggle");
    if (themeBtn) {
        themeBtn.addEventListener("click", () => {
            const nextTheme =
                document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
            applyTheme(nextTheme);
        });
    }

    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            switchTab(btn.getAttribute("data-tab"));
        });
    });

    loadOverview();
    setInterval(loadOverview, 4000);

    document.getElementById("periodSelect").addEventListener("change", (e) => {
        currentPeriod = e.target.value;
        loadOverview();
    });

    document.getElementById("btnRefresh").addEventListener("click", loadOverview);

    document.getElementById("inputStreamerFilter").addEventListener("input", renderStreamerTable);
    document.getElementById("inputGiftFilter").addEventListener("input", renderGiftLog);
    document.getElementById("selectLogSource").addEventListener("change", renderServiceLogs);

    document.getElementById("btnSendTelegramReport").addEventListener("click", async () => {
        const res = await fetch("/api/v1/telegram/send-report?hours=24", { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            alert(`24h-Bericht erfolgreich an Telegram (Chat ${data.chat_id}) gesendet!`);
        } else {
            alert(`Telegram-Versand Hinweis:\n${data.detail || "Bot nicht aktiv"}`);
        }
        loadOverview();
    });

    document.getElementById("selectTelegramMode").addEventListener("change", async (e) => {
        const newMode = e.target.value;
        await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ telegram_access_mode: newMode }),
        });
        loadOverview();
    });

    document.getElementById("formAddTelegramUser").addEventListener("submit", async (e) => {
        e.preventDefault();
        const identInput = document.getElementById("inputTgIdentifier");
        const nameInput = document.getElementById("inputTgName");
        const roleSelect = document.getElementById("selectTgRole");

        const res = await fetch("/api/v1/telegram/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                identifier: identInput.value,
                first_name: nameInput.value || null,
                role: roleSelect.value,
                is_allowed: 1,
                note: "Über Web-Konsole freigeschaltet",
            }),
        });
        if (res.ok) {
            identInput.value = "";
            nameInput.value = "";
            loadOverview();
        }
    });

    document.getElementById("btnCloseDetail").addEventListener("click", () => {
        document.getElementById("streamerDetailBox").style.display = "none";
    });

    document.getElementById("formAddStreamer").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("inputUsername");
        const displayInput = document.getElementById("inputDisplayName");
        const autoTrack = document.getElementById("checkAutoTrack").checked;
        const autoReconnect = document.getElementById("checkAutoReconnect").checked;
        const res = await fetch("/api/streamers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: input.value,
                display_name: displayInput.value || null,
                auto_track: autoTrack,
                auto_reconnect: autoReconnect,
            }),
        });
        if (res.ok) {
            input.value = "";
            displayInput.value = "";
            loadOverview();
        }
    });

    document.getElementById("formSimulateGift").addEventListener("submit", async (e) => {
        e.preventDefault();
        const streamerId = document.getElementById("simStreamerSelect").value;
        const giftSel = document.getElementById("simGiftSelect");
        const opt = giftSel.options[giftSel.selectedIndex];
        const diamonds = parseInt(opt.getAttribute("data-diamonds") || "1", 10);
        const repeatCount = parseInt(document.getElementById("simRepeatCount").value || "1", 10);
        const sender = document.getElementById("simSender").value || "live_viewer";

        await fetch("/api/gifts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                streamer_id: parseInt(streamerId, 10),
                gift_name: giftSel.value,
                diamond_count: diamonds,
                repeat_count: repeatCount,
                sender_username: sender,
                source: "manual",
            }),
        });
        loadOverview();
    });

    document.getElementById("btnSeedDemo").addEventListener("click", async () => {
        await fetch("/api/demo/seed", { method: "POST" });
        loadOverview();
    });

    document.getElementById("btnClearDemo").addEventListener("click", async () => {
        await fetch("/api/demo/clear", { method: "POST" });
        loadOverview();
    });

    document.getElementById("formSettings").addEventListener("submit", async (e) => {
        e.preventDefault();
        await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                usd_per_diamond: parseFloat(document.getElementById("setUsdPerDiamond").value),
                gross_usd_per_coin: parseFloat(document.getElementById("setGrossUsdPerCoin").value),
                usd_to_eur_rate: parseFloat(document.getElementById("setUsdToEur").value),
                poll_interval_seconds: parseInt(document.getElementById("setPollInterval").value, 10),
            }),
        });
        loadOverview();
    });
});
