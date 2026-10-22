/**
 * toktracker – Spender-Radar & Chatlog Controller
 * Handles real-time polling, whale detection, filtering, and dossier inspection.
 */

(function () {
    "use strict";

    // State
    let currentPeriod = "all";
    let selectedStreamerId = "";
    let donorSearch = "";
    let donorTier = "";
    let crossOnly = false;
    let vipOnly = false;
    let currentDossierData = null;
    let currentDossierTags = [];
    let chatSearch = "";
    let whaleOnlyChat = false;
    let chatPaused = false;
    let lastChatId = null;
    let chatMessagesList = [];
    let autoScroll = true;
    let syncIntervalId = null;
    let isFetchingChat = false;

    // DOM Elements
    const periodButtons = document.querySelectorAll(".tab-list .tab-btn");
    const filterStreamer = document.getElementById("filterStreamer");
    const chkAutoRefresh = document.getElementById("chkAutoRefresh");

    // KPI Elements
    const kpiWhalesCount = document.getElementById("kpiWhalesCount");
    const kpiSharksCount = document.getElementById("kpiSharksCount");
    const kpiDolphinsCount = document.getElementById("kpiDolphinsCount");
    const kpiCrossCount = document.getElementById("kpiCrossCount");
    const kpiVipCount = document.getElementById("kpiVipCount");
    const cardKpiVip = document.getElementById("cardKpiVip");
    const kpiChatCount = document.getElementById("kpiChatCount");

    // Donor Elements
    const donorSearchInput = document.getElementById("donorSearchInput");
    const donorTierFilter = document.getElementById("donorTierFilter");
    const chkCrossOnly = document.getElementById("chkCrossOnly");
    const chkVipOnly = document.getElementById("chkVipOnly");
    const donorTableBody = document.getElementById("donorTableBody");

    // Chat Elements
    const chatLiveBadge = document.getElementById("chatLiveBadge");
    const chatMetaCount = document.getElementById("chatMetaCount");
    const chkWhaleOnlyChat = document.getElementById("chkWhaleOnlyChat");
    const chatSearchInput = document.getElementById("chatSearchInput");
    const btnToggleChatPause = document.getElementById("btnToggleChatPause");
    const chatMessagesArea = document.getElementById("chatMessagesArea");
    const btnScrollBottom = document.getElementById("btnScrollBottom");

    // Modal Elements
    const donorModalOverlay = document.getElementById("donorModalOverlay");
    const btnCloseDonorModal = document.getElementById("btnCloseDonorModal");
    const donorModalBody = document.getElementById("donorModalBody");
    const modalDonorTierBadge = document.getElementById("modalDonorTierBadge");
    const modalCrossBadge = document.getElementById("modalCrossBadge");

    // Helper: Number Formatter
    function formatNumber(num) {
        if (num === null || num === undefined) return "0";
        return Number(num).toLocaleString("de-DE");
    }

    function formatCurrency(val, currency = "EUR") {
        if (val === null || val === undefined) return "0,00 €";
        const sym = currency === "USD" ? "$" : "€";
        return Number(val).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " " + sym;
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

    function formatTimestamp(isoStr) {
        if (!isoStr) return "-";
        try {
            const clean = isoStr.replace("T", " ");
            const parts = clean.split(" ");
            if (parts.length >= 2) {
                return parts[1].substring(0, 8);
            }
            return clean;
        } catch (e) {
            return isoStr;
        }
    }

    function renderTierBadge(tier) {
        if (tier === "whale") {
            return `<span class="tier-badge tier-whale">🐋 Whale</span>`;
        } else if (tier === "shark") {
            return `<span class="tier-badge tier-shark">🦈 Shark</span>`;
        } else if (tier === "dolphin") {
            return `<span class="tier-badge tier-dolphin">🐬 Dolphin</span>`;
        }
        return `<span class="tier-badge tier-regular">Viewer</span>`;
    }

    // Initialize Event Listeners
    function initEvents() {
        // Period tabs
        periodButtons.forEach(btn => {
            btn.addEventListener("click", () => {
                periodButtons.forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                currentPeriod = btn.dataset.period || "all";
                loadDonorRadarData();
            });
        });

        // Streamer filter
        if (filterStreamer) {
            filterStreamer.addEventListener("change", () => {
                selectedStreamerId = filterStreamer.value;
                loadDonorRadarData();
                resetAndReloadChat();
            });
        }

        // Donor search & filters
        let donorSearchTimeout;
        if (donorSearchInput) {
            donorSearchInput.addEventListener("input", () => {
                clearTimeout(donorSearchTimeout);
                donorSearchTimeout = setTimeout(() => {
                    donorSearch = donorSearchInput.value.trim();
                    loadDonorRadarData();
                }, 300);
            });
        }

        if (donorTierFilter) {
            donorTierFilter.addEventListener("change", () => {
                donorTier = donorTierFilter.value;
                loadDonorRadarData();
            });
        }

        if (chkCrossOnly) {
            chkCrossOnly.addEventListener("change", () => {
                crossOnly = chkCrossOnly.checked;
                loadDonorRadarData();
            });
        }

        if (chkVipOnly) {
            chkVipOnly.addEventListener("change", () => {
                vipOnly = chkVipOnly.checked;
                loadDonorRadarData();
            });
        }

        if (cardKpiVip) {
            cardKpiVip.addEventListener("click", () => {
                if (chkVipOnly) {
                    chkVipOnly.checked = !chkVipOnly.checked;
                    vipOnly = chkVipOnly.checked;
                    loadDonorRadarData();
                }
            });
        }

        // Chat controls
        if (chkWhaleOnlyChat) {
            chkWhaleOnlyChat.addEventListener("change", () => {
                whaleOnlyChat = chkWhaleOnlyChat.checked;
                resetAndReloadChat();
            });
        }

        let chatSearchTimeout;
        if (chatSearchInput) {
            chatSearchInput.addEventListener("input", () => {
                clearTimeout(chatSearchTimeout);
                chatSearchTimeout = setTimeout(() => {
                    chatSearch = chatSearchInput.value.trim();
                    resetAndReloadChat();
                }, 300);
            });
        }

        if (btnToggleChatPause) {
            btnToggleChatPause.addEventListener("click", () => {
                chatPaused = !chatPaused;
                if (chatPaused) {
                    btnToggleChatPause.textContent = "▶ Weiter";
                    chatLiveBadge.textContent = "PAUSIERT";
                    chatLiveBadge.className = "tag-poll mono";
                } else {
                    btnToggleChatPause.textContent = "⏸ Pause";
                    chatLiveBadge.textContent = "LIVE";
                    chatLiveBadge.className = "tag-live mono";
                    pollChatMessages();
                }
            });
        }

        if (btnScrollBottom) {
            btnScrollBottom.addEventListener("click", () => {
                autoScroll = true;
                scrollToBottom();
            });
        }

        if (chatMessagesArea) {
            chatMessagesArea.addEventListener("scroll", () => {
                const threshold = 60;
                const atBottom = chatMessagesArea.scrollHeight - chatMessagesArea.scrollTop - chatMessagesArea.clientHeight < threshold;
                autoScroll = atBottom;
            });
        }

        // Modal close
        if (btnCloseDonorModal) {
            btnCloseDonorModal.addEventListener("click", closeDonorModal);
        }
        if (donorModalOverlay) {
            donorModalOverlay.addEventListener("click", (e) => {
                if (e.target === donorModalOverlay) closeDonorModal();
            });
        }
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") closeDonorModal();
        });

        // Auto Refresh Toggle
        if (chkAutoRefresh) {
            chkAutoRefresh.addEventListener("change", () => {
                if (chkAutoRefresh.checked) {
                    startSyncLoop();
                } else {
                    stopSyncLoop();
                }
            });
        }
    }

    function scrollToBottom() {
        if (!chatMessagesArea) return;
        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;
    }

    // 1. Load Donor Radar Data
    async function loadDonorRadarData() {
        try {
            const params = new URLSearchParams({
                period: currentPeriod,
                limit: "100",
            });
            if (selectedStreamerId) params.append("streamer_id", selectedStreamerId);
            if (donorSearch) params.append("search", donorSearch);
            if (donorTier) params.append("min_tier", donorTier);
            if (crossOnly) params.append("cross_streamer_only", "true");
            if (vipOnly) params.append("vip_only", "true");

            const res = await fetch(`/api/donor-radar?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (!json.ok) throw new Error(json.error || "Fehler beim Laden");

            renderKPIs(json.data.kpis);
            renderDonorTable(json.data.donors);
            populateStreamerDropdown(json.data.streamers);
        } catch (err) {
            console.error("Fehler beim Abrufen des Spender-Radars:", err);
            if (donorTableBody) {
                donorTableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:#f85149; padding:20px;">Fehler beim Laden der Spenderdaten (${escapeHtml(err.message)})</td></tr>`;
            }
        }
    }

    // Render KPIs
    function renderKPIs(kpis) {
        if (!kpis) return;
        if (kpiWhalesCount) kpiWhalesCount.textContent = formatNumber(kpis.whales);
        if (kpiSharksCount) kpiSharksCount.textContent = formatNumber(kpis.sharks);
        if (kpiDolphinsCount) kpiDolphinsCount.textContent = formatNumber(kpis.dolphins);
        if (kpiCrossCount) kpiCrossCount.textContent = formatNumber(kpis.cross_streamer_whales);
        if (kpiVipCount) kpiVipCount.textContent = formatNumber(kpis.vip_donors || 0);
        if (kpiChatCount) kpiChatCount.textContent = formatNumber(kpis.total_chat_messages);
    }

    // Populate Streamers Dropdown
    let streamersPopulated = false;
    function populateStreamerDropdown(streamers) {
        if (streamersPopulated || !streamers || !filterStreamer) return;
        const currentVal = filterStreamer.value;
        filterStreamer.innerHTML = `<option value="">Alle Streamer</option>`;
        streamers.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = `${s.display_name || s.username} (@${s.username})${s.is_live ? " [LIVE]" : ""}`;
            filterStreamer.appendChild(opt);
        });
        filterStreamer.value = currentVal;
        streamersPopulated = true;
    }

    // Render Donor Table
    function renderDonorTable(donors) {
        if (!donorTableBody) return;
        if (!donors || donors.length === 0) {
            donorTableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">Keine Spender für die gewählten Filter gefunden.</td></tr>`;
            return;
        }

        let html = "";
        donors.forEach((d, idx) => {
            const uname = escapeHtml(d.username);
            const dname = escapeHtml(d.display_name || d.username);
            const tierBadge = renderTierBadge(d.tier);
            const crossBadge = d.is_cross_streamer
                ? `<span class="tag-cross-streamer" title="Beschenkt ${d.streamer_count} verschiedene Streamer">⚡ ${d.streamer_count} Kanäle</span>`
                : "";

            const isVip = Boolean(d.is_vip);
            const starTitle = isVip ? "Von VIP-Watchlist entfernen" : "Auf VIP-Watchlist setzen";
            const starChar = isVip ? "★" : "☆";
            const starBtn = `<button type="button" class="vip-star-btn ${isVip ? 'is-vip' : ''}" onclick="window.tokRadar.toggleVipQuick('${uname}', event)" title="${starTitle}">${starChar}</button>`;

            const tagsList = Array.isArray(d.tags) ? d.tags : [];
            const tagsHtml = tagsList.length > 0
                ? tagsList.map(t => `<span class="crm-tag-pill">${escapeHtml(t)}</span>`).join(" ")
                : "";

            const notesIcon = d.has_notes
                ? `<span class="crm-notes-badge" title="Notizen hinterlegt: ${escapeHtml(d.notes || '')}">📝</span>`
                : "";

            html += `
                <tr>
                    <td class="mono muted">${idx + 1}</td>
                    <td class="hide-sm">${tierBadge}</td>
                    <td>
                        <div style="display:flex; align-items:center; gap:8px;">
                            ${starBtn}
                            <div style="display:flex; flex-direction:column;">
                                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                                    <strong style="color:var(--text-strong); cursor:pointer;" onclick="window.tokRadar.openDossier('${uname}')">${dname}</strong>
                                    ${crossBadge}
                                    ${notesIcon}
                                </div>
                                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:2px;">
                                    <span class="mono muted" style="font-size:11px;">@${uname}</span>
                                    ${tagsHtml}
                                </div>
                            </div>
                        </div>
                    </td>
                    <td class="num-col mono" style="font-weight:700; color:#38bdf8;">${formatNumber(d.total_coins)}</td>
                    <td class="num-col mono" style="font-weight:700; color:#4ade80;">${formatCurrency(d.total_eur_net, "EUR")}</td>
                    <td class="num-col mono muted hide-sm">${formatCurrency(d.total_usd_net, "USD")}</td>
                    <td class="num-col mono hide-md">${formatNumber(d.streamer_count)}</td>
                    <td class="mono muted hide-sm" style="font-size:11.5px;">${escapeHtml(d.last_seen || "-")}</td>
                    <td style="text-align: right;">
                        <button type="button" class="btn-link sm" onclick="window.tokRadar.openDossier('${uname}')" style="font-size:11.5px; padding:3px 8px;">
                            Dossier →
                        </button>
                    </td>
                </tr>
            `;
        });

        donorTableBody.innerHTML = html;
    }

    // 2. Chatlogs System
    async function resetAndReloadChat() {
        lastChatId = null;
        chatMessagesList = [];
        if (chatMessagesArea) {
            chatMessagesArea.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:40px;">Lade Chatnachrichten...</div>`;
        }
        await pollChatMessages();
    }

    async function pollChatMessages() {
        if (chatPaused || isFetchingChat) return;
        isFetchingChat = true;

        try {
            const params = new URLSearchParams({
                limit: lastChatId ? "50" : "80",
            });
            if (selectedStreamerId) params.append("streamer_id", selectedStreamerId);
            if (chatSearch) params.append("search", chatSearch);
            if (whaleOnlyChat) params.append("only_whales", "true");
            if (lastChatId) params.append("after_id", lastChatId);

            const res = await fetch(`/api/chat-logs?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (!json.ok) throw new Error(json.error || "Fehler");

            const newMsgs = json.messages || [];

            if (!lastChatId) {
                // Initial load: messages came in DESC order, reverse them to chronological (oldest to newest)
                newMsgs.reverse();
                chatMessagesList = newMsgs;
                if (chatMessagesList.length > 0) {
                    lastChatId = chatMessagesList[chatMessagesList.length - 1].id;
                }
                renderAllChatMessages();
            } else if (newMsgs.length > 0) {
                // Live streaming: messages arrived in ASC order
                newMsgs.forEach(m => {
                    chatMessagesList.push(m);
                    appendChatBubble(m);
                });
                // Cap list length to 300
                if (chatMessagesList.length > 300) {
                    chatMessagesList = chatMessagesList.slice(-300);
                    // Remove excess elements from top of DOM
                    while (chatMessagesArea.children.length > 300) {
                        chatMessagesArea.removeChild(chatMessagesArea.firstElementChild);
                    }
                }
                lastChatId = newMsgs[newMsgs.length - 1].id;
                if (autoScroll) scrollToBottom();
            }

            if (chatMetaCount) {
                chatMetaCount.textContent = `${chatMessagesList.length} Nachrichten`;
            }
        } catch (err) {
            console.error("Fehler beim Abrufen der Chatnachrichten:", err);
        } finally {
            isFetchingChat = false;
        }
    }

    function renderAllChatMessages() {
        if (!chatMessagesArea) return;
        if (chatMessagesList.length === 0) {
            chatMessagesArea.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:40px;">Noch keine Chatnachrichten aufgezeichnet. Sobald ein Streamer live ist, erscheinen Nachrichten hier in Echtzeit.</div>`;
            return;
        }

        let html = "";
        chatMessagesList.forEach(m => {
            html += generateChatBubbleHtml(m);
        });
        chatMessagesArea.innerHTML = html;
        if (autoScroll) scrollToBottom();
    }

    function appendChatBubble(m) {
        if (!chatMessagesArea) return;
        // If empty placeholder is shown, clear it
        if (chatMessagesList.length === 1) {
            chatMessagesArea.innerHTML = "";
        }
        const temp = document.createElement("div");
        temp.innerHTML = generateChatBubbleHtml(m);
        const bubbleEl = temp.firstElementChild;
        if (bubbleEl) {
            chatMessagesArea.appendChild(bubbleEl);
        }
    }

    function generateChatBubbleHtml(m) {
        const tier = m.whale_tier || (m.is_whale ? "dolphin" : "");
        const tierBadge = tier ? renderTierBadge(tier) : "";
        const bubbleClass = tier ? `chat-bubble bubble-${tier}` : "chat-bubble";
        const uname = escapeHtml(m.username);
        const nick = escapeHtml(m.nickname || m.username);
        const comment = escapeHtml(m.comment);
        const timeStr = formatTimestamp(m.created_at);
        const streamerName = escapeHtml(m.streamer_display_name || m.streamer_username || "");

        const avatar = m.avatar_url
            ? `<img src="${escapeHtml(m.avatar_url)}" class="chat-avatar" alt="" onerror="this.style.display='none'" />`
            : `<div class="chat-avatar" style="display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--text-muted);">${uname.charAt(0).toUpperCase()}</div>`;

        return `
            <div class="${bubbleClass}">
                <div class="chat-user-line">
                    <div class="chat-user-info">
                        ${avatar}
                        <span class="chat-donor-link" onclick="window.tokRadar.openDossier('${uname}')" title="Spender-Dossier öffnen">${nick}</span>
                        <span class="mono muted" style="font-size:11px;">@${uname}</span>
                        ${tierBadge}
                    </div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span class="chat-streamer-badge" title="Stream">@${streamerName}</span>
                        <span class="chat-time">${timeStr}</span>
                    </div>
                </div>
                <div class="chat-text">${comment}</div>
            </div>
        `;
    }

    // 3. Spender-Dossier Modal
    async function openDossier(username) {
        if (!donorModalOverlay || !donorModalBody) return;
        donorModalOverlay.style.display = "flex";
        donorModalBody.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:40px;">Lade Spender-Dossier für @${escapeHtml(username)}...</div>`;
        if (modalDonorTierBadge) modalDonorTierBadge.innerHTML = "";
        if (modalCrossBadge) modalCrossBadge.innerHTML = "";

        try {
            const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(username)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (!json.ok || !json.data) throw new Error(json.error || "Nicht gefunden");

            renderDonorDossier(json.data);
        } catch (err) {
            console.error("Dossier-Fehler:", err);
            donorModalBody.innerHTML = `<div style="text-align:center; color:#f85149; padding:30px;">Fehler beim Laden des Dossiers (${escapeHtml(err.message)})</div>`;
        }
    }

    function renderDonorDossier(data) {
        const p = data.profile;
        if (!p) return;

        if (modalDonorTierBadge) {
            modalDonorTierBadge.innerHTML = renderTierBadge(p.tier);
        }
        if (modalCrossBadge) {
            modalCrossBadge.innerHTML = p.is_cross_streamer
                ? `<span class="tag-cross-streamer">⚡ Cross-Streamer (${p.streamer_count} Kanäle)</span>`
                : "";
        }

        const avatar = p.avatar_url
            ? `<img src="${escapeHtml(p.avatar_url)}" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid var(--border-strong);" alt="" onerror="this.style.display='none'" />`
            : `<div style="width:48px;height:48px;border-radius:50%;background:var(--bg-subtle);border:2px solid var(--border-color);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--text-muted);">${(p.username||"?").charAt(0).toUpperCase()}</div>`;

        // Streamers breakdown table
        let streamersHtml = "";
        if (data.streamers && data.streamers.length > 0) {
            data.streamers.forEach(s => {
                const sName = escapeHtml(s.streamer_display_name || s.streamer_username);
                const sUname = escapeHtml(s.streamer_username);
                streamersHtml += `
                    <tr>
                        <td>
                            <strong style="color:var(--text-strong);">${sName}</strong>
                            <span class="mono muted" style="font-size:11px; margin-left:4px;">@${sUname}</span>
                        </td>
                        <td class="num-col mono" style="font-weight:700; color:#38bdf8;">${formatNumber(s.coins_given)}</td>
                        <td class="num-col mono" style="color:#4ade80;">${formatCurrency(s.eur_net, "EUR")}</td>
                        <td class="num-col mono">${formatNumber(s.gift_count)}</td>
                        <td class="mono muted" style="font-size:11px;">${escapeHtml(s.last_gift_at || "-")}</td>
                    </tr>
                `;
            });
        } else {
            streamersHtml = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:14px;">Bisher keine Geschenke zugeordnet.</td></tr>`;
        }

        // Top gifts list
        let giftsHtml = "";
        if (data.top_gifts && data.top_gifts.length > 0) {
            data.top_gifts.forEach(g => {
                const icon = g.gift_icon_url
                    ? `<img src="${escapeHtml(g.gift_icon_url)}" style="width:24px;height:24px;object-fit:contain;" alt="" onerror="this.style.display='none'" />`
                    : `<span style="font-size:16px;">🎁</span>`;
                giftsHtml += `
                    <div style="background:var(--bg-subtle); border:1px solid var(--border-color); border-radius:6px; padding:10px; display:flex; align-items:center; justify-content:space-between;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            ${icon}
                            <div>
                                <strong style="font-size:12.5px;">${escapeHtml(g.gift_name)}</strong>
                                <div class="mono muted" style="font-size:11px;">${formatNumber(g.total_sent)}x gesendet</div>
                            </div>
                        </div>
                        <div class="mono" style="font-weight:700; color:#38bdf8; font-size:12.5px;">
                            ${formatNumber(g.total_coins)} Coins
                        </div>
                    </div>
                `;
            });
        } else {
            giftsHtml = `<div style="color:var(--text-muted); font-size:12px; grid-column:1/-1;">Keine spezifischen Geschenke erfasst.</div>`;
        }

        // Recent chat comments
        let chatsHtml = "";
        if (data.recent_chats && data.recent_chats.length > 0) {
            data.recent_chats.forEach(c => {
                chatsHtml += `
                    <div style="background:var(--bg-subtle); border:1px solid var(--border-subtle); border-radius:4px; padding:8px 10px; font-size:12px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:10.5px; color:var(--text-muted);">
                            <span class="mono">Stream: @${escapeHtml(c.streamer_username)}</span>
                            <span class="mono">${formatTimestamp(c.created_at)}</span>
                        </div>
                        <div style="color:var(--text-main); line-height:1.35;">${escapeHtml(c.comment)}</div>
                    </div>
                `;
            });
        } else {
            chatsHtml = `<div style="color:var(--text-muted); font-size:12px;">Keine Chatnachrichten in den letzten 7 Tagen archiviert.</div>`;
        }

        // CRM & Dossier State
        currentDossierData = data;
        const crm = data.crm || { is_vip: false, tags: [], notes: "", updated_at: null };
        currentDossierTags = Array.isArray(crm.tags) ? [...crm.tags] : [];

        donorModalBody.innerHTML = `
            <!-- Top Profile Card -->
            <div style="background:var(--bg-subtle); border:1px solid var(--border-color); border-radius:8px; padding:16px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px;">
                <div style="display:flex; align-items:center; gap:14px;">
                    ${avatar}
                    <div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <h3 style="margin:0; font-size:18px; color:var(--text-strong);">${escapeHtml(p.display_name)}</h3>
                            <button type="button" class="vip-star-btn ${crm.is_vip ? 'is-vip' : ''}" onclick="window.tokRadar.toggleModalVip()" title="VIP-Status umschalten" style="font-size:18px;">
                                ${crm.is_vip ? '★' : '☆'}
                            </button>
                        </div>
                        <div class="mono muted" style="font-size:12px;">@${escapeHtml(p.username)}</div>
                        <div style="margin-top:4px; font-size:11.5px; color:var(--text-muted);">
                            Aktiv: <span class="mono">${escapeHtml(p.first_seen || "-")}</span> bis <span class="mono">${escapeHtml(p.last_seen || "-")}</span>
                        </div>
                    </div>
                </div>

                <div style="display:flex; gap:16px; flex-wrap:wrap;">
                    <div style="text-align:right;">
                        <div class="mono muted" style="font-size:11px;">GESAMT COINS</div>
                        <div class="mono" style="font-size:20px; font-weight:800; color:#38bdf8;">${formatNumber(p.total_coins)}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="mono muted" style="font-size:11px;">NETTO (CREATOR)</div>
                        <div class="mono" style="font-size:20px; font-weight:800; color:#4ade80;">${formatCurrency(p.total_eur_net, "EUR")}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="mono muted" style="font-size:11px;">BRUTTO (KAUF)</div>
                        <div class="mono" style="font-size:20px; font-weight:800; color:#fbbf24;">${formatCurrency(p.total_eur_gross, "EUR")}</div>
                    </div>
                </div>
            </div>

            <!-- CRM & VIP Watchlist Section -->
            <div class="crm-card">
                <div class="crm-card-header">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:16px;">⭐</span>
                        <strong style="font-size:14px; color:var(--text-strong);">Gifter-CRM &amp; VIP-Watchlist</strong>
                        <span id="crmSaveStatus" class="mono" style="font-size:11px; color:#4ade80; display:none; margin-left:6px; font-weight:700;">✓ Gespeichert</span>
                    </div>
                    <button type="button" id="modalBtnToggleVip" class="crm-vip-toggle ${crm.is_vip ? 'active' : ''}" onclick="window.tokRadar.toggleModalVip()">
                        ${crm.is_vip ? '★ Auf VIP-Watchlist' : '☆ Nicht auf Watchlist'}
                    </button>
                </div>

                <!-- Tags Management -->
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Tags &amp; Einstufung:</span>
                    </div>
                    <div id="modalActiveTags" style="display:flex; flex-wrap:wrap; gap:6px; min-height:24px; align-items:center;">
                        ${renderModalTagsHtml(currentDossierTags)}
                    </div>
                    
                    <!-- Quick Tag Suggestions & Custom Input -->
                    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-top:10px;">
                        <div style="display:flex; align-items:center; gap:5px; flex-wrap:wrap;">
                            <span class="mono muted" style="font-size:10.5px;">Vorschläge:</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('Mega-Wal')">+ Mega-Wal</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('Agentur-Chef')">+ Agentur-Chef</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('Match-Sniper')">+ Match-Sniper</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('Stamm-Gifter')">+ Stamm-Gifter</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('High-Roller')">+ High-Roller</span>
                            <span class="crm-quick-tag" onclick="window.tokRadar.addModalTag('Troll/Fake')">+ Troll/Fake</span>
                        </div>

                        <div style="display:flex; align-items:center; gap:6px;">
                            <input type="text" id="modalNewTagInput" placeholder="Neuer Tag..." style="padding:4px 8px; font-size:11.5px; background:var(--bg-surface); color:var(--text-main); border:1px solid var(--border-color); border-radius:4px; width:130px;" onkeydown="if(event.key==='Enter'){event.preventDefault(); window.tokRadar.addCustomModalTag();}" />
                            <button type="button" class="btn-link sm" onclick="window.tokRadar.addCustomModalTag()" style="padding:3px 8px; font-size:11.5px;">+ Tag</button>
                        </div>
                    </div>
                </div>

                <!-- Notes Management -->
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <label for="modalNotesTextarea" style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Interne Admin-Notizen:</label>
                        <span class="mono muted" style="font-size:10.5px;">Stand: <span id="modalCrmUpdated">${escapeHtml(crm.updated_at ? formatTimestamp(crm.updated_at) : 'Keine')}</span></span>
                    </div>
                    <textarea id="modalNotesTextarea" class="crm-notes-textarea" placeholder="Interne Notizen zu diesem Spender (z. B. Streamer-Präferenzen, Taktik bei Matches, Agentur-Zugehörigkeit, Hintergrundinfos)...">${escapeHtml(crm.notes || "")}</textarea>
                    <div style="display:flex; justify-content:flex-end; margin-top:8px;">
                        <button type="button" id="btnSaveCrmNotes" class="btn-link primary sm" onclick="window.tokRadar.saveModalCrm(true)" style="padding:5px 14px; font-size:12px;">
                            💾 Notizen &amp; Tags speichern
                        </button>
                    </div>
                </div>
            </div>

            <!-- Section 1: Streamer Breakdown -->
            <div>
                <h4 style="margin:0 0 10px 0; font-size:14px; display:flex; align-items:center; gap:6px;">
                    <span>📊 Geschenke pro Streamer</span>
                    <span class="mono muted" style="font-size:11px;">(${data.streamers ? data.streamers.length : 0} Kanäle)</span>
                </h4>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Streamer</th>
                                <th class="num-col">Coins</th>
                                <th class="num-col">Netto (EUR)</th>
                                <th class="num-col">Geschenke</th>
                                <th>Letztes Geschenk</th>
                            </tr>
                        </thead>
                        <tbody>${streamersHtml}</tbody>
                    </table>
                </div>
            </div>

            <!-- Section 2: Top Gifts -->
            <div>
                <h4 style="margin:0 0 10px 0; font-size:14px;">🎁 Lieblingsgeschenke</h4>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px;">
                    ${giftsHtml}
                </div>
            </div>

            <!-- Section 3: Recent Chat Messages -->
            <div>
                <h4 style="margin:0 0 10px 0; font-size:14px;">💬 Letzte Chat-Nachrichten (Archiv)</h4>
                <div style="display:flex; flex-direction:column; gap:8px; max-height:220px; overflow-y:auto; padding-right:4px;">
                    ${chatsHtml}
                </div>
            </div>
        `;
    }

    function renderModalTagsHtml(tags) {
        if (!tags || tags.length === 0) {
            return `<span class="mono muted" style="font-size:11px;">Keine Tags zugewiesen. Wähle unten einen Vorschlag oder erstelle einen neuen Tag.</span>`;
        }
        return tags.map((t, idx) => `
            <span class="crm-tag-pill">
                ${escapeHtml(t)}
                <span class="tag-del-btn" onclick="window.tokRadar.removeModalTag(${idx})" title="Tag entfernen">×</span>
            </span>
        `).join("");
    }

    // Quick toggle VIP from Table
    async function toggleVipQuick(username, evt) {
        if (evt) evt.stopPropagation();
        try {
            const btn = evt ? evt.currentTarget : null;
            if (btn) btn.style.transform = "scale(1.4)";
            const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(username)}/toggle-vip`, {
                method: "POST"
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (json.ok) {
                loadDonorRadarData();
            }
        } catch (e) {
            console.error("Fehler beim Umschalten des VIP-Status:", e);
        }
    }

    // Toggle VIP inside Dossier Modal
    async function toggleModalVip() {
        if (!currentDossierData || !currentDossierData.profile) return;
        const uname = currentDossierData.profile.username;
        try {
            const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(uname)}/toggle-vip`, {
                method: "POST"
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (json.ok && json.data) {
                currentDossierData.crm = json.data;
                const isVip = Boolean(json.data.is_vip);
                const btn = document.getElementById("modalBtnToggleVip");
                if (btn) {
                    btn.className = `crm-vip-toggle ${isVip ? 'active' : ''}`;
                    btn.innerHTML = isVip ? '★ Auf VIP-Watchlist' : '☆ Nicht auf Watchlist';
                }
                showCrmSaveStatus();
                loadDonorRadarData();
            }
        } catch (e) {
            console.error("Fehler beim Umschalten des VIP-Status:", e);
        }
    }

    // Add Tag
    function addModalTag(tag) {
        const cleanTag = String(tag || "").trim().replace(/,/g, "");
        if (!cleanTag) return;
        if (!currentDossierTags.includes(cleanTag)) {
            currentDossierTags.push(cleanTag);
            const container = document.getElementById("modalActiveTags");
            if (container) container.innerHTML = renderModalTagsHtml(currentDossierTags);
            saveModalCrm(false);
        }
    }

    function addCustomModalTag() {
        const input = document.getElementById("modalNewTagInput");
        if (!input) return;
        const val = input.value.trim();
        if (val) {
            addModalTag(val);
            input.value = "";
        }
    }

    function removeModalTag(idx) {
        if (idx >= 0 && idx < currentDossierTags.length) {
            currentDossierTags.splice(idx, 1);
            const container = document.getElementById("modalActiveTags");
            if (container) container.innerHTML = renderModalTagsHtml(currentDossierTags);
            saveModalCrm(false);
        }
    }

    // Save Notes & Tags
    async function saveModalCrm(showNotification = true) {
        if (!currentDossierData || !currentDossierData.profile) return;
        const uname = currentDossierData.profile.username;
        const textarea = document.getElementById("modalNotesTextarea");
        const notes = textarea ? textarea.value.trim() : (currentDossierData.crm ? currentDossierData.crm.notes : "");

        try {
            const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(uname)}/crm`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    is_vip: currentDossierData.crm ? currentDossierData.crm.is_vip : false,
                    tags: currentDossierTags,
                    notes: notes,
                })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (json.ok && json.data) {
                currentDossierData.crm = json.data;
                const updatedSpan = document.getElementById("modalCrmUpdated");
                if (updatedSpan && json.data.updated_at) {
                    updatedSpan.textContent = formatTimestamp(json.data.updated_at);
                }
                if (showNotification) {
                    showCrmSaveStatus();
                }
                loadDonorRadarData();
            }
        } catch (e) {
            console.error("Fehler beim Speichern der CRM-Daten:", e);
            if (showNotification) alert("Fehler beim Speichern der Notizen.");
        }
    }

    function showCrmSaveStatus() {
        const el = document.getElementById("crmSaveStatus");
        if (!el) return;
        el.style.display = "inline";
        el.style.opacity = "1";
        setTimeout(() => {
            el.style.display = "none";
        }, 2500);
    }

    function closeDonorModal() {
        if (donorModalOverlay) donorModalOverlay.style.display = "none";
    }

    // Polling Sync Loop
    function startSyncLoop() {
        stopSyncLoop();
        syncIntervalId = setInterval(() => {
            pollChatMessages();
        }, 3000);
    }

    function stopSyncLoop() {
        if (syncIntervalId) {
            clearInterval(syncIntervalId);
            syncIntervalId = null;
        }
    }

    // Export globally for inline onclick
    window.tokRadar = {
        openDossier: openDossier,
        toggleVipQuick: toggleVipQuick,
        toggleModalVip: toggleModalVip,
        addModalTag: addModalTag,
        addCustomModalTag: addCustomModalTag,
        removeModalTag: removeModalTag,
        saveModalCrm: saveModalCrm,
    };

    // Initialize on DOM Ready
    document.addEventListener("DOMContentLoaded", () => {
        initEvents();
        loadDonorRadarData();
        pollChatMessages();
        startSyncLoop();
    });

})();
