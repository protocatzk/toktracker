let currentPeriod = "all";
let cachedStreamers = [];
let cachedGifts = [];
let cachedWorkers = [];
let cachedTgLogs = [];

let analyticsPeriod = "24h";
let analyticsStreamerId = "all";
let analyticsTimelineMode = "both"; // 'both', 'multi', 'eur', 'coins'
let cachedAnalyticsData = null;

let chartTimelineInstance = null;
let chartCompareInstance = null;
let chartTimeOfDayInstance = null;
let chartGiftDistInstance = null;
let chartTopGiftersInstance = null;

function fmtEUR(v) {
    return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(v || 0);
}

function fmtUSD(v) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v || 0);
}

function fmtNum(v) {
    return new Intl.NumberFormat("de-DE").format(v || 0);
}

function getChartThemeColors() {
    const isDark = (document.documentElement.getAttribute("data-theme") || "dark") === "dark";
    return {
        isDark,
        textColor: isDark ? "#c9d1d9" : "#24292f",
        mutedColor: isDark ? "#8b949e" : "#57606a",
        gridColor: isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.08)",
        borderColor: isDark ? "#30363d" : "#d0d7de",
        tooltipBg: isDark ? "#161b22" : "#ffffff",
        tooltipText: isDark ? "#f0f6fc" : "#0d1117",
        tooltipBorder: isDark ? "#30363d" : "#d0d7de",
        primary: "#58a6ff",
        secondary: "#3fb950",
        accentGold: "#d29922",
        accentPurple: "#bc8cff",
        accentPink: "#f778ba",
        accentCyan: "#39c5cf",
        palette: [
            "#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f778ba",
            "#39c5cf", "#ffa657", "#ff7b72", "#7ee787", "#79c0ff"
        ]
    };
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
    if (cachedAnalyticsData) {
        renderTimelineChart(cachedAnalyticsData);
        renderCompareChart(cachedAnalyticsData);
        renderTimeOfDayChart(cachedAnalyticsData);
        renderGiftDistChart(cachedAnalyticsData);
        renderTopGiftersChart(cachedAnalyticsData);
    }
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === tabId);
    });
    if (tabId === "tab-analytics") {
        loadAnalytics();
    }
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
        document.getElementById("badgeAnalytics").textContent = fmtNum(t.streamer_count || 0);
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
        populateAnalyticsStreamerSelect(cachedStreamers);
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
                            <button type="button" class="sm primary" onclick="openStreamerAnalytics(${s.id})">Analytics</button>
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

function populateAnalyticsStreamerSelect(streamers) {
    const sel = document.getElementById("selectAnalyticsStreamer");
    if (!sel) return;
    const currentVal = sel.value || analyticsStreamerId || "all";

    sel.innerHTML = `<option value="all">Alle überwachten Streamer (Vergleich &amp; Gesamt)</option>` +
        streamers.map(s => {
            const liveMarker = s.is_live ? " [LIVE]" : "";
            const dName = s.display_name && s.display_name !== s.username ? `${s.display_name} (@${s.username})` : `@${s.username}`;
            return `<option value="${s.id}">${dName}${liveMarker}</option>`;
        }).join("");

    if (currentVal && (currentVal === "all" || streamers.some(s => String(s.id) === String(currentVal)))) {
        sel.value = currentVal;
    }
}

function openStreamerAnalytics(streamerId) {
    analyticsStreamerId = String(streamerId);
    const sel = document.getElementById("selectAnalyticsStreamer");
    if (sel) {
        sel.value = String(streamerId);
    }
    switchTab("tab-analytics");
    loadAnalytics();
}

function toggleTimelineMetric() {
    const modes = ["both", "multi", "eur", "coins"];
    let nextIdx = (modes.indexOf(analyticsTimelineMode) + 1) % modes.length;
    analyticsTimelineMode = modes[nextIdx];

    const btn = document.getElementById("btnTimelineToggleMetric");
    if (btn) {
        if (analyticsTimelineMode === "both") btn.textContent = "Metrik: Coins & EUR";
        else if (analyticsTimelineMode === "multi") btn.textContent = "Metrik: Top-Streamer Vergleich";
        else if (analyticsTimelineMode === "eur") btn.textContent = "Metrik: Nur Netto EUR";
        else if (analyticsTimelineMode === "coins") btn.textContent = "Metrik: Nur Coins";
    }

    if (cachedAnalyticsData) {
        renderTimelineChart(cachedAnalyticsData);
    }
}

