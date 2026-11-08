/*
 * TokTracker – Read-only Statistik-Dashboard.
 *
 * Bewusst ohne Verwaltungs-, Loesch- oder Buchungsfunktionen. Alle Schreib-
 * operationen bleiben dem Admin-Panel vorbehalten und werden serverseitig
 * durch die Rechte-Matrix geschuetzt.
 */
(function () {
    "use strict";

    var state = {
        period: "24h",
        charts: {},
    };

    function el(id) {
        return document.getElementById(id);
    }

    function setText(id, value) {
        var node = el(id);
        if (node) node.textContent = value;
    }

    function esc(value) {
        return window.escapeHtml ? window.escapeHtml(value) : String(value == null ? "" : value);
    }

    function num(value) {
        return window.fmtNum ? window.fmtNum(value) : String(value || 0);
    }

    function eur(value) {
        return window.fmtEUR ? window.fmtEUR(value) : String(value || 0);
    }

    function usd(value) {
        return window.fmtUSD ? window.fmtUSD(value) : String(value || 0);
    }

    async function fetchJSON(url) {
        var res = await fetch(url, { headers: { Accept: "application/json" } });
        if (res.status === 401) {
            window.location.href = "login?next=/stats";
            throw new Error("unauthorized");
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }
        return res.json();
    }

    function destroyChart(key) {
        if (state.charts[key]) {
            state.charts[key].destroy();
            delete state.charts[key];
        }
    }

    function renderTimeline(timeline) {
        var canvas = el("statsChartTimeline");
        if (!canvas || !window.Chart) return;
        destroyChart("timeline");
        var labels = (timeline || []).map(function (row) { return row.label; });
        var values = (timeline || []).map(function (row) { return Number(row.eur_net || 0); });
        state.charts.timeline = new window.Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Netto EUR",
                    data: values,
                    borderColor: "#38bdf8",
                    backgroundColor: "rgba(56, 189, 248, 0.16)",
                    fill: true,
                    tension: 0.32,
                    pointRadius: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: "rgba(148, 163, 184, 0.12)" }, ticks: { maxTicksLimit: 10 } },
                    y: { beginAtZero: true, grid: { color: "rgba(148, 163, 184, 0.12)" } },
                },
            },
        });
    }

    function renderTopGifts(topGifts) {
        var canvas = el("statsChartTopGifts");
        if (!canvas || !window.Chart) return;
        destroyChart("topGifts");
        var rows = (topGifts || []).slice(0, 8);
        state.charts.topGifts = new window.Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels: rows.map(function (row) { return row.gift_name; }),
                datasets: [{
                    label: "Coins",
                    data: rows.map(function (row) { return Number(row.total_coins || 0); }),
                    backgroundColor: "rgba(168, 85, 247, 0.65)",
                    borderColor: "#a855f7",
                    borderWidth: 1,
                    borderRadius: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
                    y: { beginAtZero: true, grid: { color: "rgba(148, 163, 184, 0.12)" } },
                },
            },
        });
    }

    function renderStreamers(streamers) {
        var body = el("statsStreamerBody");
        if (!body) return;
        var list = streamers || [];
        setText("statsStreamerMeta", list.length + " Einträge");
        if (!list.length) {
            body.innerHTML = '<tr><td colspan="7">Keine Streamer vorhanden.</td></tr>';
            return;
        }
        body.innerHTML = list.map(function (s) {
            var name = s.display_name || s.username || "–";
            var uname = s.username || "–";
            var status = s.is_live ? "🟢 LIVE" : (s.is_tracking_active ? "⚪ Tracking" : "⚪ Offline");
            var topGift = s.top_gift
                ? esc(s.top_gift.gift_name) + " · " + num(s.top_gift.coins) + " Coins"
                : "–";
            return (
                "<tr>" +
                '<td><div class="stats-streamer-cell">' +
                '<img src="' + esc(s.avatar_url || "static/avatar_default.png") + '" alt="" class="stats-streamer-avatar" onerror="this.src=\'static/avatar_default.png\'" />' +
                "<div><strong>" + esc(name) + "</strong><span>@" + esc(uname) + "</span></div>" +
                "</div></td>" +
                "<td class=\"hide-sm\">" + status + "</td>" +
                '<td class="num-col">' + num(s.current_viewers) + "</td>" +
                '<td class="num-col">' + num(s.total_coins) + "</td>" +
                '<td class="num-col">' + eur(s.eur_net) + "</td>" +
                '<td class="num-col hide-sm">' + eur(s.eur_gross) + "</td>" +
                '<td class="hide-sm">' + topGift + "</td>" +
                "</tr>"
            );
        }).join("");
    }

    function renderOverview(data) {
        var totals = (data && data.totals) || {};
        setText("statsNetEur", eur(totals.eur_net));
        setText("statsNetUsd", usd(totals.usd_net));
        setText("statsCoins", num(totals.total_coins));
        setText("statsStreamersSub", num(totals.streamer_count) + " Streamer (" + num(totals.live_count) + " live)");
        setText("statsGrossEur", eur(totals.eur_gross));
        setText("statsGrossUsd", usd(totals.usd_gross));
        setText("statsGifts", num(totals.total_gifts_sent));
        setText("statsGiftEvents", num(totals.gift_events_count) + " Transaktionen");
        renderStreamers(data && data.streamers);
    }

    function renderAnalytics(data) {
        renderTimeline(data && data.timeline);
        renderTopGifts(data && data.top_gifts);
    }

    function renderBattles(data) {
        data = data || {};
        setText("statsBattlesTotal", num(data.total_battles));
        setText("statsBattlesSub", num(data.ongoing) + " aktiv");
        setText("statsBattleWinrate", (Number(data.winrate_pct || 0)).toFixed(1).replace(".", ",") + " %");
        setText("statsBattleWinLoss", num(data.wins) + "S / " + num(data.losses) + "N / " + num(data.draws) + "U");
        setText("statsBattleEur", eur(data.total_eur_net));
        setText("statsBattleCoins", num(data.total_coins) + " Coins");
        var rival = data.top_opponent;
        setText("statsTopRival", rival ? ("@" + (rival.opponent_username || "–")) : "–");
        setText("statsTopRivalSub", rival ? (num(rival.matches_count) + " Duelle · " + (Number(rival.winrate_pct || 0)).toFixed(1).replace(".", ",") + " % Siege") : "Keine Duelle");
    }

    function renderSiteAnalytics(data) {
        var kpis = (data && data.kpis) || {};
        setText("statsViews", num(kpis.total_views));
        setText("statsVisitors", num(kpis.unique_visitors));
        setText("statsBotSessions", num((data && data.bot_sessions || []).length));
        setText("statsLatency", num(kpis.avg_latency) + " ms");
    }

    function renderSystem(data) {
        data = data || {};
        setText("statsActiveWorkers", num(data.workers_running));
        setText("statsWorkerCount", num(data.workers_total));
        var bot = data.telegram_bot || {};
        setText("statsBotState", "Telegram-Bot: " + String(bot.state || "offline").toUpperCase());
    }

    function renderHealth(data) {
        data = data || {};
        var db = data.database === "ok" ? "OK" : "Fehler";
        var bus = data.bus === "ok" ? "OK" : "Fehler";
        setText("statsDbState", db);
        setText("statsBusState", bus);
    }

    async function loadAll() {
        var period = state.period;
        var results = await Promise.allSettled([
            fetchJSON("api/overview?period=" + encodeURIComponent(period)),
            fetchJSON("api/analytics?period=" + encodeURIComponent(period)),
            fetchJSON("api/battles/stats?period=" + encodeURIComponent(period)),
            fetchJSON("api/site-analytics?period=" + encodeURIComponent(period)),
            fetchJSON("api/system/status"),
            fetchJSON("api/health"),
        ]);

        if (results[0].status === "fulfilled") renderOverview(results[0].value);
        if (results[1].status === "fulfilled") renderAnalytics(results[1].value);
        if (results[2].status === "fulfilled") renderBattles(results[2].value);
        if (results[3].status === "fulfilled") renderSiteAnalytics(results[3].value);
        if (results[4].status === "fulfilled") renderSystem(results[4].value);
        if (results[5].status === "fulfilled") renderHealth(results[5].value);

        setText("statsLastUpdate", new Date().toLocaleTimeString("de-DE"));
    }

    function bindEvents() {
        var periodSelect = el("statsPeriod");
        if (periodSelect) {
            periodSelect.addEventListener("change", function () {
                state.period = periodSelect.value;
                loadAll().catch(function (err) {
                    console.error("Statistiken konnten nicht geladen werden:", err);
                });
            });
        }

        var refreshBtn = el("statsBtnRefresh");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () {
                loadAll().catch(function (err) {
                    console.error("Statistiken konnten nicht geladen werden:", err);
                });
            });
        }

        var themeBtn = el("btnThemeToggle");
        var savedTheme = "dark";
        try {
            savedTheme = localStorage.getItem("toktracker_theme") || "dark";
        } catch (e) {}
        if (window.applyTheme) window.applyTheme(savedTheme);
        if (themeBtn) {
            themeBtn.addEventListener("click", function () {
                var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
                if (window.applyTheme) window.applyTheme(next);
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindEvents();
        loadAll().catch(function (err) {
            console.error("Statistiken konnten nicht geladen werden:", err);
        });
    });
})();
