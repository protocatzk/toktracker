let currentPeriod = "all";

function fmtEUR(v) {
    return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(v || 0);
}

function fmtUSD(v) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v || 0);
}

function fmtNum(v) {
    return new Intl.NumberFormat("de-DE").format(v || 0);
}

async function loadOverview() {
    try {
        const res = await fetch(`/api/overview?period=${encodeURIComponent(currentPeriod)}`);
        const data = await res.json();

        const t = data.totals;
        document.getElementById("sumNet").textContent = `${fmtEUR(t.eur_net)} / ${fmtUSD(t.usd_net)}`;
        document.getElementById("sumCoins").textContent = fmtNum(t.total_coins);
        document.getElementById("sumGross").textContent = `${fmtEUR(t.eur_gross)} / ${fmtUSD(t.usd_gross)}`;
        document.getElementById("sumGifts").textContent = `${fmtNum(t.total_gifts_sent)} (${fmtNum(t.gift_events_count)} Events)`;

        if (data.system) {
            document.getElementById("sysWorkerInfo").textContent =
                `Worker: ${data.system.workers_running} aktiv (${data.system.workers_connected} verbunden)`;
            renderWorkerLogs(data.system.workers || []);
        }

        if (data.settings) {
            const activeEl = document.activeElement;
            if (!activeEl || !activeEl.id.startsWith("set")) {
                document.getElementById("setUsdPerDiamond").value = data.settings.usd_per_diamond;
                document.getElementById("setGrossUsdPerCoin").value = data.settings.gross_usd_per_coin;
                document.getElementById("setUsdToEur").value = data.settings.usd_to_eur_rate;
                document.getElementById("setPollInterval").value = data.settings.poll_interval_seconds;
            }
        }

        renderStreamerTable(data.streamers || []);
        renderGiftLog(data.recent_gifts || []);
        populateSimulatorSelect(data.streamers || []);
    } catch (e) {
        console.error("Fehler beim Laden:", e);
    }
}

function renderStreamerTable(streamers) {
    const tbody = document.getElementById("streamerTableBody");
    if (streamers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10">Keine Streamer angelegt.</td></tr>`;
        return;
    }

    tbody.innerHTML = streamers
        .map((s) => {
            const diag = s.worker_diagnostics;
            const state = diag ? diag.state : (s.is_live ? "live" : "stopped");
            let tagClass = "";
            if (state === "connected" || s.is_live) tagClass = "live";
            else if (state === "polling_offline" || state === "connecting" || state === "backoff") tagClass = "polling";

            const topGift = s.top_gift
                ? `${s.top_gift.gift_name} (${fmtNum(s.top_gift.coins)})`
                : "-";
            const topGifter = s.top_gifter
                ? `@${s.top_gifter.sender_username} (${fmtNum(s.top_gifter.coins)})`
                : "-";

            const trackBtnText = s.is_tracking_active ? "Stop Worker" : "Start Worker";

            return `
                <tr>
                    <td class="mono">${s.id}</td>
                    <td>
                        <strong><a href="#" onclick="showStreamerDetail(${s.id}); return false;">${s.display_name || s.username}</a></strong><br/>
                        <span class="mono">@${s.username}</span>
                        ${s.room_id ? `<br/><span class="mono">Room: ${s.room_id}</span>` : ""}
                    </td>
                    <td>
                        <span class="status-tag ${tagClass}">${state.toUpperCase()}</span>
                        <div class="mono" style="margin-top:3px;">${s.monitor_status || ""}</div>
                        ${s.last_error ? `<div class="mono" style="color:#b02a37;">${s.last_error}</div>` : ""}
                    </td>
                    <td class="mono">
                        Aktuell: ${fmtNum(s.current_viewers || 0)}<br/>
                        Follower: ${fmtNum(s.follower_count || 0)}
                    </td>
                    <td class="mono">
                        <strong>${fmtNum(s.total_coins)}</strong><br/>
                        (${fmtNum(s.total_gifts_sent)} Gifts / ${s.unique_gifters} Gifter)
                    </td>
                    <td class="mono"><strong>${fmtEUR(s.eur_net)}</strong></td>
                    <td class="mono">${fmtUSD(s.usd_net)}</td>
                    <td class="mono">${fmtEUR(s.eur_gross)}</td>
                    <td class="mono">
                        Gift: ${topGift}<br/>
                        Gifter: ${topGifter}
                    </td>
                    <td>
                        <button type="button" onclick="toggleWorker(${s.id})">${trackBtnText}</button>
                        <button type="button" onclick="showStreamerDetail(${s.id})">Details</button>
                        <a class="btn-link mono" href="/api/v1/streamers/${encodeURIComponent(s.username)}/report?hours=24" target="_blank" title="JSON Einzelabfrage für Telegram Bot">Bot-JSON</a>
                        <button type="button" onclick="refreshStreamer(${s.id})">Profil-Check</button>
                        <button type="button" class="danger" onclick="deleteStreamer(${s.id}, '${s.username}')">X</button>
                    </td>
                </tr>
            `;
        })
        .join("");
}