function renderTimelineChart(data) {
    const canvas = document.getElementById("chartTimeline");
    if (!canvas || typeof Chart === "undefined") return;

    if (chartTimelineInstance) {
        chartTimelineInstance.destroy();
        chartTimelineInstance = null;
    }

    const colors = getChartThemeColors();
    const timeline = data.timeline || [];
    const labels = timeline.map(t => t.label);

    const titleEl = document.getElementById("timelineChartTitle");
    const subEl = document.getElementById("timelineChartSubtitle");
    const isSingleStreamer = Boolean(data.selected_streamer);
    const streamerName = isSingleStreamer ? (data.selected_streamer.display_name || data.selected_streamer.username) : "Alle Streamer";

    let datasets = [];
    let scales = {
        x: {
            grid: { color: colors.gridColor },
            ticks: { color: colors.mutedColor, font: { size: 11, family: "JetBrains Mono" } }
        },
        y: {
            position: "left",
            grid: { color: colors.gridColor },
            ticks: { color: colors.mutedColor, font: { size: 11, family: "JetBrains Mono" } },
            title: { display: true, text: "Coins", color: colors.mutedColor, font: { size: 11, family: "JetBrains Mono" } }
        }
    };

    if (analyticsTimelineMode === "multi" && !isSingleStreamer && data.multi_streamer_datasets && data.multi_streamer_datasets.length > 0) {
        if (titleEl) titleEl.textContent = `Top-Streamer Einnahmen-Vergleich (${labels.length} Zeitintervalle)`;
        if (subEl) subEl.textContent = `Chronologischer Coin-Verlauf der aktivsten Streamer`;
        datasets = data.multi_streamer_datasets.map((s, idx) => {
            const color = colors.palette[idx % colors.palette.length];
            return {
                type: "line",
                label: `@${s.username}`,
                data: s.data,
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                pointRadius: 3,
                tension: 0.25,
                fill: false,
            };
        });
    } else if (analyticsTimelineMode === "coins") {
        if (titleEl) titleEl.textContent = `Coin-Verlauf · ${streamerName}`;
        if (subEl) subEl.textContent = `Chronologische Entwicklung der erhaltenen Coins im Zeitfenster`;
        datasets = [{
            type: "bar",
            label: "Coins",
            data: timeline.map(t => t.coins),
            backgroundColor: colors.accentGold + "dd",
            borderColor: colors.accentGold,
            borderWidth: 1,
            borderRadius: 2,
        }];
    } else if (analyticsTimelineMode === "eur") {
        if (titleEl) titleEl.textContent = `Netto Creator-Auszahlung (EUR) · ${streamerName}`;
        if (subEl) subEl.textContent = `Chronologische Entwicklung der Netto-Erlöse in Euro`;
        scales.y.title.text = "Netto EUR (€)";
        scales.y.ticks.callback = (v) => `${v} €`;
        datasets = [{
            type: "line",
            label: "Netto EUR",
            data: timeline.map(t => t.eur_net),
            borderColor: colors.secondary,
            backgroundColor: colors.secondary + "26",
            borderWidth: 2,
            pointRadius: 3,
            fill: true,
            tension: 0.3,
        }];
    } else {
        // Mode "both" (default)
        if (titleEl) titleEl.textContent = `Einnahmen- & Coin-Verlauf · ${streamerName}`;
        if (subEl) subEl.textContent = `Balken: Coins (links) | Linie: Netto Creator-Auszahlung in Euro (rechts)`;
        scales.y1 = {
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: {
                color: colors.mutedColor,
                font: { size: 11, family: "JetBrains Mono" },
                callback: (v) => `${v} €`
            },
            title: { display: true, text: "Netto EUR", color: colors.mutedColor, font: { size: 11, family: "JetBrains Mono" } }
        };
        datasets = [
            {
                type: "bar",
                label: "Coins",
                data: timeline.map(t => t.coins),
                backgroundColor: colors.accentGold + "99",
                borderColor: colors.accentGold,
                borderWidth: 1,
                borderRadius: 2,
                yAxisID: "y",
            },
            {
                type: "line",
                label: "Netto EUR (€)",
                data: timeline.map(t => t.eur_net),
                borderColor: colors.primary,
                backgroundColor: colors.primary + "22",
                borderWidth: 2,
                pointRadius: 3,
                fill: false,
                tension: 0.3,
                yAxisID: "y1",
            }
        ];
    }

    chartTimelineInstance = new Chart(canvas, {
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: {
                    display: true,
                    labels: { color: colors.textColor, font: { family: "JetBrains Mono", size: 11 } }
                },
                tooltip: {
                    backgroundColor: colors.tooltipBg,
                    titleColor: colors.tooltipText,
                    bodyColor: colors.tooltipText,
                    borderColor: colors.tooltipBorder,
                    borderWidth: 1,
                    padding: 9,
                }
            },
            scales
        }
    });
}

