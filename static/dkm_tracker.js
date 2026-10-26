/**
 * TokTracker – DKM Justiz- & Knast-Tracker (Gag-Portal)
 * Frontend Controller (Vanilla JavaScript)
 */
(function() {
    "use strict";

    // State
    const state = {
        data: null,
        hourlyRate: 5.80, // Default fallback
        pollTimer: null,
        isPolling: false,
    };

    // DOM Elements
    const elements = {
        dkmAvatar: document.getElementById("dkmAvatar"),
        dkmUsername: document.getElementById("dkmUsername"),
        dkmLiveBadge: document.getElementById("dkmLiveBadge"),
        dkmLiveDot: document.getElementById("dkmLiveDot"),
        dkmLiveText: document.getElementById("dkmLiveText"),
        dkmSentenceInfo: document.getElementById("dkmSentenceInfo"),

        // Live Ticker Card
        dkmLiveTickerCard: document.getElementById("dkmLiveTickerCard"),
        dkmLiveSubText: document.getElementById("dkmLiveSubText"),
        dkmLiveSessionStats: document.getElementById("dkmLiveSessionStats"),

        // Progress Meter
        dkmProgressFill: document.getElementById("dkmProgressFill"),
        dkmProgressLabel: document.getElementById("dkmProgressLabel"),
        dkmEarnedNetEur: document.getElementById("dkmEarnedNetEur"),
        dkmRemainingEur: document.getElementById("dkmRemainingEur"),
        dkmTargetEur: document.getElementById("dkmTargetEur"),
        dkmTotalCoins: document.getElementById("dkmTotalCoins"),

        // 4 KPIs
        kpiHoursRemaining: document.getElementById("kpiHoursRemaining"),
        kpiHourlyRateSub: document.getElementById("kpiHourlyRateSub"),
        kpiSessionsRemaining: document.getElementById("kpiSessionsRemaining"),
        kpiAvgSessionSub: document.getElementById("kpiAvgSessionSub"),
        kpiLionsRemaining: document.getElementById("kpiLionsRemaining"),
        kpiUniversesRemaining: document.getElementById("kpiUniversesRemaining"),

        // Gift Equivalents
        eqUniverses: document.getElementById("eqUniverses"),
        eqLions: document.getElementById("eqLions"),
        eqWhales: document.getElementById("eqWhales"),
        eqRoses: document.getElementById("eqRoses"),

        // JVA Comparison
        jvaEarningsSentence: document.getElementById("jvaEarningsSentence"),
        jvaYearsNeeded: document.getElementById("jvaYearsNeeded"),
        jvaTikTokEquiv: document.getElementById("jvaTikTokEquiv"),

        // Simulator
        simSlider: document.getElementById("simSlider"),
        simCoinsText: document.getElementById("simCoinsText"),
        simEurText: document.getElementById("simEurText"),
        simHoursText: document.getElementById("simHoursText"),
        simReliefBadge: document.getElementById("simReliefBadge"),

        // Top Gifters
        dkmTopGiftersBody: document.getElementById("dkmTopGiftersBody"),

        // Sharing & Toast
        btnSharePortal: document.getElementById("btnSharePortal"),
        btnShareCopy: document.getElementById("btnShareCopy"),
        dkmToast: document.getElementById("dkmToast"),
        dkmToastText: document.getElementById("dkmToastText"),

        // Direct Target & Sentence Editing
        btnEditDkmTarget: document.getElementById("btnEditDkmTarget"),
        btnEditDkmSentence: document.getElementById("btnEditDkmSentence"),
    };

    // Format Helpers
    function formatNumber(num) {
        if (num === null || num === undefined) return "0";
        return new Intl.NumberFormat("de-DE").format(num);
    }

    function formatCurrency(num) {
        if (num === null || num === undefined) return "0,00 €";
        return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(num);
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    let toastTimer = null;
    function showToast(text = "Link kopiert!") {
        if (!elements.dkmToast) return;
        if (elements.dkmToastText) elements.dkmToastText.textContent = text;
        elements.dkmToast.style.display = "flex";
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            elements.dkmToast.style.display = "none";
        }, 2200);
    }

    function copyShareLink() {
        const url = window.location.origin + "/dkm";
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(() => {
                showToast("Portal-Link in Zwischenablage kopiert!");
            }).catch(() => {
                fallbackCopy(url);
            });
        } else {
            fallbackCopy(url);
        }
    }

    function fallbackCopy(text) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand("copy");
            showToast("Portal-Link kopiert!");
        } catch (e) {}
        document.body.removeChild(ta);
    }

    // 1. Initialize
    async function init() {
        bindEvents();
        await loadTrackerData();
        startPolling();
    }

    // 2. Bind UI Events
    function bindEvents() {
        if (elements.btnSharePortal) {
            elements.btnSharePortal.addEventListener("click", copyShareLink);
        }
        if (elements.btnShareCopy) {
            elements.btnShareCopy.addEventListener("click", copyShareLink);
        }

        // Simulator Slider
        if (elements.simSlider) {
            elements.simSlider.addEventListener("input", (e) => {
                updateSimulator(parseInt(e.target.value, 10) || 0);
            });
        }

        // Simulator Quick Buttons
        document.querySelectorAll(".btn-sim-quick").forEach(btn => {
            btn.addEventListener("click", () => {
                const coins = parseInt(btn.getAttribute("data-coins"), 10) || 0;
                if (elements.simSlider) elements.simSlider.value = coins;
                updateSimulator(coins);
            });
        });

        // Direct Target Editing (Prompt & Save)
        if (elements.btnEditDkmTarget) {
            elements.btnEditDkmTarget.addEventListener("click", async () => {
                const current = state.data ? state.data.court_costs_target : 10000;
                const input = prompt("⚖️ Neuer Zielbetrag für die Gerichtskosten in Euro:\n(z.B. 10000 für 10.000 €)", current);
                if (input === null) return;
                const clean = input.replace(/\s+/g, "").replace(",", ".");
                const val = parseFloat(clean);
                if (isNaN(val) || val <= 0) {
                    alert("Bitte einen gültigen Betrag größer als 0 eingeben (z.B. 10000).");
                    return;
                }
                try {
                    const res = await fetch("/api/settings", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ dkm_court_costs_target: val })
                    });
                    const data = await res.json().catch(() => ({}));
                    if (res.ok && data.ok) {
                        showToast(`Gerichtskosten auf ${formatCurrency(val)} gesetzt!`);
                        await loadTrackerData();
                    } else if (res.status === 401) {
                        alert("⚠️ Nur angemeldete Admins können diesen Wert ändern.\nBitte logge dich zuerst im Admin-Panel ein (/login).");
                    } else {
                        alert(`⚠️ Fehler beim Speichern: ${data.detail || res.statusText}`);
                    }
                } catch (e) {
                    alert(`⚠️ Netzwerkfehler: ${e.message}`);
                }
            });
        }

        // Direct Sentence Editing
        if (elements.btnEditDkmSentence) {
            elements.btnEditDkmSentence.addEventListener("click", async () => {
                const current = state.data ? state.data.sentence_months : 7;
                const input = prompt("⚖️ Haftstrafe in Monaten (z.B. 7):", current);
                if (input === null) return;
                const val = parseInt(input.trim(), 10);
                if (isNaN(val) || val <= 0) {
                    alert("Bitte eine gültige Monatsanzahl größer als 0 eingeben.");
                    return;
                }
                try {
                    const res = await fetch("/api/settings", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ dkm_sentence_months: val })
                    });
                    const data = await res.json().catch(() => ({}));
                    if (res.ok && data.ok) {
                        showToast(`Haftstrafe auf ${val} Monate gesetzt!`);
                        await loadTrackerData();
                    } else if (res.status === 401) {
                        alert("⚠️ Nur angemeldete Admins können diesen Wert ändern.\nBitte logge dich zuerst im Admin-Panel ein (/login).");
                    } else {
                        alert(`⚠️ Fehler beim Speichern: ${data.detail || res.statusText}`);
                    }
                } catch (e) {
                    alert(`⚠️ Netzwerkfehler: ${e.message}`);
                }
            });
        }
    }

    // 3. API Loader
    async function loadTrackerData() {
        if (state.isPolling) return;
        state.isPolling = true;

        try {
            const res = await fetch("/api/public/dkm-tracker");
            if (!res.ok) return;
            const data = await res.json();
            if (!data.ok) return;

            state.data = data;
            state.hourlyRate = data.hourly_rate_effective || 5.80;

            renderProfile(data);
            renderProgress(data);
            renderKPIs(data);
            renderGifts(data);
            renderJVA(data);
            renderTopGifters(data.top_gifters || []);
            updateSimulator(elements.simSlider ? parseInt(elements.simSlider.value, 10) : 29999);
        } catch (e) {
            console.error("Fehler loadTrackerData:", e);
        } finally {
            state.isPolling = false;
        }
    }

    // 4. Render Functions
    function renderProfile(d) {
        const s = d.streamer || {};
        if (elements.dkmAvatar && s.avatar_url) {
            elements.dkmAvatar.src = s.avatar_url;
        }
        if (elements.dkmUsername && s.username) {
            elements.dkmUsername.textContent = `@${s.username}`;
        }

        // Live Badge
        if (elements.dkmLiveBadge) {
            if (d.is_live) {
                elements.dkmLiveBadge.className = "dkm-live-status-pill online";
                if (elements.dkmLiveDot) elements.dkmLiveDot.style.background = "#ef4444";
                if (elements.dkmLiveText) {
                    elements.dkmLiveText.textContent = `🔴 DKM LIVE (${formatNumber(d.current_viewers || 0)} Zuschauer)`;
                }
                if (elements.dkmLiveTickerCard) {
                    elements.dkmLiveTickerCard.style.display = "flex";
                }
                if (elements.dkmLiveSessionStats && d.active_session) {
                    elements.dkmLiveSessionStats.textContent = `Aktueller Stream: +${formatNumber(d.active_session.coins)} Coins (+${formatCurrency(d.active_session.net_eur)})`;
                }
            } else {
                elements.dkmLiveBadge.className = "dkm-live-status-pill offline";
                if (elements.dkmLiveDot) elements.dkmLiveDot.style.background = "#94a3b8";
                if (elements.dkmLiveText) elements.dkmLiveText.textContent = "DKM OFFLINE";
                if (elements.dkmLiveTickerCard) {
                    elements.dkmLiveTickerCard.style.display = "none";
                }
            }
        }
    }

    function renderProgress(d) {
        const target = d.court_costs_target || 10000;
        const earned = d.earned_net_eur || 0;
        const remaining = d.remaining_eur !== undefined ? d.remaining_eur : Math.max(0, target - earned);
        const pct = d.progress_pct !== undefined ? d.progress_pct : Math.min(100, (earned / target) * 100);

        if (elements.dkmProgressFill) {
            elements.dkmProgressFill.style.width = `${Math.min(100, Math.max(2, pct))}%`;
        }
        if (elements.dkmProgressLabel) {
            elements.dkmProgressLabel.textContent = `${pct.toFixed(1)} % ABGESTREAMT`;
        }
        if (elements.dkmEarnedNetEur) {
            elements.dkmEarnedNetEur.textContent = formatCurrency(earned);
        }
        if (elements.dkmRemainingEur) {
            elements.dkmRemainingEur.textContent = formatCurrency(remaining);
        }
        if (elements.dkmTargetEur) {
            elements.dkmTargetEur.textContent = formatCurrency(target);
        }
        if (elements.dkmTotalCoins) {
            elements.dkmTotalCoins.textContent = formatNumber(d.total_coins || 0);
        }
        if (elements.dkmSentenceInfo) {
            elements.dkmSentenceInfo.textContent = `Haftstrafe: ${d.sentence_months || 7} Monate (~${d.sentence_days || 213} Tage)`;
        }
    }

    function renderKPIs(d) {
        if (elements.kpiHoursRemaining) {
            elements.kpiHoursRemaining.textContent = `${formatNumber(d.hours_remaining || 0)} Std.`;
        }
        if (elements.kpiHourlyRateSub) {
            elements.kpiHourlyRateSub.textContent = `bei Ø ${formatCurrency(d.hourly_rate_effective || 5.80)} / Streamingstunde`;
        }
        if (elements.kpiSessionsRemaining) {
            elements.kpiSessionsRemaining.textContent = `${formatNumber(d.sessions_remaining || 0)} Streams`;
        }
        if (elements.kpiAvgSessionSub) {
            elements.kpiAvgSessionSub.textContent = `bei Ø ${formatCurrency(d.avg_net_per_session || 21.70)} Netto pro Stream`;
        }
        if (elements.kpiLionsRemaining) {
            elements.kpiLionsRemaining.textContent = `${formatNumber(d.gifts_remaining ? d.gifts_remaining.lions : 0)} Löwen`;
        }
        if (elements.kpiUniversesRemaining) {
            elements.kpiUniversesRemaining.textContent = `${formatNumber(d.gifts_remaining ? d.gifts_remaining.universes : 0)} Universen`;
        }
    }

    function renderGifts(d) {
        const g = d.gifts_remaining || {};
        if (elements.eqUniverses) elements.eqUniverses.textContent = formatNumber(g.universes || 0);
        if (elements.eqLions) elements.eqLions.textContent = formatNumber(g.lions || 0);
        if (elements.eqRoses) elements.eqRoses.textContent = formatNumber(g.roses || 0);
        // Whales: ~10,000 coins (approx. 46 EUR)
        const whalesRemaining = Math.ceil((d.remaining_eur || 0) / 46.0);
        if (elements.eqWhales) elements.eqWhales.textContent = formatNumber(whalesRemaining);
    }

    function renderJVA(d) {
        const jva = d.jva_comparison || {};
        if (elements.jvaEarningsSentence) {
            elements.jvaEarningsSentence.textContent = formatCurrency(jva.sentence_earnings || 426.0);
        }
        if (elements.jvaYearsNeeded) {
            elements.jvaYearsNeeded.textContent = `~${jva.years_needed || 13.7} Jahre`;
        }
        if (elements.jvaTikTokEquiv) {
            elements.jvaTikTokEquiv.textContent = `~${formatNumber(d.hours_remaining || 1649)} Stream-Std.`;
        }
    }

    function updateSimulator(coins) {
        if (!coins || coins <= 0) coins = 1;
        // 1 Coin = 0.005 USD * 0.92 EUR = ~0.0046 EUR Netto
        const netEur = coins * 0.0046;
        const rate = state.hourlyRate || 5.80;
        const hoursSavedTotal = netEur / rate;

        const hours = Math.floor(hoursSavedTotal);
        const minutes = Math.round((hoursSavedTotal - hours) * 60);

        if (elements.simCoinsText) elements.simCoinsText.textContent = `${formatNumber(coins)} Coins`;
        if (elements.simEurText) elements.simEurText.textContent = formatCurrency(netEur);
        if (elements.simHoursText) {
            if (hours > 0) {
                elements.simHoursText.textContent = `~${hours} Stunden und ${minutes} Minuten`;
            } else {
                elements.simHoursText.textContent = `~${minutes} Minuten`;
            }
        }
        if (elements.simReliefBadge) {
            if (hoursSavedTotal >= 1.0) {
                elements.simReliefBadge.textContent = `-${hoursSavedTotal.toFixed(1)} Std.`;
            } else {
                elements.simReliefBadge.textContent = `-${minutes} Min.`;
            }
        }
    }

    function renderTopGifters(gifters) {
        if (!elements.dkmTopGiftersBody) return;
        if (!gifters || gifters.length === 0) {
            elements.dkmTopGiftersBody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; padding:20px; color:#64748b;">
                        Keine Spenderdaten erfasst.
                    </td>
                </tr>
            `;
            return;
        }

        let html = "";
        gifters.forEach((g, idx) => {
            const medal = idx === 0 ? "🥇" : (idx === 1 ? "🥈" : (idx === 2 ? "🥉" : `#${idx + 1}`));
            html += `
                <tr>
                    <td class="mono" style="font-weight:800; color:#f59e0b;">${medal}</td>
                    <td>
                        <strong style="color:#f8fafc;">${escapeHtml(g.nickname || g.username)}</strong>
                        <span class="mono muted" style="font-size:11px; margin-left:4px;">@${escapeHtml(g.username)}</span>
                    </td>
                    <td class="mono" style="font-weight:700; color:#f59e0b;">${formatNumber(g.coins)}</td>
                    <td class="mono" style="font-weight:700; color:#10b981;">${formatCurrency(g.net_eur)}</td>
                    <td class="mono" style="color:#94a3b8;">${g.pct_of_target || 0} %</td>
                    <td class="mono" style="font-weight:700; color:#38bdf8;">-${g.relief_hours || 0} Std.</td>
                </tr>
            `;
        });

        elements.dkmTopGiftersBody.innerHTML = html;
    }

    function startPolling() {
        clearInterval(state.pollTimer);
        state.pollTimer = setInterval(() => {
            loadTrackerData();
        }, 6000);
    }

    // Run on DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
