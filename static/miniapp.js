/* =====================================================================
   toktracker Telegram Mini-App Client Logic v2.2.0
   Mobile-First Real-Time Feed, Public Analytics & Admin Control Panel
   ===================================================================== */

(function () {
    "use strict";

    // 1. Telegram WebApp Integration
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    if (tg) {
        try {
            tg.ready();
            tg.expand();
            if (tg.setHeaderColor) {
                tg.setHeaderColor("#0b0e14");
            }
            if (tg.setBackgroundColor) {
                tg.setBackgroundColor("#0b0e14");
            }
        } catch (e) {
            console.warn("Telegram WebApp init hint:", e);
        }
    }

    // State
    let currentPeriod = "24h";
    let activeTab = "tab-matches";
    let pollInterval = null;
    let isFetching = false;
    let isAdmin = false;
    let authUser = null;
    let sessionToken = localStorage.getItem("toktracker_admin_token") || "";
    let cachedStreamers = [];
    let selectedAnalyticsStreamer = "all";
    let analyticsMetric = "both";
    let analyticsChartType = "line";
    let cachedAnalyticsData = null;
    let analyticsLoadedOnce = false;
    let lastAnalyticsFingerprint = null;

    // Chart.js Instances
    let chartTimelineInstance = null;
    let chartStreamerCompareInstance = null;
    let chartGiftDistInstance = null;
    let chartTimeOfDayInstance = null;

    // Cache DOM Elements
    const elements = {
        btnRefresh: document.getElementById("maBtnRefresh"),
        periodPills: document.querySelectorAll(".period-pill"),
        navTabs: document.querySelectorAll(".nav-tab-btn"),
        tabViews: document.querySelectorAll(".ma-tab-view"),
        headerAdminBadge: document.getElementById("maHeaderAdminBadge"),

        // KPIs
        kpiNetEur: document.getElementById("kpiNetEur"),
        kpiNetUsd: document.getElementById("kpiNetUsd"),
        kpiCoins: document.getElementById("kpiCoins"),
        kpiGifts: document.getElementById("kpiGifts"),
        kpiLiveCount: document.getElementById("kpiLiveCount"),
        liveBanner: document.getElementById("maLiveBanner"),
        liveBannerText: document.getElementById("maLiveBannerText"),

        // Containers
        liveBattlesContainer: document.getElementById("maLiveBattlesContainer"),
        recentBattlesContainer: document.getElementById("maRecentBattlesContainer"),
        streamersContainer: document.getElementById("maStreamersContainer"),
        giftsContainer: document.getElementById("maGiftsContainer"),

        // Analytics Elements
        analyticsStreamerSelect: document.getElementById("maAnalyticsStreamerSelect"),
        kpiUniqueGifters: document.getElementById("maKpiUniqueGifters"),
        kpiAvgPerGifter: document.getElementById("maKpiAvgPerGifter"),
        kpiAvgCoinsGift: document.getElementById("maKpiAvgCoinsGift"),
        kpiWhaleShare: document.getElementById("maKpiWhaleShare"),
        kpiGrossRevenue: document.getElementById("maKpiGrossRevenue"),
        kpiNetQuote: document.getElementById("maKpiNetQuote"),
        kpiTotalEvents: document.getElementById("maKpiTotalEvents"),
        kpiCadence: document.getElementById("maKpiCadence"),
        metricSelect: document.getElementById("maTimelineMetricSelect"),
        metricPills: document.querySelectorAll(".ma-metric-pill"),
        timelineTitle: document.getElementById("maTimelineTitle"),
        timelineSub: document.getElementById("maTimelineSub"),
        btnChartLine: document.getElementById("maBtnChartLine"),
        btnChartBar: document.getElementById("maBtnChartBar"),
        btnChartArea: document.getElementById("maBtnChartArea"),
        statPeak: document.getElementById("maStatPeak"),
        statAvg: document.getElementById("maStatAvg"),
        statTotal: document.getElementById("maStatTotal"),
        chartTimeline: document.getElementById("maChartTimeline"),
        chartStreamerCompare: document.getElementById("maChartStreamerCompare"),
        topGiftersContainer: document.getElementById("maTopGiftersContainer"),
        chartGiftDist: document.getElementById("maChartGiftDist"),
        topGiftsList: document.getElementById("maTopGiftsList"),
        chartTimeOfDay: document.getElementById("maChartTimeOfDay"),

        // Admin Elements
        adminAuthGate: document.getElementById("maAdminAuthGate"),
        adminContent: document.getElementById("maAdminContent"),
        authGateMsg: document.getElementById("maAuthGateMsg"),
        otpCodeInput: document.getElementById("maOtpCodeInput"),
        btnSubmitOtp: document.getElementById("maBtnSubmitOtp"),
        btnRequestOtp: document.getElementById("maBtnRequestOtp"),
        adminUserLabel: document.getElementById("maAdminUserLabel"),
        btnAdminLogout: document.getElementById("maBtnAdminLogout"),
        adminStreamersContainer: document.getElementById("maAdminStreamersContainer"),

        // Admin Diagnostic Elements
        diagDbEngine: document.getElementById("maDiagDbEngine"),
        diagActiveWorkers: document.getElementById("maDiagActiveWorkers"),
        diagBotStatus: document.getElementById("maDiagBotStatus"),
        diagTiktokSession: document.getElementById("maDiagTiktokSession"),

        // Admin Action Buttons
        btnOpenAddStreamer: document.getElementById("maBtnOpenAddStreamer"),
        btnOpenAddGift: document.getElementById("maBtnOpenAddGift"),
        btnOpenSettings: document.getElementById("maBtnOpenSettings"),
        btnOpenWhitelist: document.getElementById("maBtnOpenWhitelist"),

        // Modals
        modalAddStreamer: document.getElementById("modalAddStreamer"),
        modalAddGift: document.getElementById("modalAddGift"),
        modalSettings: document.getElementById("modalSettings"),
        modalWhitelist: document.getElementById("modalWhitelist"),

        // Modal Form Controls
        inputAddStreamerUsername: document.getElementById("inputAddStreamerUsername"),
        inputAddStreamerDisplayName: document.getElementById("inputAddStreamerDisplayName"),
        checkAddStreamerAutoTrack: document.getElementById("checkAddStreamerAutoTrack"),
        checkAddStreamerAutoReconnect: document.getElementById("checkAddStreamerAutoReconnect"),
        btnSubmitAddStreamer: document.getElementById("btnSubmitAddStreamer"),

        selectAddGiftStreamer: document.getElementById("selectAddGiftStreamer"),
        inputAddGiftName: document.getElementById("inputAddGiftName"),
        inputAddGiftCoins: document.getElementById("inputAddGiftCoins"),
        inputAddGiftCount: document.getElementById("inputAddGiftCount"),
        inputAddGiftSender: document.getElementById("inputAddGiftSender"),
        btnSubmitAddGift: document.getElementById("btnSubmitAddGift"),

        inputSettingsUsdDiamond: document.getElementById("inputSettingsUsdDiamond"),
        inputSettingsGrossCoin: document.getElementById("inputSettingsGrossCoin"),
        inputSettingsUsdToEur: document.getElementById("inputSettingsUsdToEur"),
        selectSettingsCurrency: document.getElementById("selectSettingsCurrency"),
        selectSettingsTgMode: document.getElementById("selectSettingsTgMode"),
        btnSubmitSettings: document.getElementById("btnSubmitSettings"),

        inputAddTgUserIdent: document.getElementById("inputAddTgUserIdent"),
        selectAddTgUserRole: document.getElementById("selectAddTgUserRole"),
        btnSubmitAddTgUser: document.getElementById("btnSubmitAddTgUser"),
        whitelistUsersContainer: document.getElementById("maWhitelistUsersContainer"),

        toastContainer: document.getElementById("maToastContainer"),
    };

    // Formatters
    function formatNumber(num) {
        return new Intl.NumberFormat("de-DE").format(Math.round(num || 0));
    }

    function formatCurrency(val, currency = "EUR") {
        return new Intl.NumberFormat("de-DE", {
            style: "currency",
            currency: currency,
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(val || 0);
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function getRelativeTime(timestamp) {
        if (!timestamp) return "";
        try {
            const date = new Date(timestamp);
            const now = new Date();
            const diffSec = Math.floor((now - date) / 1000);
            if (diffSec < 60) return "gerade eben";
            if (diffSec < 3600) return `vor ${Math.floor(diffSec / 60)}m`;
            if (diffSec < 86400) return `vor ${Math.floor(diffSec / 3600)}h`;
            return date.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
        } catch (e) {
            return timestamp;
        }
    }

    function triggerHaptic(type = "light") {
        if (tg && tg.HapticFeedback) {
            try {
                if (type === "light" || type === "medium" || type === "heavy") {
                    tg.HapticFeedback.impactOccurred(type);
                } else if (type === "success" || type === "error" || type === "warning") {
                    tg.HapticFeedback.notificationOccurred(type);
                }
            } catch (e) {}
        }
    }

    function showToast(msg, type = "success") {
        if (!elements.toastContainer) return;
        const toast = document.createElement("div");
        toast.className = `ma-toast ${type}`;
        toast.textContent = msg;
        elements.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(12px)";
            setTimeout(() => toast.remove(), 200);
        }, 3200);
    }

    function openModal(el) {
        if (!el) return;
        triggerHaptic("light");
        el.classList.add("open");
    }

    function closeModal(el) {
        if (!el) return;
        triggerHaptic("light");
        el.classList.remove("open");
    }

    function getAuthHeaders() {
        const headers = { "Accept": "application/json" };
        if (sessionToken) {
            headers["X-Admin-Session"] = sessionToken;
        }
        return headers;
    }

    // =====================================================================
    // 2. AUTHENTICATION & SESSION MANAGEMENT
    // =====================================================================
    async function initAuth() {
        // Step A: Telegram Native WebApp initData
        if (tg && tg.initData) {
            try {
                const res = await fetch("/api/miniapp/auth", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Accept": "application/json" },
                    body: JSON.stringify({ init_data: tg.initData })
                });
                if (res.ok) {
                    const data = await res.json();
                    isAdmin = !!data.is_admin;
                    authUser = data.user;
                    if (data.token) {
                        sessionToken = data.token;
                        localStorage.setItem("toktracker_admin_token", sessionToken);
                    }
                    updateAdminUI();
                    return;
                }
            } catch (err) {
                console.warn("Telegram WebApp Auth Fehler:", err);
            }
        }

        // Step B: Check stored session token / cookie status
        try {
            const res = await fetch("/api/miniapp/auth/status", {
                headers: getAuthHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                isAdmin = !!data.is_admin;
                authUser = { username: data.admin_label || "Admin" };
            } else {
                isAdmin = false;
            }
        } catch (e) {
            isAdmin = false;
        }
        updateAdminUI();
    }

    function updateAdminUI() {
        if (elements.headerAdminBadge) {
            elements.headerAdminBadge.style.display = isAdmin ? "inline-block" : "none";
        }

        if (isAdmin) {
            if (elements.adminAuthGate) elements.adminAuthGate.style.display = "none";
            if (elements.adminContent) elements.adminContent.style.display = "block";
            if (elements.adminUserLabel) {
                const name = authUser && (authUser.username ? `@${authUser.username}` : (authUser.first_name || authUser.id)) || "Admin";
                elements.adminUserLabel.textContent = name;
            }
            if (activeTab === "tab-admin") {
                loadAdminData();
            }
        } else {
            if (elements.adminAuthGate) elements.adminAuthGate.style.display = "block";
            if (elements.adminContent) elements.adminContent.style.display = "none";
            if (elements.authGateMsg) {
                if (authUser && authUser.username) {
                    elements.authGateMsg.textContent = `Angemeldet als @${authUser.username} (Zuschauer-Rolle ohne Admin-Rechte).`;
                } else {
                    elements.authGateMsg.textContent = "Dieser Bereich erfordert Administrator-Rechte.";
                }
            }
        }
    }

    // =====================================================================
    // 3. DATA FETCHING (FEED & OVERVIEW)
    // =====================================================================
    async function fetchMiniAppData() {
        if (isFetching) return;
        isFetching = true;
        if (elements.btnRefresh) elements.btnRefresh.classList.add("spinning");

        try {
            const res = await fetch(`/api/miniapp/data?period=${encodeURIComponent(currentPeriod)}`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            renderMiniApp(data);
        } catch (err) {
            console.error("Mini-App Fetch Fehler:", err);
        } finally {
            isFetching = false;
            if (elements.btnRefresh) elements.btnRefresh.classList.remove("spinning");
        }
    }

    function renderMiniApp(data) {
        const totals = data.totals || {};
        const streamers = data.streamers || [];
        cachedStreamers = streamers;
        const liveBattles = data.live_battles || [];
        const recentBattles = data.recent_battles || [];
        const recentGifts = data.recent_gifts || [];

        // 1. KPIs
        const netEur = totals.eur_net !== undefined ? totals.eur_net : (totals.total_eur_net || 0);
        const netUsd = totals.usd_net !== undefined ? totals.usd_net : (totals.total_usd_net || 0);
        if (elements.kpiNetEur) elements.kpiNetEur.textContent = formatCurrency(netEur, "EUR");
        if (elements.kpiNetUsd) elements.kpiNetUsd.textContent = `$${formatNumber(netUsd)} USD`;
        if (elements.kpiCoins) elements.kpiCoins.textContent = formatNumber(totals.total_coins);
        if (elements.kpiGifts) elements.kpiGifts.textContent = formatNumber(totals.total_gifts_sent || totals.gift_events_count);

        const liveCount = streamers.filter(s => s.is_live).length;
        if (elements.kpiLiveCount) elements.kpiLiveCount.textContent = `${liveCount} LIVE`;

        // 2. Live Banner Status
        if (elements.liveBanner && elements.liveBannerText) {
            if (liveBattles.length > 0) {
                elements.liveBanner.className = "ma-live-banner";
                elements.liveBannerText.textContent = `⚡ JETZT: ${liveBattles.length} Battle(s) LIVE im Gange!`;
            } else if (liveCount > 0) {
                elements.liveBanner.className = "ma-live-banner";
                elements.liveBannerText.textContent = `🟢 ${liveCount} Streamer aktiv LIVE auf Sendung`;
            } else {
                elements.liveBanner.className = "ma-live-banner no-active";
                elements.liveBannerText.textContent = `💤 Aktuell keine Streamer LIVE – Auto-Monitor aktiv`;
            }
        }

        // 3. Render Views
        renderLiveBattles(liveBattles);
        renderRecentBattles(recentBattles);
        renderStreamers(streamers);
        renderGifts(recentGifts);
        populateStreamerSelects(streamers);

        // Update active tab data if needed
        if (activeTab === "tab-analytics") {
            if (analyticsLoadedOnce) {
                fetchAnalyticsData(true);
            }
        } else if (activeTab === "tab-admin" && isAdmin) {
            renderAdminStreamers(streamers);
        }
    }

    function renderLiveBattles(liveBattles) {
        if (!elements.liveBattlesContainer) return;
        if (!liveBattles || liveBattles.length === 0) {
            elements.liveBattlesContainer.innerHTML = "";
            return;
        }

        let html = '<div class="section-head"><div class="section-title">🔴 LIVE DUELL</div></div>';
        liveBattles.forEach(item => {
            const b = item.battle || {};
            const mode = b.battle_mode || "1v1";
            const sName = item.display_name || item.username;
            const sAvatar = item.avatar_url || "/static/avatar_default.png";
            const oName = b.opponent_display_name || b.opponent_username || "Gegner";
            const oAvatar = b.opponent_avatar_url || "/static/avatar_default.png";

            const sScore = b.streamer_score || 0;
            const oScore = b.opponent_score || 0;
            const totalScore = Math.max(1, sScore + oScore);
            const sPct = Math.round((sScore / totalScore) * 100);
            const oPct = 100 - sPct;

            html += `
                <div class="battle-card-mobile active-match">
                    <div class="battle-card-header">
                        <span class="match-mode-pill mode-${escapeHtml(mode)}">${escapeHtml(mode.toUpperCase())}</span>
                        <span class="match-result-badge live">LIVE DUELL</span>
                    </div>

                    <div class="battle-arena-1v1">
                        <div class="combatant-side">
                            <div class="combatant-avatar-wrap">
                                <img src="${escapeHtml(sAvatar)}" class="combatant-avatar ${sScore >= oScore ? 'winner-glow' : ''}" onerror="this.src='/static/avatar_default.png'">
                            </div>
                            <div class="combatant-name">${escapeHtml(sName)}</div>
                            <div class="combatant-score" style="color: #38bdf8;">${formatNumber(sScore)}</div>
                        </div>

                        <div class="vs-center-mobile"><span class="vs-text">VS</span></div>

                        <div class="combatant-side">
                            <div class="combatant-avatar-wrap">
                                <img src="${escapeHtml(oAvatar)}" class="combatant-avatar ${oScore >= sScore ? 'winner-glow' : ''}" onerror="this.src='/static/avatar_default.png'">
                            </div>
                            <div class="combatant-name">${escapeHtml(oName)}</div>
                            <div class="combatant-score" style="color: #ef4444;">${formatNumber(oScore)}</div>
                        </div>
                    </div>

                    <div class="duel-score-bar-mobile">
                        <div class="bar-side-left" style="width: ${sPct}%;"></div>
                        <div class="bar-side-right" style="width: ${oPct}%;"></div>
                    </div>

                    <div class="battle-card-footer">
                        <span>Punkte-Vorsprung: ${formatNumber(Math.abs(sScore - oScore))}</span>
                        <span class="battle-earnings-badge">LIVE BATTLE</span>
                    </div>
                </div>
            `;
        });
        elements.liveBattlesContainer.innerHTML = html;
    }

    function renderRecentBattles(battles) {
        if (!elements.recentBattlesContainer) return;
        if (!battles || battles.length === 0) {
            elements.recentBattlesContainer.innerHTML = `
                <div class="ma-empty-state">
                    <div class="ma-empty-icon">⚔️</div>
                    <div>Noch keine Matches im gewählten Zeitraum erfasst.</div>
                </div>
            `;
            return;
        }

        let html = "";
        battles.forEach(b => {
            const mode = b.battle_mode || "1v1";
            const res = (b.result || "DRAW").toUpperCase();
            const resClass = res === "WIN" ? "win" : (res === "LOSE" ? "lose" : "draw");
            const resLabel = res === "WIN" ? "SIEG" : (res === "LOSE" ? "NIEDERLAGE" : "UNENTSCHIEDEN");

            const sName = b.streamer_display_name || b.streamer_username || "Streamer";
            const sAvatar = b.streamer_avatar_url || "/static/avatar_default.png";
            const sScore = b.streamer_score || 0;
            const relTime = getRelativeTime(b.started_at || b.created_at);

            const oName = b.opponent_display_name || b.opponent_username || "Gegner";
            const oAvatar = b.opponent_avatar_url || "/static/avatar_default.png";
            const oScore = b.opponent_score || 0;

            const totalScore = Math.max(1, sScore + oScore);
            const sPct = Math.round((sScore / totalScore) * 100);
            const oPct = 100 - sPct;

            html += `
                <div class="battle-card-mobile">
                    <div class="battle-card-header">
                        <span class="match-mode-pill mode-${escapeHtml(mode)}">${escapeHtml(mode.toUpperCase())}</span>
                        <span class="match-result-badge ${resClass}">${resLabel}</span>
                    </div>

                    <div class="battle-arena-1v1">
                        <div class="combatant-side">
                            <div class="combatant-avatar-wrap">
                                <img src="${escapeHtml(sAvatar)}" class="combatant-avatar ${res === 'WIN' ? 'winner-glow' : ''}" onerror="this.src='/static/avatar_default.png'">
                            </div>
                            <div class="combatant-name">${escapeHtml(sName)}</div>
                            <div class="combatant-score" style="color: #38bdf8;">${formatNumber(sScore)}</div>
                        </div>

                        <div class="vs-center-mobile"><span class="vs-text">VS</span></div>

                        <div class="combatant-side">
                            <div class="combatant-avatar-wrap">
                                <img src="${escapeHtml(oAvatar)}" class="combatant-avatar ${res === 'LOSE' ? 'winner-glow' : ''}" onerror="this.src='/static/avatar_default.png'">
                            </div>
                            <div class="combatant-name">${escapeHtml(oName)}</div>
                            <div class="combatant-score" style="color: #ef4444;">${formatNumber(oScore)}</div>
                        </div>
                    </div>

                    <div class="duel-score-bar-mobile">
                        <div class="bar-side-left" style="width: ${sPct}%;"></div>
                        <div class="bar-side-right" style="width: ${oPct}%;"></div>
                    </div>

                    <div class="battle-card-footer">
                        <span>${relTime} · ${formatNumber(b.coins_earned || 0)} Coins</span>
                        <span class="battle-earnings-badge">+${formatCurrency(b.eur_net, "EUR")}</span>
                    </div>
                </div>
            `;
        });
        elements.recentBattlesContainer.innerHTML = html;
    }

    function renderStreamers(streamers) {
        if (!elements.streamersContainer) return;
        if (!streamers || streamers.length === 0) {
            elements.streamersContainer.innerHTML = `
                <div class="ma-empty-state">
                    <div class="ma-empty-icon">👥</div>
                    <div>Keine Streamer im TokTracker hinterlegt.</div>
                </div>
            `;
            return;
        }

        let html = "";
        streamers.forEach(s => {
            const avatar = s.avatar_url || "/static/avatar_default.png";
            const name = s.display_name || s.username;
            const viewers = s.is_live ? `${formatNumber(s.current_viewers)} Zuschauer` : "Offline";

            html += `
                <div class="streamer-card-mobile ${s.is_live ? 'is-live' : ''}">
                    <div class="streamer-info-left">
                        <div class="streamer-avatar-box">
                            <img src="${escapeHtml(avatar)}" class="streamer-avatar-ma" onerror="this.src='/static/avatar_default.png'">
                            ${s.is_live ? '<span class="streamer-live-dot"></span>' : ''}
                        </div>
                        <div class="streamer-text-col">
                            <div class="streamer-title">${escapeHtml(name)}</div>
                            <div class="streamer-subtitle">@${escapeHtml(s.username)} · ${viewers}</div>
                        </div>
                    </div>

                    <div class="streamer-financials-right">
                        <div class="streamer-eur-net">${formatCurrency(s.eur_net, "EUR")}</div>
                        <div class="streamer-coins">${formatNumber(s.total_coins)} Coins</div>
                    </div>
                </div>
            `;
        });
        elements.streamersContainer.innerHTML = html;
    }

    function renderGifts(gifts) {
        if (!elements.giftsContainer) return;
        if (!gifts || gifts.length === 0) {
            elements.giftsContainer.innerHTML = `
                <div class="ma-empty-state">
                    <div class="ma-empty-icon">🎁</div>
                    <div>Keine Geschenke im ausgewählten Zeitraum erfasst.</div>
                </div>
            `;
            return;
        }

        let html = "";
        gifts.forEach(g => {
            const relTime = getRelativeTime(g.created_at);
            const count = g.repeat_count > 1 ? `${g.repeat_count}x ` : "";

            html += `
                <div class="gift-item-mobile">
                    <div class="gift-sender-info">
                        <div class="gift-icon-placeholder">🎁</div>
                        <div class="gift-text-wrap">
                            <div class="gift-sender-name">${escapeHtml(g.sender_username || 'Anonym')}</div>
                            <div class="gift-target-streamer">${count}${escapeHtml(g.gift_name)} → @${escapeHtml(g.streamer_username)} · ${relTime}</div>
                        </div>
                    </div>
                    <div class="gift-coins-val">+${formatNumber(g.total_coins)} Coins</div>
                </div>
            `;
        });
        elements.giftsContainer.innerHTML = html;
    }

    function populateStreamerSelects(streamers) {
        if (elements.analyticsStreamerSelect) {
            const currentVal = elements.analyticsStreamerSelect.value;
            let optHtml = '<option value="all">Alle Streamer</option>';
            streamers.forEach(s => {
                optHtml += `<option value="${s.id}">@${escapeHtml(s.username)}</option>`;
            });
            elements.analyticsStreamerSelect.innerHTML = optHtml;
            if (currentVal) elements.analyticsStreamerSelect.value = currentVal;
        }

        if (elements.selectAddGiftStreamer) {
            let optHtml = "";
            streamers.forEach(s => {
                optHtml += `<option value="${s.id}">@${escapeHtml(s.username)} (${escapeHtml(s.display_name)})</option>`;
            });
            elements.selectAddGiftStreamer.innerHTML = optHtml;
        }
    }

    // =====================================================================
    // 4. PUBLIC ANALYTICS & CHARTS
    // =====================================================================
    function updateAnalyticsTimestamp() {
        const el = document.getElementById("maAnalyticsTimestamp");
        if (el) {
            const d = new Date();
            const timeStr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            el.textContent = `Stand: ${timeStr}`;
        }
    }

    async function fetchAnalyticsData(isBackground = false) {
        try {
            const sid = selectedAnalyticsStreamer !== "all" ? `&streamer_id=${encodeURIComponent(selectedAnalyticsStreamer)}` : "";
            const res = await fetch(`/api/miniapp/analytics?period=${encodeURIComponent(currentPeriod)}${sid}`, {
                headers: { "Accept": "application/json" }
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            renderAnalytics(data, isBackground);
        } catch (err) {
            console.error("Analytics Fetch Fehler:", err);
        }
    }

    function renderAnalytics(data, isBackground = false) {
        if (typeof Chart === "undefined") {
            console.warn("Chart.js noch nicht geladen");
            return;
        }

        const totals = data.totals || {};
        const fingerprint = `${totals.total_coins}_${totals.gift_events_count}_${totals.unique_gifters}_${(data.timeline || []).length}_${currentPeriod}_${selectedAnalyticsStreamer}_${analyticsMetric}_${analyticsChartType}`;
        if (isBackground && lastAnalyticsFingerprint === fingerprint) {
            updateAnalyticsTimestamp();
            return;
        }
        lastAnalyticsFingerprint = fingerprint;

        cachedAnalyticsData = data;
        updateAnalyticsTimestamp();

        // 1. Render Mini KPIs (4-Card 2x2 Grid)
        if (elements.kpiUniqueGifters) elements.kpiUniqueGifters.textContent = formatNumber(totals.unique_gifters || 0);
        if (elements.kpiAvgPerGifter) elements.kpiAvgPerGifter.textContent = `Ø ${formatCurrency(totals.avg_eur_per_gifter)} / Spender`;
        if (elements.kpiAvgCoinsGift) elements.kpiAvgCoinsGift.textContent = `${formatNumber(totals.avg_coins_per_gift)} Coins`;
        if (elements.kpiWhaleShare) elements.kpiWhaleShare.textContent = `Top 5: ${totals.whale_share_top5_pct || 0}% Anteil`;
        if (elements.kpiGrossRevenue) elements.kpiGrossRevenue.textContent = formatCurrency(totals.eur_gross || 0);
        if (elements.kpiNetQuote) {
            const netQuote = (totals.eur_gross && totals.eur_gross > 0)
                ? (Math.round((totals.eur_net / totals.eur_gross) * 1000) / 10)
                : 0;
            elements.kpiNetQuote.textContent = `Netto-Quote: ${netQuote}%`;
        }
        if (elements.kpiTotalEvents) elements.kpiTotalEvents.textContent = formatNumber(totals.gift_events_count || 0);
        if (elements.kpiCadence) elements.kpiCadence.textContent = `${formatNumber(totals.total_gifts_sent || 0)} Geschenke gesamt`;

        // 2. Timeline Chart (Multi-Metric Deep-Dive)
        renderTimelineChart();

        // 3. Streamer Revenue Comparison
        renderStreamerCompareChart(data.streamers_ranking || []);

        // 4. Top Gifters Leaderboard
        renderTopGifters(data.top_gifters || []);

        // 5. Top Gifts Distribution
        renderGiftDistChart(data.top_gifts || []);

        // 6. Time of Day Pattern
        renderTimeOfDayChart(data.time_of_day || []);
    }

    function createChartGradient(ctx, hexColor) {
        try {
            const gradient = ctx.createLinearGradient(0, 0, 0, 240);
            let r = 56, g = 189, b = 248;
            if (hexColor && hexColor.startsWith("#") && hexColor.length === 7) {
                r = parseInt(hexColor.slice(1, 3), 16);
                g = parseInt(hexColor.slice(3, 5), 16);
                b = parseInt(hexColor.slice(5, 7), 16);
            }
            gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.38)`);
            gradient.addColorStop(0.7, `rgba(${r}, ${g}, ${b}, 0.08)`);
            gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);
            return gradient;
        } catch (e) {
            return "rgba(56, 189, 248, 0.15)";
        }
    }

    function updateChartStats(dataArr, labels, formatFn, isCumulative = false) {
        if (!elements.statPeak || !elements.statAvg || !elements.statTotal) return;
        if (!dataArr || dataArr.length === 0) {
            elements.statPeak.textContent = "-";
            elements.statAvg.textContent = "-";
            elements.statTotal.textContent = "-";
            return;
        }

        let maxVal = -Infinity;
        let maxIdx = 0;
        let sum = 0;
        for (let i = 0; i < dataArr.length; i++) {
            const v = Number(dataArr[i]) || 0;
            sum += v;
            if (v > maxVal) {
                maxVal = v;
                maxIdx = i;
            }
        }
        if (maxVal === -Infinity) maxVal = 0;
        const avg = dataArr.length > 0 ? (sum / dataArr.length) : 0;
        const peakLabel = (labels && labels[maxIdx]) ? ` (${labels[maxIdx]})` : "";

        if (isCumulative) {
            const endVal = dataArr[dataArr.length - 1] || 0;
            elements.statPeak.textContent = `${formatFn(endVal)}${peakLabel}`;
            elements.statAvg.textContent = `${formatFn(avg)} / Step`;
            elements.statTotal.textContent = formatFn(endVal);
        } else {
            elements.statPeak.textContent = `${formatFn(maxVal)}${peakLabel}`;
            elements.statAvg.textContent = formatFn(avg);
            elements.statTotal.textContent = formatFn(sum);
        }
    }

    function renderTimelineChart() {
        if (!elements.chartTimeline || !cachedAnalyticsData) return;
        const ctx = elements.chartTimeline.getContext("2d");

        const data = cachedAnalyticsData;
        const timeline = data.timeline || [];
        const isSingleStreamer = Boolean(data.selected_streamer);
        const streamerName = isSingleStreamer ? (data.selected_streamer.display_name || data.selected_streamer.username) : "Alle Streamer";

        // Sync dropdown & pills active state
        if (elements.metricSelect && elements.metricSelect.value !== analyticsMetric) {
            elements.metricSelect.value = analyticsMetric;
        }
        if (elements.metricPills) {
            elements.metricPills.forEach(p => {
                p.classList.toggle("active", p.getAttribute("data-metric") === analyticsMetric);
            });
        }

        if (timeline.length === 0) {
            if (chartTimelineInstance) {
                chartTimelineInstance.destroy();
                chartTimelineInstance = null;
            }
            if (elements.timelineTitle) elements.timelineTitle.textContent = "Keine Daten im Zeitfenster";
            if (elements.timelineSub) elements.timelineSub.textContent = "Im gewählten Zeitraum wurden keine Geschenke verzeichnet.";
            if (elements.statPeak) elements.statPeak.textContent = "-";
            if (elements.statAvg) elements.statAvg.textContent = "-";
            if (elements.statTotal) elements.statTotal.textContent = "-";
            return;
        }

        const labels = timeline.map(t => t.label || t.bucket);
        let chartType = analyticsChartType || "line";
        let datasets = [];
        let scales = {
            x: {
                grid: { color: "rgba(255, 255, 255, 0.05)" },
                ticks: { color: "#8b949e", font: { family: "monospace", size: 9 }, maxTicksLimit: 7 }
            },
            y: {
                position: "left",
                grid: { color: "rgba(255, 255, 255, 0.05)" },
                ticks: { color: "#8b949e", font: { family: "monospace", size: 9 } }
            }
        };

        const isArea = chartType === "area";
        const baseType = isArea ? "line" : chartType;

        if (analyticsMetric === "multi" && !isSingleStreamer && data.multi_streamer_datasets && data.multi_streamer_datasets.length > 0) {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Top-Streamer Vergleich (Coins)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Chronologische Entwicklung der aktivsten Streamer`;
            scales.y.ticks.color = "#38bdf8";
            scales.y.ticks.callback = v => formatNumber(v);
            const palette = ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f778ba", "#39c5cf"];
            datasets = data.multi_streamer_datasets.map((s, idx) => {
                const col = palette[idx % palette.length];
                return {
                    label: `@${s.username}`,
                    data: s.data,
                    borderColor: col,
                    backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                    borderWidth: 2,
                    pointRadius: 2.5,
                    tension: 0.35,
                    fill: isArea,
                };
            });
            // Total coins over time across timeline
            const totalCoinsPerBucket = timeline.map(t => t.coins || 0);
            updateChartStats(totalCoinsPerBucket, labels, v => `${formatNumber(v)} Coins`);
        } else if (analyticsMetric === "eur") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Netto Creator-Auszahlung (€)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Netto-Erlöse in Euro · ${streamerName}`;
            scales.y.ticks.color = "#10b981";
            scales.y.ticks.callback = v => `€${formatNumber(v)}`;
            const col = "#10b981";
            const vals = timeline.map(t => t.eur_net || 0);
            datasets = [{
                type: baseType,
                label: "Netto EUR",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "EUR"));
        } else if (analyticsMetric === "usd") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Netto Creator-Auszahlung ($)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Netto-Erlöse in US-Dollar · ${streamerName}`;
            scales.y.ticks.color = "#06b6d4";
            scales.y.ticks.callback = v => `$${formatNumber(v)}`;
            const col = "#06b6d4";
            const vals = timeline.map(t => t.usd_net || 0);
            datasets = [{
                type: baseType,
                label: "Netto USD",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "USD"));
        } else if (analyticsMetric === "gross") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Brutto Zuschauer-Kaufwert (€)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Kaufwert aller TikTok-Münzen durch Zuschauer in EUR · ${streamerName}`;
            scales.y.ticks.color = "#f59e0b";
            scales.y.ticks.callback = v => `€${formatNumber(v)}`;
            const col = "#f59e0b";
            const vals = timeline.map(t => t.eur_gross || 0);
            datasets = [{
                type: baseType,
                label: "Brutto EUR",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "EUR"));
        } else if (analyticsMetric === "gross_usd") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Brutto Zuschauer-Kaufwert ($)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Kaufwert aller TikTok-Münzen durch Zuschauer in USD · ${streamerName}`;
            scales.y.ticks.color = "#fbbf24";
            scales.y.ticks.callback = v => `$${formatNumber(v)}`;
            const col = "#fbbf24";
            const vals = timeline.map(t => t.usd_gross || 0);
            datasets = [{
                type: baseType,
                label: "Brutto USD",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "USD"));
        } else if (analyticsMetric === "cumulative_eur") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Kumulierte Netto-Einnahmen (€)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Aufsummierte Gesamterlöse über die Zeit · ${streamerName}`;
            scales.y.ticks.color = "#22c55e";
            scales.y.ticks.callback = v => `€${formatNumber(v)}`;
            const col = "#22c55e";
            let runSum = 0;
            const vals = timeline.map(t => {
                runSum += (t.eur_net || 0);
                return Math.round(runSum * 100) / 100;
            });
            datasets = [{
                type: baseType,
                label: "Kumulativ EUR",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2.5,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.25,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "EUR"), true);
        } else if (analyticsMetric === "cumulative_coins") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Kumulierte TikTok-Münzen (💎)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Aufsummiertes Münzvolumen über die Zeit · ${streamerName}`;
            scales.y.ticks.color = "#a855f7";
            scales.y.ticks.callback = v => formatNumber(v);
            const col = "#a855f7";
            let runSum = 0;
            const vals = timeline.map(t => {
                runSum += (t.coins || 0);
                return runSum;
            });
            datasets = [{
                type: baseType,
                label: "Kumulativ Coins",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2.5,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.25,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => `${formatNumber(v)} Coins`, true);
        } else if (analyticsMetric === "coins") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `TikTok Diamanten & Münzen (💎)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Erhaltene TikTok-Münzen · ${streamerName}`;
            scales.y.ticks.color = "#38bdf8";
            scales.y.ticks.callback = v => formatNumber(v);
            const col = "#38bdf8";
            const vals = timeline.map(t => t.coins || 0);
            datasets = [{
                type: baseType,
                label: "Coins",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => `${formatNumber(v)} Coins`);
        } else if (analyticsMetric === "events") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Gift-Events & Transaktionen (🎁)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Anzahl Geschenk-Buchungen · ${streamerName}`;
            scales.y.ticks.color = "#ec4899";
            scales.y.ticks.callback = v => formatNumber(v);
            const col = "#ec4899";
            const vals = timeline.map(t => t.events_count || 0);
            datasets = [{
                type: baseType,
                label: "Gift-Events",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => `${formatNumber(v)} Events`);
        } else if (analyticsMetric === "gifters") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Aktive Spender (👤)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Eindeutige Gifter pro Zeitintervall · ${streamerName}`;
            scales.y.ticks.color = "#8b5cf6";
            scales.y.ticks.callback = v => formatNumber(v);
            const col = "#8b5cf6";
            const vals = timeline.map(t => t.unique_gifters || 0);
            datasets = [{
                type: baseType,
                label: "Spender",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => `${formatNumber(v)} Spender`);
        } else if (analyticsMetric === "avg_gifter") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Ø Netto-Wert pro Spender (€)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Durchschnittlicher Ertrag je Gifter · ${streamerName}`;
            scales.y.ticks.color = "#eab308";
            scales.y.ticks.callback = v => `€${v}`;
            const col = "#eab308";
            const vals = timeline.map(t => {
                if (t.avg_eur_per_gifter !== undefined) return t.avg_eur_per_gifter;
                return t.unique_gifters > 0 ? (Math.round((t.eur_net / t.unique_gifters) * 100) / 100) : 0;
            });
            datasets = [{
                type: baseType,
                label: "Ø € / Spender",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => formatCurrency(v, "EUR"));
        } else if (analyticsMetric === "avg_gift") {
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Ø Münzen pro Geschenk (💎)`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Durchschnittliche Geschenkgröße · ${streamerName}`;
            scales.y.ticks.color = "#14b8a6";
            scales.y.ticks.callback = v => `${formatNumber(v)}`;
            const col = "#14b8a6";
            const vals = timeline.map(t => {
                if (t.avg_coins_per_gift !== undefined) return t.avg_coins_per_gift;
                return t.events_count > 0 ? (Math.round((t.coins / t.events_count) * 10) / 10) : 0;
            });
            datasets = [{
                type: baseType,
                label: "Ø Coins / Gift",
                data: vals,
                borderColor: col,
                backgroundColor: isArea ? createChartGradient(ctx, col) : (baseType === "bar" ? col : "transparent"),
                borderWidth: 2,
                borderRadius: baseType === "bar" ? 3 : 0,
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
            }];
            updateChartStats(vals, labels, v => `${formatNumber(v)} Coins`);
        } else {
            // Mode "both" (default combo: Coins Bar + Netto EUR Line)
            if (elements.timelineTitle) elements.timelineTitle.textContent = `Einnahmen- & Coin-Verlauf`;
            if (elements.timelineSub) elements.timelineSub.textContent = `Balken: Coins (links) | Linie: Netto EUR (rechts) · ${streamerName}`;
            scales.y.title = { display: true, text: "Coins", color: "#38bdf8", font: { family: "monospace", size: 9 } };
            scales.y.ticks.color = "#38bdf8";
            scales.y.ticks.callback = v => formatNumber(v);
            scales.yEur = {
                position: "right",
                grid: { drawOnChartArea: false },
                ticks: { color: "#10b981", font: { family: "monospace", size: 9 }, callback: v => `€${formatNumber(v)}` },
                title: { display: true, text: "Netto EUR", color: "#10b981", font: { family: "monospace", size: 9 } }
            };
            const coinVals = timeline.map(t => t.coins || 0);
            const eurVals = timeline.map(t => t.eur_net || 0);
            datasets = [
                {
                    type: "bar",
                    label: "Coins",
                    data: coinVals,
                    backgroundColor: "rgba(56, 189, 248, 0.65)",
                    borderColor: "#38bdf8",
                    borderWidth: 1,
                    borderRadius: 2,
                    yAxisID: "y",
                },
                {
                    type: "line",
                    label: "Netto EUR",
                    data: eurVals,
                    borderColor: "#10b981",
                    backgroundColor: isArea ? createChartGradient(ctx, "#10b981") : "rgba(16, 185, 129, 0.1)",
                    borderWidth: 2.2,
                    pointRadius: 2.5,
                    fill: isArea,
                    tension: 0.35,
                    yAxisID: "yEur",
                }
            ];
            updateChartStats(eurVals, labels, v => formatCurrency(v, "EUR"));
        }

        if (chartTimelineInstance && chartTimelineInstance.config.type === baseType) {
            chartTimelineInstance.data.labels = labels;
            chartTimelineInstance.data.datasets = datasets;
            chartTimelineInstance.options.scales = scales;
            chartTimelineInstance.options.plugins.legend.display = datasets.length > 1;
            chartTimelineInstance.update("none");
            return;
        }

        if (chartTimelineInstance) {
            chartTimelineInstance.destroy();
            chartTimelineInstance = null;
        }

        chartTimelineInstance = new Chart(ctx, {
            type: baseType,
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        display: datasets.length > 1,
                        labels: { color: "#8b949e", font: { family: "monospace", size: 10 } }
                    },
                    tooltip: {
                        backgroundColor: "#161b22",
                        titleColor: "#c9d1d9",
                        bodyColor: "#58a6ff",
                        borderColor: "#30363d",
                        borderWidth: 1,
                        padding: 8,
                        titleFont: { family: "monospace", size: 11 },
                        bodyFont: { family: "monospace", size: 11 },
                    }
                },
                scales: scales
            }
        });
    }

    function renderStreamerCompareChart(ranking) {
        if (!elements.chartStreamerCompare) return;
        const ctx = elements.chartStreamerCompare.getContext("2d");

        if (!ranking || ranking.length === 0) {
            if (chartStreamerCompareInstance) {
                chartStreamerCompareInstance.destroy();
                chartStreamerCompareInstance = null;
            }
            return;
        }
        const top = ranking.slice(0, 6);
        const labels = top.map(s => s.display_name || s.username);
        const dataVals = top.map(s => s.eur_net || 0);

        if (chartStreamerCompareInstance) {
            chartStreamerCompareInstance.data.labels = labels;
            chartStreamerCompareInstance.data.datasets[0].data = dataVals;
            chartStreamerCompareInstance.update("none");
            return;
        }

        chartStreamerCompareInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Netto EUR (€)",
                    data: dataVals,
                    backgroundColor: [
                        "#38bdf8", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#64748b"
                    ],
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { color: "rgba(255, 255, 255, 0.05)" },
                        ticks: { color: "#8b949e", font: { family: "monospace", size: 9 }, callback: v => `€${v}` }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: "#e6edf3", font: { family: "monospace", size: 10 } }
                    }
                }
            }
        });
    }

    function renderTopGifters(gifters) {
        if (!elements.topGiftersContainer) return;
        if (!gifters || gifters.length === 0) {
            elements.topGiftersContainer.innerHTML = '<div class="ma-empty-state">Keine Spenderdaten im Zeitraum.</div>';
            return;
        }

        let html = "";
        gifters.slice(0, 10).forEach((g, idx) => {
            const rank = idx + 1;
            const rankClass = rank === 1 ? "gold" : (rank === 2 ? "silver" : (rank === 3 ? "bronze" : ""));
            const medal = rank === 1 ? "🥇" : (rank === 2 ? "🥈" : (rank === 3 ? "🥉" : `#${rank}`));
            const name = g.sender_nickname || g.sender_username || "Anonym";
            const txText = `${formatNumber(g.gifts_sent || 0)} Gifts · ${formatNumber(g.transactions || 0)}x`;

            html += `
                <div class="ma-gifter-item">
                    <div class="ma-gifter-left">
                        <span class="ma-gifter-rank ${rankClass}">${medal}</span>
                        <div>
                            <div class="ma-gifter-name">${escapeHtml(name)}</div>
                            <div class="ma-gifter-sub">@${escapeHtml(g.sender_username)} · ${txText}</div>
                        </div>
                    </div>
                    <div class="ma-gifter-coins">+${formatNumber(g.total_coins)} 💎</div>
                </div>
            `;
        });
        elements.topGiftersContainer.innerHTML = html;
    }

    function renderGiftDistChart(topGifts) {
        if (!elements.chartGiftDist) return;
        const ctx = elements.chartGiftDist.getContext("2d");

        if (!topGifts || topGifts.length === 0) {
            if (chartGiftDistInstance) {
                chartGiftDistInstance.destroy();
                chartGiftDistInstance = null;
            }
            if (elements.topGiftsList) elements.topGiftsList.innerHTML = '<div class="ma-empty-state">Keine Geschenke.</div>';
            return;
        }

        const labels = topGifts.slice(0, 6).map(g => g.gift_name);
        const dataVals = topGifts.slice(0, 6).map(g => g.total_coins);
        const palette = ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f778ba", "#39c5cf"];

        if (chartGiftDistInstance) {
            chartGiftDistInstance.data.labels = labels;
            chartGiftDistInstance.data.datasets[0].data = dataVals;
            chartGiftDistInstance.update("none");
        } else {
            chartGiftDistInstance = new Chart(ctx, {
                type: "doughnut",
                data: {
                    labels: labels,
                    datasets: [{
                        data: dataVals,
                        backgroundColor: palette,
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "right",
                            labels: { color: "#8b949e", font: { family: "monospace", size: 10 } }
                        }
                    }
                }
            });
        }

        if (elements.topGiftsList) {
            let listHtml = "";
            topGifts.slice(0, 5).forEach(g => {
                listHtml += `
                    <div class="ma-gift-dist-item">
                        <span class="ma-gift-dist-name">🎁 ${escapeHtml(g.gift_name)} (${formatNumber(g.total_quantity)}x)</span>
                        <span class="ma-gift-dist-val">${formatNumber(g.total_coins)} Coins · ${formatCurrency(g.eur_net)}</span>
                    </div>
                `;
            });
            elements.topGiftsList.innerHTML = listHtml;
        }
    }

    function renderTimeOfDayChart(timeData) {
        if (!elements.chartTimeOfDay) return;
        const ctx = elements.chartTimeOfDay.getContext("2d");

        const labels = Array.from({ length: 24 }, (_, i) => `${i}h`);
        const values = new Array(24).fill(0);

        if (Array.isArray(timeData)) {
            timeData.forEach(item => {
                const hour = parseInt(item.hour !== undefined ? item.hour : item.bucket, 10);
                if (!isNaN(hour) && hour >= 0 && hour < 24) {
                    values[hour] = item.coins || item.total_coins || 0;
                }
            });
        }

        if (chartTimeOfDayInstance) {
            chartTimeOfDayInstance.data.labels = labels;
            chartTimeOfDayInstance.data.datasets[0].data = values;
            chartTimeOfDayInstance.update("none");
            return;
        }

        chartTimeOfDayInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Coins",
                    data: values,
                    backgroundColor: "#38bdf8",
                    borderRadius: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: "#8b949e", font: { family: "monospace", size: 9 } }
                    },
                    y: {
                        grid: { color: "rgba(255, 255, 255, 0.05)" },
                        ticks: { color: "#8b949e", font: { family: "monospace", size: 9 } }
                    }
                }
            }
        });
    }

    // =====================================================================
    // 5. ADMIN CONTROL PANEL
    // =====================================================================
    async function loadAdminData() {
        if (!isAdmin) return;
        renderAdminStreamers(cachedStreamers);
        fetchSystemStatus();
    }

    function renderAdminStreamers(streamers) {
        if (!elements.adminStreamersContainer) return;
        if (!streamers || streamers.length === 0) {
            elements.adminStreamersContainer.innerHTML = '<div class="ma-empty-state">Keine Streamer vorhanden.</div>';
            return;
        }

        let html = "";
        streamers.forEach(s => {
            const avatar = s.avatar_url || "/static/avatar_default.png";
            const name = s.display_name || s.username;
            const uname = s.username;
            const isTracking = !!s.is_tracking;
            const isLive = !!s.is_live;

            html += `
                <div class="ma-admin-streamer-card">
                    <div class="ma-admin-streamer-top">
                        <div class="ma-admin-streamer-meta">
                            <img src="${escapeHtml(avatar)}" class="ma-admin-streamer-avatar" onerror="this.src='/static/avatar_default.png'">
                            <div>
                                <div class="ma-admin-streamer-title">${escapeHtml(name)} ${isLive ? '🟢' : '⚪'}</div>
                                <div class="ma-admin-streamer-sub">@${escapeHtml(uname)}</div>
                            </div>
                        </div>
                        <div>
                            <button type="button" class="ma-btn-toggle ${isTracking ? 'active' : ''}" data-action="toggle-track" data-username="${escapeHtml(uname)}">
                                ${isTracking ? '● TRACKING' : '○ PAUSIERT'}
                            </button>
                        </div>
                    </div>
                    <div class="ma-admin-streamer-actions">
                        <button type="button" class="ma-btn ma-btn-secondary" style="font-size: 10px; padding: 4px 8px;" data-action="refresh" data-username="${escapeHtml(uname)}">
                            🔄 Sync
                        </button>
                        <button type="button" class="ma-btn ma-btn-danger" style="font-size: 10px; padding: 4px 8px;" data-action="delete" data-username="${escapeHtml(uname)}" data-id="${s.id}">
                            🗑️ Löschen
                        </button>
                    </div>
                </div>
            `;
        });
        elements.adminStreamersContainer.innerHTML = html;

        // Attach action handlers
        elements.adminStreamersContainer.querySelectorAll("[data-action]").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const action = btn.getAttribute("data-action");
                const username = btn.getAttribute("data-username");
                const streamerId = btn.getAttribute("data-id");

                if (action === "toggle-track") {
                    triggerHaptic("medium");
                    try {
                        const res = await fetch(`/api/streamers/${encodeURIComponent(username)}/track`, {
                            method: "POST",
                            headers: Object.assign({ "Content-Type": "application/json" }, getAuthHeaders()),
                            body: JSON.stringify({ action: "toggle", auto_reconnect: true })
                        });
                        if (res.ok) {
                            showToast(`Tracking für @${username} umgeschaltet!`);
                            fetchMiniAppData();
                        } else {
                            showToast("Fehler beim Umschalten", "error");
                        }
                    } catch (err) {
                        showToast("Netzwerkfehler", "error");
                    }
                } else if (action === "refresh") {
                    triggerHaptic("light");
                    btn.textContent = "⏳...";
                    try {
                        const res = await fetch(`/api/streamers/${encodeURIComponent(username)}/refresh`, {
                            method: "POST",
                            headers: getAuthHeaders()
                        });
                        if (res.ok) {
                            showToast(`Profil @${username} aktualisiert!`);
                            fetchMiniAppData();
                        } else {
                            showToast("Sync fehlgeschlagen", "error");
                        }
                    } catch (err) {
                        showToast("Netzwerkfehler", "error");
                    }
                } else if (action === "delete") {
                    triggerHaptic("warning");
                    if (confirm(`Streamer @${username} wirklich komplett aus dem TokTracker löschen?`)) {
                        try {
                            const res = await fetch(`/api/streamers/${encodeURIComponent(streamerId || username)}`, {
                                method: "DELETE",
                                headers: getAuthHeaders()
                            });
                            if (res.ok) {
                                showToast(`Streamer @${username} gelöscht.`);
                                fetchMiniAppData();
                            } else {
                                showToast("Löschen fehlgeschlagen", "error");
                            }
                        } catch (err) {
                            showToast("Netzwerkfehler", "error");
                        }
                    }
                }
            });
        });
    }

    async function fetchSystemStatus() {
        try {
            const res = await fetch("/api/system/status", {
                headers: getAuthHeaders()
            });
            if (!res.ok) return;
            const data = await res.json();

            if (elements.diagDbEngine) elements.diagDbEngine.textContent = data.db_engine || "mariadb";
            if (elements.diagActiveWorkers) {
                const total = data.total_streamers || 0;
                const active = data.active_workers || 0;
                elements.diagActiveWorkers.textContent = `${active} von ${total} aktiv`;
            }
            if (elements.diagBotStatus) {
                const b = data.telegram_bot || {};
                elements.diagBotStatus.textContent = `${b.state || 'ok'} (${b.username || '@toktrackeragent'})`;
            }
            if (elements.diagTiktokSession) {
                elements.diagTiktokSession.textContent = data.has_tiktok_session ? "✅ Aktiv" : "⚪ Keine Session";
            }
        } catch (e) {}
    }

    // Modal Submissions
    // 1. Add Streamer
    if (elements.btnSubmitAddStreamer) {
        elements.btnSubmitAddStreamer.addEventListener("click", async () => {
            const uname = (elements.inputAddStreamerUsername.value || "").trim().replace(/^@/, "");
            if (!uname) {
                showToast("Bitte Username eingeben", "error");
                return;
            }
            triggerHaptic("medium");
            elements.btnSubmitAddStreamer.disabled = true;
            try {
                const res = await fetch("/api/streamers", {
                    method: "POST",
                    headers: Object.assign({ "Content-Type": "application/json" }, getAuthHeaders()),
                    body: JSON.stringify({
                        username: uname,
                        display_name: (elements.inputAddStreamerDisplayName.value || "").trim() || null,
                        auto_track: elements.checkAddStreamerAutoTrack.checked,
                        auto_reconnect: elements.checkAddStreamerAutoReconnect.checked
                    })
                });
                if (res.ok) {
                    showToast(`Streamer @${uname} erfolgreich angelegt!`);
                    elements.inputAddStreamerUsername.value = "";
                    elements.inputAddStreamerDisplayName.value = "";
                    closeModal(elements.modalAddStreamer);
                    fetchMiniAppData();
                } else {
                    const err = await res.json();
                    showToast(err.detail || "Fehler beim Anlegen", "error");
                }
            } catch (err) {
                showToast("Netzwerkfehler", "error");
            } finally {
                elements.btnSubmitAddStreamer.disabled = false;
            }
        });
    }

    // 2. Add Gift
    if (elements.btnSubmitAddGift) {
        elements.btnSubmitAddGift.addEventListener("click", async () => {
            const streamerId = parseInt(elements.selectAddGiftStreamer.value, 10);
            const giftName = (elements.inputAddGiftName.value || "").trim();
            const diamonds = parseInt(elements.inputAddGiftCoins.value, 10) || 1;
            const count = parseInt(elements.inputAddGiftCount.value, 10) || 1;
            const sender = (elements.inputAddGiftSender.value || "").trim() || "manual_admin";

            if (!streamerId || !giftName) {
                showToast("Bitte Streamer und Gift-Name angeben", "error");
                return;
            }
            triggerHaptic("medium");
            elements.btnSubmitAddGift.disabled = true;
            try {
                const res = await fetch("/api/gifts", {
                    method: "POST",
                    headers: Object.assign({ "Content-Type": "application/json" }, getAuthHeaders()),
                    body: JSON.stringify({
                        streamer_id: streamerId,
                        gift_name: giftName,
                        diamond_count: diamonds,
                        repeat_count: count,
                        sender_username: sender,
                        source: "manual_miniapp"
                    })
                });
                if (res.ok) {
                    showToast(`Geschenk ${count}x ${giftName} erfolgreich gebucht!`);
                    closeModal(elements.modalAddGift);
                    fetchMiniAppData();
                } else {
                    showToast("Fehler beim Buchen", "error");
                }
            } catch (err) {
                showToast("Netzwerkfehler", "error");
            } finally {
                elements.btnSubmitAddGift.disabled = false;
            }
        });
    }

    // 3. Settings Modal
    async function loadSettings() {
        try {
            const res = await fetch("/api/settings", { headers: getAuthHeaders() });
            if (!res.ok) return;
            const s = await res.json();
            if (elements.inputSettingsUsdDiamond) elements.inputSettingsUsdDiamond.value = s.usd_per_diamond || 0.005;
            if (elements.inputSettingsGrossCoin) elements.inputSettingsGrossCoin.value = s.gross_usd_per_coin || 0.0106;
            if (elements.inputSettingsUsdToEur) elements.inputSettingsUsdToEur.value = s.usd_to_eur_rate || 0.92;
            if (elements.selectSettingsCurrency) elements.selectSettingsCurrency.value = s.currency_primary || "EUR";
            if (elements.selectSettingsTgMode) elements.selectSettingsTgMode.value = s.telegram_access_mode || "whitelist";
        } catch (e) {}
    }

    if (elements.btnSubmitSettings) {
        elements.btnSubmitSettings.addEventListener("click", async () => {
            triggerHaptic("medium");
            try {
                const payload = {
                    usd_per_diamond: parseFloat(elements.inputSettingsUsdDiamond.value),
                    gross_usd_per_coin: parseFloat(elements.inputSettingsGrossCoin.value),
                    usd_to_eur_rate: parseFloat(elements.inputSettingsUsdToEur.value),
                    currency_primary: elements.selectSettingsCurrency.value,
                    telegram_access_mode: elements.selectSettingsTgMode.value
                };
                const res = await fetch("/api/settings", {
                    method: "POST",
                    headers: Object.assign({ "Content-Type": "application/json" }, getAuthHeaders()),
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    showToast("Einstellungen gespeichert!");
                    closeModal(elements.modalSettings);
                    fetchMiniAppData();
                } else {
                    showToast("Fehler beim Speichern", "error");
                }
            } catch (err) {
                showToast("Netzwerkfehler", "error");
            }
        });
    }

    // 4. Whitelist Modal
    async function loadWhitelist() {
        if (!elements.whitelistUsersContainer) return;
        try {
            const res = await fetch("/api/telegram/users", { headers: getAuthHeaders() });
            if (!res.ok) return;
            const users = await res.json();

            let html = "";
            users.forEach(u => {
                const uname = u.username ? `@${u.username}` : (u.telegram_id || "Unbekannt");
                const isAllowed = parseInt(u.is_allowed, 10) === 1;
                const isAdminRole = u.role === "admin";
                const badge = isAllowed ? (isAdminRole ? "👑 Admin" : "🟢 User") : "🔴 Gesperrt";

                html += `
                    <div class="ma-whitelist-item">
                        <div>
                            <div style="font-weight: 700; color: var(--text-strong);">${escapeHtml(uname)}</div>
                            <div style="font-size: 9px; color: var(--text-muted);">${badge} · ID: ${u.telegram_id || '-'}</div>
                        </div>
                        <div class="ma-whitelist-actions">
                            <button type="button" class="ma-btn ma-btn-secondary" style="font-size: 9px; padding: 2px 6px;" data-toggle-role="${u.id}" data-role="${isAdminRole ? 'user' : 'admin'}" data-ident="${u.telegram_id || u.username}">
                                ${isAdminRole ? 'User machen' : 'Admin machen'}
                            </button>
                            <button type="button" class="ma-btn ${isAllowed ? 'ma-btn-danger' : 'ma-btn-primary'}" style="font-size: 9px; padding: 2px 6px;" data-toggle-allow="${u.id}" data-allowed="${isAllowed ? 0 : 1}" data-ident="${u.telegram_id || u.username}">
                                ${isAllowed ? 'Sperren' : 'Erlauben'}
                            </button>
                        </div>
                    </div>
                `;
            });
            elements.whitelistUsersContainer.innerHTML = html;

            elements.whitelistUsersContainer.querySelectorAll("[data-toggle-role]").forEach(b => {
                b.addEventListener("click", async () => {
                    const ident = b.getAttribute("data-ident");
                    const newRole = b.getAttribute("data-role");
                    await updateTelegramUserPermission(ident, 1, newRole);
                });
            });

            elements.whitelistUsersContainer.querySelectorAll("[data-toggle-allow]").forEach(b => {
                b.addEventListener("click", async () => {
                    const ident = b.getAttribute("data-ident");
                    const newAllow = parseInt(b.getAttribute("data-allowed"), 10);
                    await updateTelegramUserPermission(ident, newAllow, "user");
                });
            });
        } catch (e) {
            elements.whitelistUsersContainer.innerHTML = '<div class="ma-empty-state">Fehler beim Laden.</div>';
        }
    }

    async function updateTelegramUserPermission(ident, isAllowed, role) {
        triggerHaptic("medium");
        try {
            const res = await fetch("/api/telegram/users/permissions", {
                method: "POST",
                headers: Object.assign({ "Content-Type": "application/json" }, getAuthHeaders()),
                body: JSON.stringify({ identifier: String(ident), is_allowed: isAllowed, role: role })
            });
            if (res.ok) {
                showToast("Nutzerrechte aktualisiert!");
                loadWhitelist();
            } else {
                showToast("Fehler bei Rechteänderung", "error");
            }
        } catch (e) {
            showToast("Netzwerkfehler", "error");
        }
    }

    if (elements.btnSubmitAddTgUser) {
        elements.btnSubmitAddTgUser.addEventListener("click", async () => {
            const ident = (elements.inputAddTgUserIdent.value || "").trim();
            const role = elements.selectAddTgUserRole.value;
            if (!ident) return;
            await updateTelegramUserPermission(ident, 1, role);
            elements.inputAddTgUserIdent.value = "";
        });
    }

    // Modal Trigger Buttons
    if (elements.btnOpenAddStreamer) elements.btnOpenAddStreamer.addEventListener("click", () => openModal(elements.modalAddStreamer));
    if (elements.btnOpenAddGift) elements.btnOpenAddGift.addEventListener("click", () => openModal(elements.modalAddGift));
    if (elements.btnOpenSettings) elements.btnOpenSettings.addEventListener("click", () => { openModal(elements.modalSettings); loadSettings(); });
    if (elements.btnOpenWhitelist) elements.btnOpenWhitelist.addEventListener("click", () => { openModal(elements.modalWhitelist); loadWhitelist(); });

    // Modal Close Buttons
    document.querySelectorAll(".ma-sheet-close, [data-close]").forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.closest(".ma-modal-backdrop");
            if (target) closeModal(target);
        });
    });

    document.querySelectorAll(".ma-modal-backdrop").forEach(backdrop => {
        backdrop.addEventListener("click", (e) => {
            if (e.target === backdrop) closeModal(backdrop);
        });
    });

    // OTP Auth Fallback Handlers
    if (elements.btnRequestOtp) {
        elements.btnRequestOtp.addEventListener("click", async () => {
            triggerHaptic("medium");
            elements.btnRequestOtp.disabled = true;
            try {
                const res = await fetch("/api/miniapp/auth/request_otp", { method: "POST" });
                if (res.ok) {
                    showToast("Code an hinterlegte Admins in Telegram gesendet!", "success");
                } else {
                    showToast("Fehler beim Code-Versand", "error");
                }
            } catch (e) {
                showToast("Netzwerkfehler", "error");
            } finally {
                elements.btnRequestOtp.disabled = false;
            }
        });
    }

    if (elements.btnSubmitOtp) {
        elements.btnSubmitOtp.addEventListener("click", async () => {
            const code = (elements.otpCodeInput.value || "").trim();
            if (!code) {
                showToast("Bitte Code eingeben", "error");
                return;
            }
            triggerHaptic("heavy");
            elements.btnSubmitOtp.disabled = true;
            try {
                const res = await fetch("/api/miniapp/auth/verify_otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ code: code })
                });
                if (res.ok) {
                    const data = await res.json();
                    sessionToken = data.token;
                    localStorage.setItem("toktracker_admin_token", sessionToken);
                    isAdmin = true;
                    authUser = { username: data.admin_label };
                    showToast("Erfolgreich als Admin angemeldet!");
                    elements.otpCodeInput.value = "";
                    updateAdminUI();
                } else {
                    showToast("Ungültiger oder abgelaufener Code", "error");
                }
            } catch (e) {
                showToast("Netzwerkfehler", "error");
            } finally {
                elements.btnSubmitOtp.disabled = false;
            }
        });
    }

    if (elements.btnAdminLogout) {
        elements.btnAdminLogout.addEventListener("click", async () => {
            triggerHaptic("medium");
            try {
                await fetch("/api/miniapp/auth/logout", { method: "POST" });
            } catch (e) {}
            sessionToken = "";
            localStorage.removeItem("toktracker_admin_token");
            isAdmin = false;
            showToast("Erfolgreich abgemeldet");
            updateAdminUI();
        });
    }

    // =====================================================================
    // 6. EVENT HANDLERS & NAVIGATION
    // =====================================================================
    // Period Pills
    elements.periodPills.forEach(pill => {
        pill.addEventListener("click", () => {
            const period = pill.getAttribute("data-period");
            if (period === currentPeriod) return;
            triggerHaptic("light");
            currentPeriod = period;
            elements.periodPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            lastAnalyticsFingerprint = null;
            fetchMiniAppData();
            if (activeTab === "tab-analytics") {
                fetchAnalyticsData();
            }
        });
    });

    // Navigation Tabs
    elements.navTabs.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            if (targetTab === activeTab) return;
            triggerHaptic("medium");
            activeTab = targetTab;

            elements.navTabs.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            elements.tabViews.forEach(view => {
                if (view.id === targetTab) {
                    view.classList.add("active");
                } else {
                    view.classList.remove("active");
                }
            });

            if (targetTab === "tab-analytics") {
                if (!analyticsLoadedOnce) {
                    analyticsLoadedOnce = true;
                    setTimeout(() => {
                        fetchAnalyticsData();
                    }, 50);
                } else {
                    fetchAnalyticsData();
                }
            } else if (targetTab === "tab-admin") {
                updateAdminUI();
            }
        });
    });

    // Analytics Streamer Dropdown
    if (elements.analyticsStreamerSelect) {
        elements.analyticsStreamerSelect.addEventListener("change", () => {
            selectedAnalyticsStreamer = elements.analyticsStreamerSelect.value;
            triggerHaptic("light");
            lastAnalyticsFingerprint = null;
            fetchAnalyticsData();
        });
    }

    // Analytics Metric Dropdown
    if (elements.metricSelect) {
        elements.metricSelect.addEventListener("change", () => {
            const metric = elements.metricSelect.value;
            if (metric === analyticsMetric) return;
            triggerHaptic("light");
            analyticsMetric = metric;
            if (elements.metricPills) {
                elements.metricPills.forEach(p => {
                    p.classList.toggle("active", p.getAttribute("data-metric") === metric);
                });
            }
            if (cachedAnalyticsData) renderTimelineChart();
        });
    }

    // Analytics Metric Selector Pills
    if (elements.metricPills) {
        elements.metricPills.forEach(pill => {
            pill.addEventListener("click", () => {
                const metric = pill.getAttribute("data-metric");
                if (metric === analyticsMetric) return;
                triggerHaptic("light");
                analyticsMetric = metric;
                elements.metricPills.forEach(p => p.classList.remove("active"));
                pill.classList.add("active");
                if (elements.metricSelect) {
                    elements.metricSelect.value = metric;
                }
                if (cachedAnalyticsData) renderTimelineChart();
            });
        });
    }

    // Analytics Chart Type Toggle (Line, Bar, Area)
    if (elements.btnChartLine) {
        elements.btnChartLine.addEventListener("click", () => {
            if (analyticsChartType === "line") return;
            triggerHaptic("light");
            analyticsChartType = "line";
            elements.btnChartLine.classList.add("active");
            if (elements.btnChartBar) elements.btnChartBar.classList.remove("active");
            if (elements.btnChartArea) elements.btnChartArea.classList.remove("active");
            if (cachedAnalyticsData) renderTimelineChart();
        });
    }
    if (elements.btnChartBar) {
        elements.btnChartBar.addEventListener("click", () => {
            if (analyticsChartType === "bar") return;
            triggerHaptic("light");
            analyticsChartType = "bar";
            elements.btnChartBar.classList.add("active");
            if (elements.btnChartLine) elements.btnChartLine.classList.remove("active");
            if (elements.btnChartArea) elements.btnChartArea.classList.remove("active");
            if (cachedAnalyticsData) renderTimelineChart();
        });
    }
    if (elements.btnChartArea) {
        elements.btnChartArea.addEventListener("click", () => {
            if (analyticsChartType === "area") return;
            triggerHaptic("light");
            analyticsChartType = "area";
            elements.btnChartArea.classList.add("active");
            if (elements.btnChartLine) elements.btnChartLine.classList.remove("active");
            if (elements.btnChartBar) elements.btnChartBar.classList.remove("active");
            if (cachedAnalyticsData) renderTimelineChart();
        });
    }

    // Refresh Button Click
    if (elements.btnRefresh) {
        elements.btnRefresh.addEventListener("click", () => {
            triggerHaptic("light");
            lastAnalyticsFingerprint = null;
            fetchMiniAppData();
            if (activeTab === "tab-analytics") fetchAnalyticsData();
            if (activeTab === "tab-admin" && isAdmin) loadAdminData();
        });
    }

    // Initial Start
    initAuth();
    fetchMiniAppData();
    pollInterval = setInterval(fetchMiniAppData, 8000);

    // Visibility change handling
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            if (pollInterval) clearInterval(pollInterval);
        } else {
            fetchMiniAppData();
            pollInterval = setInterval(fetchMiniAppData, 8000);
        }
    });

})();