function renderCompareChart(data) {
    const canvas = document.getElementById("chartCompare");
    if (!canvas || typeof Chart === "undefined") return;

    if (chartCompareInstance) {
        chartCompareInstance.destroy();
        chartCompareInstance = null;
    }

    const colors = getChartThemeColors();
    const titleEl = document.getElementById("compareChartTitle");
    const subEl = document.getElementById("compareChartSubtitle");

    if (!data.selected_streamer) {
        if (titleEl) titleEl.textContent = "Streamer-Umsatz-Ranking";
        if (subEl) subEl.textContent = "Vergleich der überwachten Streamer nach generierten Coins";

        const topStreamers = (data.streamers_ranking || []).slice(0, 10);
        const labels = topStreamers.map(s => `@${s.username}`);
        const coinsData = topStreamers.map(s => s.total_coins);
        const eurData = topStreamers.map(s => s.eur_net);

        chartCompareInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Coins",
                    data: coinsData,
                    backgroundColor: colors.primary + "bb",
                    borderColor: colors.primary,
                    borderWidth: 1,
                    borderRadius: 2,
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                const idx = ctx.dataIndex;
                                return ` Coins: ${fmtNum(coinsData[idx])} (${fmtEUR(eurData[idx])})`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: colors.textColor, font: { size: 11, family: "JetBrains Mono" } }
                    }
                }
            }
        });
    } else {
        if (titleEl) titleEl.textContent = "Session-Performance & Peak-Viewers";
        if (subEl) subEl.textContent = "Peak-Zuschauer und generierte Coins der aufgezeichneten Streams";

        const sess = (data.sessions || []).slice(0, 10).reverse();
        const labels = sess.map(s => `#${s.id} (${(s.started_at || "").slice(5, 10)})`);
        const coinsData = sess.map(s => s.session_coins);
        const viewersData = sess.map(s => s.peak_viewers);

        chartCompareInstance = new Chart(canvas, {
            data: {
                labels,
                datasets: [
                    {
                        type: "bar",
                        label: "Coins",
                        data: coinsData,
                        backgroundColor: colors.accentGold + "bb",
                        borderColor: colors.accentGold,
                        borderWidth: 1,
                        borderRadius: 2,
                        yAxisID: "y",
                    },
                    {
                        type: "line",
                        label: "Peak Viewers",
                        data: viewersData,
                        borderColor: colors.accentPurple,
                        backgroundColor: colors.accentPurple,
                        borderWidth: 2,
                        pointRadius: 4,
                        tension: 0.25,
                        yAxisID: "y1",
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: colors.textColor, font: { family: "JetBrains Mono", size: 11 } }
                    }
                },
                scales: {
                    x: {
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                    },
                    y: {
                        position: "left",
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } },
                        title: { display: true, text: "Coins", color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                    },
                    y1: {
                        position: "right",
                        grid: { drawOnChartArea: false },
                        ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } },
                        title: { display: true, text: "Peak Viewers", color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                    }
                }
            }
        });
    }
}