function renderGiftLog(gifts) {
    const tbody = document.getElementById("giftLogBody");
    if (gifts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7">Keine Geschenke im Zeitraum.</td></tr>`;
        return;
    }

    tbody.innerHTML = gifts
        .map((g) => {
            const ts = (g.created_at || "").replace("T", " ").slice(5, 19);
            return `
                <tr>
                    <td class="mono">${ts}</td>
                    <td class="mono">@${g.streamer_username}</td>
                    <td>${g.sender_nickname || g.sender_username} ${g.is_super_fan ? "[SF]" : ""}</td>
                    <td>${g.repeat_count}x ${g.gift_name}</td>
                    <td class="mono">${fmtNum(g.total_coins)}</td>
                    <td class="mono">${fmtEUR(g.eur_net)}</td>
                    <td class="mono">${g.source}</td>
                </tr>
            `;
        })
        .join("");
}

function renderWorkerLogs(workers) {
    const box = document.getElementById("workerLogBox");
    const lines = [];
    workers.forEach((w) => {
        (w.logs || []).forEach((l) => {
            lines.push(`${l.timestamp} [@${w.username}] [${l.level}] ${l.message}`);
        });
    });
    lines.sort().reverse();
    box.innerHTML = lines.length > 0 ? lines.slice(0, 30).join("<br/>") : "Keine Worker-Logs vorhanden.";
}

function populateSimulatorSelect(streamers) {
    const sel = document.getElementById("simStreamerSelect");
    const prev = sel.value;
    sel.innerHTML =
        `<option value="">Streamer...</option>` +
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
        `Detail-Auswertung: ${s.display_name || s.username} (@${s.username}) – Netto: ${fmtEUR(data.summary.eur_net)} (${fmtNum(data.summary.total_coins)} Coins)`;

    const giftsBody = document.getElementById("detailGiftsBody");
    giftsBody.innerHTML =
        data.gift_breakdown.length === 0
            ? `<tr><td colspan="4">Keine Geschenke.</td></tr>`
            : data.gift_breakdown
                  .map(
                      (g) => `
                <tr>
                    <td>${g.gift_name} (${g.diamond_count})</td>
                    <td class="mono">${fmtNum(g.total_quantity)}x</td>
                    <td class="mono">${fmtNum(g.total_coins)}</td>
                    <td class="mono">${fmtEUR(g.eur_net)}</td>
                </tr>`
                  )
                  .join("");

    const giftersBody = document.getElementById("detailGiftersBody");
    giftersBody.innerHTML =
        data.top_gifters.length === 0
            ? `<tr><td colspan="4">Keine Gifter.</td></tr>`
            : data.top_gifters
                  .map(
                      (tg) => `
                <tr>
                    <td>@${tg.sender_username} ${tg.is_super_fan ? "[SuperFan]" : ""}</td>
                    <td class="mono">${fmtNum(tg.gifts_sent)}</td>
                    <td class="mono">${fmtNum(tg.total_coins)}</td>
                    <td class="mono">${fmtEUR(tg.eur_net)}</td>
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
                          `#${ss.id} [${ss.status}] Start: ${ss.started_at} | Peak Viewers: ${ss.peak_viewers} | Coins: ${fmtNum(ss.session_coins)} (${fmtEUR(ss.eur_net)})`
                  )
                  .join("<br/>");

    document.getElementById("streamerDetailBox").style.display = "block";
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
    loadOverview();
    setInterval(loadOverview, 4000);

    document.getElementById("periodSelect").addEventListener("change", (e) => {
        currentPeriod = e.target.value;
        loadOverview();
    });

    document.getElementById("btnRefresh").addEventListener("click", loadOverview);

    document.getElementById("btnCloseDetail").addEventListener("click", () => {
        document.getElementById("streamerDetailBox").style.display = "none";
    });

    document.getElementById("formAddStreamer").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("inputUsername");
        const autoTrack = document.getElementById("checkAutoTrack").checked;
        const autoReconnect = document.getElementById("checkAutoReconnect").checked;
        const res = await fetch("/api/streamers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: input.value,
                auto_track: autoTrack,
                auto_reconnect: autoReconnect,
            }),
        });
        if (res.ok) {
            input.value = "";
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
        const sender = document.getElementById("simSender").value || "test_viewer";

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