function renderTimeOfDayChart(data) {
    const canvas = document.getElementById("chartTimeOfDay");
    if (!canvas || typeof Chart === "undefined") return;

    if (chartTimeOfDayInstance) {
        chartTimeOfDayInstance.destroy();
        chartTimeOfDayInstance = null;
    }

    const colors = getChartThemeColors();
    const tod = data.time_of_day || [];
    const labels = tod.map(t => t.label);
    const coinsData = tod.map(t => t.coins);
    const eventsData = tod.map(t => t.events_count);

    const maxCoins = Math.max(...coinsData, 1);
    const bgColors = coinsData.map(c => {
        if (c === maxCoins && c > 0) return colors.accentGold;
        return colors.accentPurple + "bb";
    });

    chartTimeOfDayInstance = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Coins",
                data: coinsData,
                backgroundColor: bgColors,
                borderWidth: 0,
                borderRadius: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const idx = ctx.dataIndex;
                            return ` Coins: ${fmtNum(coinsData[idx])} (${fmtEUR(tod[idx].eur_net)} | ${eventsData[idx]} Events)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: colors.gridColor },
                    ticks: {
                        color: colors.mutedColor,
                        font: { size: 10, family: "JetBrains Mono" },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    grid: { color: colors.gridColor },
                    ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                }
            }
        }
    });
}

function renderGiftDistChart(data) {
    const canvas = document.getElementById("chartGiftDist");
    if (!canvas || typeof Chart === "undefined") return;

    if (chartGiftDistInstance) {
        chartGiftDistInstance.destroy();
        chartGiftDistInstance = null;
    }

    const colors = getChartThemeColors();
    const gifts = data.top_gifts || [];

    if (gifts.length === 0) {
        return;
    }

    const top6 = gifts.slice(0, 6);
    const otherCoins = gifts.slice(6).reduce((acc, g) => acc + g.total_coins, 0);

    const labels = top6.map(g => `${g.gift_name} (${fmtNum(g.diamond_count)})`);
    const values = top6.map(g => g.total_coins);
    const bgColors = top6.map((_, i) => colors.palette[i % colors.palette.length]);

    if (otherCoins > 0) {
        labels.push("Andere Geschenke");
        values.push(otherCoins);
        bgColors.push(colors.mutedColor);
    }

    chartGiftDistInstance = new Chart(canvas, {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: bgColors,
                borderColor: colors.isDark ? "#12171f" : "#ffffff",
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "60%",
            plugins: {
                legend: {
                    position: "right",
                    labels: {
                        color: colors.textColor,
                        boxWidth: 12,
                        font: { family: "JetBrains Mono", size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const val = ctx.raw || 0;
                            const total = values.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                            return ` ${ctx.label}: ${fmtNum(val)} Coins (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderTopGiftersChart(data) {
    const canvas = document.getElementById("chartTopGifters");
    if (!canvas || typeof Chart === "undefined") return;

    if (chartTopGiftersInstance) {
        chartTopGiftersInstance.destroy();
        chartTopGiftersInstance = null;
    }

    const colors = getChartThemeColors();
    const gifters = (data.top_gifters || []).slice(0, 10);

    if (gifters.length === 0) {
        return;
    }

    const labels = gifters.map(g => `@${g.sender_username}`);
    const coinsData = gifters.map(g => g.total_coins);
    const eurData = gifters.map(g => g.eur_net);

    chartTopGiftersInstance = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Coins",
                data: coinsData,
                backgroundColor: colors.secondary + "bb",
                borderColor: colors.secondary,
                borderWidth: 1,
                borderRadius: 2,
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const idx = ctx.dataIndex;
                            return ` Coins: ${fmtNum(coinsData[idx])} (${fmtEUR(eurData[idx])} | ${gifters[idx].gifts_sent} Gifts)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: colors.gridColor },
                    ticks: { color: colors.mutedColor, font: { size: 10, family: "JetBrains Mono" } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: colors.textColor, font: { size: 11, family: "JetBrains Mono" } }
                }
            }
        }
    });
}

function renderAnalyticsTables(data) {
    // 1. Top Gifters Table
    const giftersBody = document.getElementById("anGiftersTableBody");
    const giftersMeta = document.getElementById("anGiftersTableMeta");
    const gifters = data.top_gifters || [];
    if (giftersMeta) giftersMeta.textContent = `${gifters.length} Top-Spender`;

    if (giftersBody) {
        if (gifters.length === 0) {
            giftersBody.innerHTML = `<tr><td colspan="6" class="muted">Keine Spenderdaten im gewählten Zeitraum vorhanden.</td></tr>`;
        } else {
            giftersBody.innerHTML = gifters.map(g => {
                const topRankCls = g.rank <= 3 ? "rank-badge top-rank" : "rank-badge";
                const sfBadge = g.is_super_fan ? `<span class="status-tag polling">SF</span>` : "";
                return `
                    <tr>
                        <td><span class="${topRankCls}">${g.rank}</span></td>
                        <td>
                            <strong>@${g.sender_username}</strong> ${sfBadge}
                            ${g.sender_nickname && g.sender_nickname !== g.sender_username ? `<div class="mono muted" style="font-size:11px;">${g.sender_nickname}</div>` : ""}
                        </td>
                        <td class="num-col">${fmtNum(g.gifts_sent)} (${fmtNum(g.transactions)})</td>
                        <td class="num-col"><strong>${fmtNum(g.total_coins)}</strong></td>
                        <td class="num-col"><strong>${fmtEUR(g.eur_net)}</strong></td>
                        <td class="num-col">
                            <div class="pct-bar-wrapper">
                                <span class="pct-pill">${g.pct_of_total}%</span>
                                <span class="pct-bar-fill" style="width:${Math.max(2, Math.min(60, g.pct_of_total * 0.6))}px;"></span>
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");
        }
    }

    // 2. Top Gifts Table
    const giftsBody = document.getElementById("anGiftsTableBody");
    const giftsMeta = document.getElementById("anGiftsTableMeta");
    const gifts = data.top_gifts || [];
    if (giftsMeta) giftsMeta.textContent = `${gifts.length} Geschenke`;

    if (giftsBody) {
        if (gifts.length === 0) {
            giftsBody.innerHTML = `<tr><td colspan="6" class="muted">Keine Geschenk-Daten im gewählten Zeitraum vorhanden.</td></tr>`;
        } else {
            giftsBody.innerHTML = gifts.map(g => {
                return `
                    <tr>
                        <td>
                            <strong>${g.gift_name}</strong>
                            ${g.gift_id ? `<span class="mono muted" style="font-size:10.5px;">(#${g.gift_id})</span>` : ""}
                        </td>
                        <td class="num-col">${fmtNum(g.diamond_count)}</td>
                        <td class="num-col">${fmtNum(g.total_quantity)}x</td>
                        <td class="num-col"><strong>${fmtNum(g.total_coins)}</strong></td>
                        <td class="num-col"><strong>${fmtEUR(g.eur_net)}</strong></td>
                        <td class="num-col">
                            <div class="pct-bar-wrapper">
                                <span class="pct-pill">${g.pct_of_total}%</span>
                                <span class="pct-bar-fill" style="width:${Math.max(2, Math.min(60, g.pct_of_total * 0.6))}px;"></span>
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");
        }
    }

    // 3. Sessions Table
    const sessBody = document.getElementById("anSessionsTableBody");
    const sessMeta = document.getElementById("anSessionsTableMeta");
    const sessions = data.sessions || [];
    if (sessMeta) sessMeta.textContent = `${sessions.length} Sessions`;

    if (sessBody) {
        if (sessions.length === 0) {
            sessBody.innerHTML = `<tr><td colspan="9" class="muted">Keine aufgezeichneten Live-Sessions vorhanden.</td></tr>`;
        } else {
            sessBody.innerHTML = sessions.map(ss => {
                const isLive = ss.status === "active";
                const statusTag = isLive ? `<span class="status-tag live">LIVE</span>` : `<span class="status-tag">BEENDET</span>`;
                const durStr = ss.duration_minutes >= 60
                    ? `${Math.floor(ss.duration_minutes / 60)}h ${ss.duration_minutes % 60}m`
                    : `${ss.duration_minutes}m`;

                return `
                    <tr>
                        <td class="mono muted">#${ss.id}</td>
                        <td>
                            <strong>${ss.streamer_display_name}</strong>
                            <div class="mono muted" style="font-size:11px;">@${ss.streamer_username}</div>
                        </td>
                        <td class="mono">${(ss.started_at || "").replace("T", " ")}</td>
                        <td class="num-col">${durStr}</td>
                        <td class="num-col"><strong>${fmtNum(ss.peak_viewers)}</strong></td>
                        <td>${statusTag}</td>
                        <td class="num-col"><strong>${fmtNum(ss.session_coins)}</strong></td>
                        <td class="num-col"><strong>${fmtEUR(ss.eur_net)}</strong></td>
                        <td class="num-col mono"><strong>${fmtNum(ss.coins_per_hour)}</strong> <span class="muted">/h</span></td>
                    </tr>
                `;
            }).join("");
        }
    }
}

async function loadAnalytics(isBackground = false) {
    try {
        const sidParam = analyticsStreamerId && analyticsStreamerId !== "all" ? `&streamer_id=${encodeURIComponent(analyticsStreamerId)}` : "";
        const res = await fetch(`/api/analytics?period=${encodeURIComponent(analyticsPeriod)}${sidParam}`);
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) return;
        const data = await res.json();
        cachedAnalyticsData = data;

        // KPI updates
        const t = data.totals || {};
        document.getElementById("anNetEur").textContent = fmtEUR(t.eur_net);
        document.getElementById("anNetUsd").textContent = `${fmtUSD(t.usd_net)} USD`;
        document.getElementById("anGrossEur").textContent = fmtEUR(t.eur_gross);
        document.getElementById("anCoins").textContent = fmtNum(t.total_coins);
        document.getElementById("anAvgCoinsPerGift").textContent = `Ø ${fmtNum(t.avg_coins_per_gift)} Coins pro Gift`;
        document.getElementById("anGiftsCount").textContent = `${fmtNum(t.total_gifts_sent)} Gifts`;
        document.getElementById("anGiftEventsCount").textContent = `${fmtNum(t.gift_events_count)} Transaktionen`;
        document.getElementById("anUniqueGifters").textContent = `${fmtNum(t.unique_gifters)} Spender`;
        document.getElementById("anAvgPerGifter").textContent = `Ø ${fmtEUR(t.avg_eur_per_gifter)} pro Spender`;

        document.getElementById("anWhaleTop1").textContent = `${t.whale_share_top1_pct || 0.0}%`;
        document.getElementById("anWhaleTop3").textContent = `${t.whale_share_top3_pct || 0.0}%`;
        document.getElementById("anWhaleTop5").textContent = `${t.whale_share_top5_pct || 0.0}%`;

        const totalMins = t.total_stream_minutes || 0;
        const hoursStr = (totalMins / 60).toFixed(1);
        document.getElementById("anSessionsCount").textContent = `${fmtNum(t.sessions_count || 0)} Sessions`;
        document.getElementById("anStreamDuration").textContent = `${hoursStr} Std. Gesamtlaufzeit`;

        // Streamer Meta Banner
        const banner = document.getElementById("anStreamerMetaBanner");
        const bannerMeta = document.getElementById("anStreamerMeta");
        if (data.selected_streamer) {
            const s = data.selected_streamer;
            const liveBadge = s.is_live ? `<span class="status-tag live">LIVE</span>` : `<span class="status-tag">OFFLINE</span>`;
            banner.style.display = "block";
            bannerMeta.innerHTML = `Auswertung fokussiert auf: <strong>${s.display_name || s.username}</strong> (@${s.username}) · ${liveBadge} · ${fmtNum(s.follower_count)} Follower · Raum-ID: ${s.room_id || "Keine"}`;
        } else {
            banner.style.display = "none";
        }

        renderTimelineChart(data);
        renderCompareChart(data);
        renderTimeOfDayChart(data);
        renderGiftDistChart(data);
        renderTopGiftersChart(data);
        renderAnalyticsTables(data);
    } catch (e) {
        console.error("Fehler beim Laden der Analytics:", e);
    }
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
    setInterval(() => {
        loadOverview();
        if (document.getElementById("tab-analytics")?.classList.contains("active")) {
            loadAnalytics(true);
        }
    }, 4000);

    document.getElementById("periodSelect").addEventListener("change", (e) => {
        currentPeriod = e.target.value;
        loadOverview();
    });

    document.getElementById("selectAnalyticsStreamer")?.addEventListener("change", (e) => {
        analyticsStreamerId = e.target.value;
        loadAnalytics();
    });

    document.getElementById("selectAnalyticsPeriod")?.addEventListener("change", (e) => {
        analyticsPeriod = e.target.value;
        loadAnalytics();
    });

    document.getElementById("btnRefreshAnalytics")?.addEventListener("click", () => {
        loadAnalytics();
    });

    document.getElementById("btnTimelineToggleMetric")?.addEventListener("click", () => {
        toggleTimelineMetric();
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
