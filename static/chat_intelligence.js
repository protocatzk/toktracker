/**
 * TokTracker – Chat Intelligence, Wortwolke & Stream-Log Viewer
 * Frontend Controller (Vanilla JavaScript)
 */
(function() {
    "use strict";

    // State
    const state = {
        streamerId: "",
        sessionId: "",
        period: "24h",
        minWordLen: 3,
        searchTerm: "",
        activeFilterWord: "",
        onlyWhales: false,
        isLiveTail: true,
        activeTab: "phrases", // "phrases" | "emojis"
        messages: [],
        oldestMsgId: null,
        newestMsgId: null,
        isFetchingAnalysis: false,
        isFetchingMessages: false,
        pollTimer: null,
    };

    // DOM Elements
    const elements = {
        selectStreamer: document.getElementById("selectStreamer"),
        selectSession: document.getElementById("selectSession"),
        periodPills: document.getElementById("periodPills"),
        selectMinWordLen: document.getElementById("selectMinWordLen"),
        btnRefreshAnalysis: document.getElementById("btnRefreshAnalysis"),
        btnExportMenu: document.getElementById("btnExportMenu"),

        // KPIs
        kpiTotalMsgs: document.getElementById("kpiTotalMsgs"),
        kpiAvgChars: document.getElementById("kpiAvgChars"),
        kpiUniqueChatters: document.getElementById("kpiUniqueChatters"),
        kpiDiversity: document.getElementById("kpiDiversity"),
        kpiWhaleMsgs: document.getElementById("kpiWhaleMsgs"),
        kpiWhaleShare: document.getElementById("kpiWhaleShare"),
        kpiTopChatter: document.getElementById("kpiTopChatter"),
        kpiTopChatterCount: document.getElementById("kpiTopChatterCount"),

        // Word Cloud & Phrases
        wordCloudContainer: document.getElementById("wordCloudContainer"),
        wordCloudCountBadge: document.getElementById("wordCloudCountBadge"),
        tabBtnPhrases: document.getElementById("tabBtnPhrases"),
        tabBtnEmojis: document.getElementById("tabBtnEmojis"),
        phrasesListContainer: document.getElementById("phrasesListContainer"),
        emojisGridContainer: document.getElementById("emojisGridContainer"),

        // Log Viewer
        inputChatSearch: document.getElementById("inputChatSearch"),
        activeFilterPill: document.getElementById("activeFilterPill"),
        activeFilterText: document.getElementById("activeFilterText"),
        btnClearWordFilter: document.getElementById("btnClearWordFilter"),
        chkOnlyWhales: document.getElementById("chkOnlyWhales"),
        btnToggleLiveTail: document.getElementById("btnToggleLiveTail"),
        liveTailDot: document.getElementById("liveTailDot"),
        liveTailText: document.getElementById("liveTailText"),
        btnExportCsvDirect: document.getElementById("btnExportCsvDirect"),
        viewerMsgCountMeta: document.getElementById("viewerMsgCountMeta"),
        chatStreamArea: document.getElementById("chatStreamArea"),
        btnLoadOlderMsgs: document.getElementById("btnLoadOlderMsgs"),
        streamSessionInfoText: document.getElementById("streamSessionInfoText"),

        // Export Modal
        exportModal: document.getElementById("exportModal"),
        btnCloseExportModal: document.getElementById("btnCloseExportModal"),
        btnDownloadCsv: document.getElementById("btnDownloadCsv"),
        btnDownloadTxt: document.getElementById("btnDownloadTxt"),
    };

    // Utility Helpers
    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatNumber(num) {
        if (num === null || num === undefined) return "0";
        return new Intl.NumberFormat("de-DE").format(num);
    }

    function formatTime(isoStr) {
        if (!isoStr) return "";
        const parts = isoStr.split(" ");
        if (parts.length > 1) {
            return parts[1].substring(0, 8);
        }
        return isoStr.substring(11, 19) || isoStr;
    }

    function highlightText(text, query) {
        if (!query || !text) return escapeHtml(text);
        const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const regex = new RegExp(`(${safeQuery})`, "gi");
        const escaped = escapeHtml(text);
        return escaped.replace(regex, '<span class="highlight-term">$1</span>');
    }

    // 1. Initialize
    async function init() {
        bindEvents();
        await loadStreamers();
        await loadSessions();
        await loadAnalysis();
        await loadMessages(false);
        startPolling();
    }

    // 2. Bind UI Events
    function bindEvents() {
        // Streamer Select
        if (elements.selectStreamer) {
            elements.selectStreamer.addEventListener("change", async (e) => {
                state.streamerId = e.target.value;
                state.sessionId = "";
                await loadSessions();
                triggerFullRefresh();
            });
        }

        // Session Select
        if (elements.selectSession) {
            elements.selectSession.addEventListener("change", (e) => {
                state.sessionId = e.target.value;
                updateSessionInfoLabel();
                triggerFullRefresh();
            });
        }

        // Period Pills
        if (elements.periodPills) {
            elements.periodPills.querySelectorAll(".ci-period-btn").forEach(btn => {
                btn.addEventListener("click", () => {
                    elements.periodPills.querySelectorAll(".ci-period-btn").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    state.period = btn.getAttribute("data-period") || "24h";
                    triggerFullRefresh();
                });
            });
        }

        // Min Word Length
        if (elements.selectMinWordLen) {
            elements.selectMinWordLen.addEventListener("change", (e) => {
                state.minWordLen = parseInt(e.target.value, 10) || 3;
                loadAnalysis();
            });
        }

        // Refresh Button
        if (elements.btnRefreshAnalysis) {
            elements.btnRefreshAnalysis.addEventListener("click", () => {
                triggerFullRefresh();
            });
        }

        // Phrases / Emojis Tabs
        if (elements.tabBtnPhrases && elements.tabBtnEmojis) {
            elements.tabBtnPhrases.addEventListener("click", () => {
                state.activeTab = "phrases";
                elements.tabBtnPhrases.classList.add("active");
                elements.tabBtnEmojis.classList.remove("active");
                elements.phrasesListContainer.style.display = "flex";
                elements.emojisGridContainer.style.display = "none";
            });

            elements.tabBtnEmojis.addEventListener("click", () => {
                state.activeTab = "emojis";
                elements.tabBtnEmojis.classList.add("active");
                elements.tabBtnPhrases.classList.remove("active");
                elements.phrasesListContainer.style.display = "none";
                elements.emojisGridContainer.style.display = "grid";
            });
        }

        // Search Input (Debounced)
        let searchTimer = null;
        if (elements.inputChatSearch) {
            elements.inputChatSearch.addEventListener("input", (e) => {
                clearTimeout(searchTimer);
                searchTimer = setTimeout(() => {
                    state.searchTerm = e.target.value.trim();
                    loadMessages(false);
                }, 300);
            });
        }

        // Clear Word Filter
        if (elements.btnClearWordFilter) {
            elements.btnClearWordFilter.addEventListener("click", () => {
                clearWordFilter();
            });
        }

        // Whale only checkbox
        if (elements.chkOnlyWhales) {
            elements.chkOnlyWhales.addEventListener("change", (e) => {
                state.onlyWhales = e.target.checked;
                loadMessages(false);
            });
        }

        // Live Tail Toggle
        if (elements.btnToggleLiveTail) {
            elements.btnToggleLiveTail.addEventListener("click", () => {
                state.isLiveTail = !state.isLiveTail;
                if (elements.liveTailDot) {
                    elements.liveTailDot.style.background = state.isLiveTail ? "#10b981" : "#64748b";
                }
                if (elements.liveTailText) {
                    elements.liveTailText.textContent = state.isLiveTail ? "Live-Tail: An" : "Live-Tail: Pausiert";
                }
                if (state.isLiveTail) {
                    scrollChatToBottom();
                }
            });
        }

        // Load Older Messages
        if (elements.btnLoadOlderMsgs) {
            elements.btnLoadOlderMsgs.addEventListener("click", () => {
                loadOlderMessages();
            });
        }

        // Export Modal & Downloads
        if (elements.btnExportMenu) {
            elements.btnExportMenu.addEventListener("click", () => {
                elements.exportModal.style.display = "flex";
            });
        }
        if (elements.btnCloseExportModal) {
            elements.btnCloseExportModal.addEventListener("click", () => {
                elements.exportModal.style.display = "none";
            });
        }
        if (elements.exportModal) {
            elements.exportModal.addEventListener("click", (e) => {
                if (e.target === elements.exportModal) {
                    elements.exportModal.style.display = "none";
                }
            });
        }
        if (elements.btnDownloadCsv) {
            elements.btnDownloadCsv.addEventListener("click", () => {
                triggerExportDownload("csv");
                elements.exportModal.style.display = "none";
            });
        }
        if (elements.btnDownloadTxt) {
            elements.btnDownloadTxt.addEventListener("click", () => {
                triggerExportDownload("txt");
                elements.exportModal.style.display = "none";
            });
        }
        if (elements.btnExportCsvDirect) {
            elements.btnExportCsvDirect.addEventListener("click", () => {
                triggerExportDownload("csv");
            });
        }
    }

    function triggerFullRefresh() {
        loadAnalysis();
        loadMessages(false);
    }

    function setWordFilter(word) {
        state.activeFilterWord = word;
        if (elements.activeFilterPill && elements.activeFilterText) {
            elements.activeFilterText.textContent = word;
            elements.activeFilterPill.style.display = "inline-flex";
        }
        // Highlight active word in cloud
        document.querySelectorAll(".cloud-word").forEach(el => {
            if (el.getAttribute("data-word") === word) {
                el.classList.add("active-filter");
            } else {
                el.classList.remove("active-filter");
            }
        });
        loadMessages(false);

        // Smooth scroll down to chat viewer
        const viewerSection = document.getElementById("chatViewerSection");
        if (viewerSection) {
            viewerSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function clearWordFilter() {
        state.activeFilterWord = "";
        if (elements.activeFilterPill) {
            elements.activeFilterPill.style.display = "none";
        }
        document.querySelectorAll(".cloud-word").forEach(el => {
            el.classList.remove("active-filter");
        });
        loadMessages(false);
    }

    function updateSessionInfoLabel() {
        if (!elements.streamSessionInfoText) return;
        if (!state.sessionId) {
            elements.streamSessionInfoText.textContent = "Alle Streams";
            return;
        }
        const opt = elements.selectSession ? elements.selectSession.selectedOptions[0] : null;
        if (opt) {
            elements.streamSessionInfoText.textContent = `Session #${state.sessionId} (${opt.textContent})`;
        }
    }

    // 3. API Loaders
    async function loadStreamers() {
        try {
            const res = await fetch("/api/overview?period=all");
            if (!res.ok) return;
            const data = await res.json();
            const streamers = data.streamers || [];

            if (elements.selectStreamer) {
                let html = '<option value="">Alle Streamer</option>';
                streamers.forEach(s => {
                    const isLive = s.is_live ? "🔴 " : "";
                    const name = s.display_name ? `${s.display_name} (@${s.username})` : `@${s.username}`;
                    html += `<option value="${s.id}">${isLive}${escapeHtml(name)}</option>`;
                });
                elements.selectStreamer.innerHTML = html;
            }
        } catch (e) {
            console.error("Fehler loadStreamers:", e);
        }
    }

    async function loadSessions() {
        try {
            let url = "/api/chat-intelligence/sessions?limit=80";
            if (state.streamerId) {
                url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
            }
            const res = await fetch(url);
            if (!res.ok) return;
            const data = await res.json();
            const sessions = data.sessions || [];

            if (elements.selectSession) {
                let html = '<option value="">Alle Streams des Zeitraums</option>';
                sessions.forEach(ss => {
                    const isLive = ss.status === "active";
                    const livePrefix = isLive ? "🔴 LIVE: " : "";
                    const streamerName = `@${ss.streamer_username}`;
                    const timeStr = ss.started_at ? ss.started_at.substring(0, 16).replace("T", " ") : "";
                    const countStr = formatNumber(ss.chat_count || 0);

                    html += `<option value="${ss.id}" ${state.sessionId == ss.id ? "selected" : ""}>
                        ${livePrefix}${escapeHtml(streamerName)} · ${timeStr} (${countStr} Nachrichten)
                    </option>`;
                });
                elements.selectSession.innerHTML = html;
            }
        } catch (e) {
            console.error("Fehler loadSessions:", e);
        }
    }

    async function loadAnalysis() {
        if (state.isFetchingAnalysis) return;
        state.isFetchingAnalysis = true;

        try {
            let url = `/api/chat-intelligence/analysis?period=${encodeURIComponent(state.period)}&min_word_len=${state.minWordLen}`;
            if (state.sessionId) {
                url += `&session_id=${encodeURIComponent(state.sessionId)}`;
            } else if (state.streamerId) {
                url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
            }

            const res = await fetch(url);
            if (!res.ok) return;
            const json = await res.json();
            const d = json.data || {};

            renderKPIs(d);
            renderWordCloud(d.words || []);
            renderPhrases(d.phrases || []);
            renderEmojis(d.emojis || []);
        } catch (e) {
            console.error("Fehler loadAnalysis:", e);
        } finally {
            state.isFetchingAnalysis = false;
        }
    }

    function renderKPIs(d) {
        const total = d.total_messages || 0;
        const unique = d.unique_chatters || 0;
        const whales = d.whale_messages || 0;
        const diversity = d.chatter_diversity_pct || 0;
        const avgChars = d.avg_chars_per_msg || 0;

        if (elements.kpiTotalMsgs) elements.kpiTotalMsgs.textContent = formatNumber(total);
        if (elements.kpiAvgChars) elements.kpiAvgChars.textContent = `Ø ${avgChars} Zeichen / Nachricht`;

        if (elements.kpiUniqueChatters) elements.kpiUniqueChatters.textContent = formatNumber(unique);
        if (elements.kpiDiversity) elements.kpiDiversity.textContent = `Chatter-Quote: ${diversity} %`;

        if (elements.kpiWhaleMsgs) elements.kpiWhaleMsgs.textContent = formatNumber(whales);
        const whalePct = total > 0 ? ((whales / total) * 100).toFixed(1) : 0;
        if (elements.kpiWhaleShare) elements.kpiWhaleShare.textContent = `${whalePct} % aller Nachrichten`;

        const top = (d.top_chatters && d.top_chatters.length > 0) ? d.top_chatters[0] : null;
        if (top) {
            if (elements.kpiTopChatter) {
                elements.kpiTopChatter.textContent = top.nickname || `@${top.username}`;
                elements.kpiTopChatter.title = `@${top.username}`;
            }
            if (elements.kpiTopChatterCount) {
                elements.kpiTopChatterCount.textContent = `${formatNumber(top.count)} Nachrichten (${top.pct}%)`;
            }
        } else {
            if (elements.kpiTopChatter) elements.kpiTopChatter.textContent = "-";
            if (elements.kpiTopChatterCount) elements.kpiTopChatterCount.textContent = "Keine Daten";
        }
    }

    function renderWordCloud(words) {
        if (!elements.wordCloudContainer) return;
        if (!words || words.length === 0) {
            elements.wordCloudContainer.innerHTML = `
                <div style="color:var(--text-muted); font-size:13px; text-align:center; padding:30px;">
                    Keine Chatnachrichten im gewählten Zeitraum gefunden.
                </div>
            `;
            if (elements.wordCloudCountBadge) elements.wordCloudCountBadge.textContent = "0 Wörter";
            return;
        }

        if (elements.wordCloudCountBadge) {
            elements.wordCloudCountBadge.textContent = `${words.length} Wörter`;
        }

        // Shuffle words slightly so highest aren't all at the very start
        const sorted = [...words];
        // Distribute: top weights get classes
        let html = "";
        sorted.forEach(w => {
            let wClass = "w-base";
            if (w.weight >= 70) wClass = "w-top";
            else if (w.weight >= 45) wClass = "w-high";
            else if (w.weight >= 25) wClass = "w-med";
            else if (w.weight >= 12) wClass = "w-low";

            const isActive = state.activeFilterWord === w.text ? "active-filter" : "";

            html += `
                <span class="cloud-word ${wClass} ${isActive}" data-word="${escapeHtml(w.text)}" title="${formatNumber(w.count)}x geschrieben">
                    <span>${escapeHtml(w.text)}</span>
                    <span class="cloud-word-count">${formatNumber(w.count)}</span>
                </span>
            `;
        });

        elements.wordCloudContainer.innerHTML = html;

        // Add Click listener
        elements.wordCloudContainer.querySelectorAll(".cloud-word").forEach(el => {
            el.addEventListener("click", () => {
                const word = el.getAttribute("data-word");
                if (state.activeFilterWord === word) {
                    clearWordFilter();
                } else {
                    setWordFilter(word);
                }
            });
        });
    }

    function renderPhrases(phrases) {
        if (!elements.phrasesListContainer) return;
        if (!phrases || phrases.length === 0) {
            elements.phrasesListContainer.innerHTML = `
                <div style="color:var(--text-muted); font-size:12.5px; padding:16px; text-align:center;">
                    Keine wiederkehrenden Phrasen erkannt.
                </div>
            `;
            return;
        }

        const maxCount = phrases[0] ? phrases[0].count : 1;
        let html = "";
        phrases.forEach((p, idx) => {
            const barWidth = Math.max(5, Math.round((p.count / maxCount) * 100));
            html += `
                <div class="phrase-item" data-phrase="${escapeHtml(p.phrase)}" title="Klicken zum Filtern nach '${escapeHtml(p.phrase)}'">
                    <span class="phrase-rank">#${idx + 1}</span>
                    <span class="phrase-text">${escapeHtml(p.phrase)}</span>
                    <div class="phrase-meta">
                        <span class="phrase-count-badge">${formatNumber(p.count)}x</span>
                        <span class="mono muted" style="font-size:10.5px;">${p.pct}%</span>
                    </div>
                    <div class="phrase-bar" style="width: ${barWidth}%;"></div>
                </div>
            `;
        });

        elements.phrasesListContainer.innerHTML = html;

        elements.phrasesListContainer.querySelectorAll(".phrase-item").forEach(el => {
            el.addEventListener("click", () => {
                const phrase = el.getAttribute("data-phrase");
                setWordFilter(phrase);
            });
        });
    }

    function renderEmojis(emojis) {
        if (!elements.emojisGridContainer) return;
        if (!emojis || emojis.length === 0) {
            elements.emojisGridContainer.innerHTML = `
                <div style="color:var(--text-muted); font-size:12.5px; padding:16px; grid-column:1/-1; text-align:center;">
                    Keine Emojis gefunden.
                </div>
            `;
            return;
        }

        let html = "";
        emojis.forEach(emo => {
            html += `
                <div class="emoji-tile" data-emoji="${escapeHtml(emo.emoji)}" title="${formatNumber(emo.count)}x verwendet">
                    <div class="emoji-char">${escapeHtml(emo.emoji)}</div>
                    <div class="emoji-count">${formatNumber(emo.count)}</div>
                </div>
            `;
        });

        elements.emojisGridContainer.innerHTML = html;

        elements.emojisGridContainer.querySelectorAll(".emoji-tile").forEach(el => {
            el.addEventListener("click", () => {
                const emo = el.getAttribute("data-emoji");
                setWordFilter(emo);
            });
        });
    }

    // 4. Log Viewer Messages Loader
    async function loadMessages(isAppend = false) {
        if (state.isFetchingMessages) return;
        state.isFetchingMessages = true;

        try {
            const effectiveQuery = state.activeFilterWord || state.searchTerm;
            let url = `/api/chat-logs?limit=80`;
            if (state.sessionId) {
                url += `&session_id=${encodeURIComponent(state.sessionId)}`;
            } else if (state.streamerId) {
                url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
            }

            if (effectiveQuery) {
                url += `&search=${encodeURIComponent(effectiveQuery)}`;
            }

            if (state.onlyWhales) {
                url += `&only_whales=true`;
            }

            const res = await fetch(url);
            if (!res.ok) return;
            const data = await res.json();
            const msgs = data.messages || [];

            // API delivers DESC order (newest first). For a natural chat stream, reverse to ASC
            state.messages = [...msgs].reverse();
            if (state.messages.length > 0) {
                state.oldestMsgId = state.messages[0].id;
                state.newestMsgId = state.messages[state.messages.length - 1].id;
            } else {
                state.oldestMsgId = null;
                state.newestMsgId = null;
            }

            renderChatMessages();

            if (elements.viewerMsgCountMeta) {
                elements.viewerMsgCountMeta.textContent = `${formatNumber(state.messages.length)} Nachrichten`;
            }

            if (state.isLiveTail) {
                scrollChatToBottom();
            }
        } catch (e) {
            console.error("Fehler loadMessages:", e);
        } finally {
            state.isFetchingMessages = false;
        }
    }

    async function loadOlderMessages() {
        if (!state.oldestMsgId || state.isFetchingMessages) return;
        state.isFetchingMessages = true;

        const scrollContainer = elements.chatStreamArea;
        const prevScrollHeight = scrollContainer ? scrollContainer.scrollHeight : 0;

        try {
            const effectiveQuery = state.activeFilterWord || state.searchTerm;
            let url = `/api/chat-logs?limit=80&before_id=${state.oldestMsgId}`;
            if (state.sessionId) {
                url += `&session_id=${encodeURIComponent(state.sessionId)}`;
            } else if (state.streamerId) {
                url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
            }
            if (effectiveQuery) url += `&search=${encodeURIComponent(effectiveQuery)}`;
            if (state.onlyWhales) url += `&only_whales=true`;

            const res = await fetch(url);
            if (!res.ok) return;
            const data = await res.json();
            const older = data.messages || [];

            if (older.length > 0) {
                const reversedOlder = [...older].reverse();
                state.messages = [...reversedOlder, ...state.messages];
                state.oldestMsgId = state.messages[0].id;
                renderChatMessages();

                // Restore scroll position
                if (scrollContainer) {
                    const newScrollHeight = scrollContainer.scrollHeight;
                    scrollContainer.scrollTop = newScrollHeight - prevScrollHeight;
                }
            } else {
                if (elements.btnLoadOlderMsgs) {
                    elements.btnLoadOlderMsgs.textContent = "Keine älteren Nachrichten mehr";
                    elements.btnLoadOlderMsgs.disabled = true;
                }
            }
        } catch (e) {
            console.error("Fehler loadOlderMessages:", e);
        } finally {
            state.isFetchingMessages = false;
        }
    }

    async function pollNewMessages() {
        if (!state.newestMsgId || !state.isLiveTail || state.isFetchingMessages) return;

        try {
            const effectiveQuery = state.activeFilterWord || state.searchTerm;
            let url = `/api/chat-logs?limit=40&after_id=${state.newestMsgId}`;
            if (state.sessionId) {
                url += `&session_id=${encodeURIComponent(state.sessionId)}`;
            } else if (state.streamerId) {
                url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
            }
            if (effectiveQuery) url += `&search=${encodeURIComponent(effectiveQuery)}`;
            if (state.onlyWhales) url += `&only_whales=true`;

            const res = await fetch(url);
            if (!res.ok) return;
            const data = await res.json();
            const newOnes = data.messages || [];

            if (newOnes.length > 0) {
                state.messages = [...state.messages, ...newOnes];
                state.newestMsgId = state.messages[state.messages.length - 1].id;
                renderChatMessages();

                if (elements.viewerMsgCountMeta) {
                    elements.viewerMsgCountMeta.textContent = `${formatNumber(state.messages.length)} Nachrichten`;
                }

                if (state.isLiveTail) {
                    scrollChatToBottom();
                }
            }
        } catch (e) {
            // Silently ignore polling failures
        }
    }

    function renderChatMessages() {
        if (!elements.chatStreamArea) return;
        if (!state.messages || state.messages.length === 0) {
            elements.chatStreamArea.innerHTML = `
                <div style="color:var(--text-muted); font-size:13px; text-align:center; margin-top:50px;">
                    Keine passenden Chat-Nachrichten gefunden.
                </div>
            `;
            return;
        }

        const effectiveQuery = state.activeFilterWord || state.searchTerm;
        let html = "";
        state.messages.forEach(m => {
            let whaleClass = "";
            let whalePill = "";
            if (m.whale_tier === "whale") {
                whaleClass = "whale-whale";
                whalePill = '<span class="ci-badge" style="background:#f59e0b; color:#000;">WHALE</span>';
            } else if (m.whale_tier === "shark") {
                whaleClass = "whale-shark";
                whalePill = '<span class="ci-badge" style="background:#38bdf8; color:#000;">SHARK</span>';
            } else if (m.whale_tier === "dolphin" || m.is_whale) {
                whaleClass = "whale-dolphin";
                whalePill = '<span class="ci-badge" style="background:#10b981; color:#000;">VIP</span>';
            }

            const avatar = m.avatar_url || "/pictures/bot_avatar.jpg";
            const timeStr = formatTime(m.created_at);
            const userDisplay = m.nickname || `@${m.username}`;
            const streamerTag = !state.streamerId ? `<span class="chat-streamer-tag">@${escapeHtml(m.streamer_username)}</span>` : "";
            const commentHighlighted = highlightText(m.comment, effectiveQuery);

            html += `
                <div class="chat-row ${whaleClass}">
                    <img src="${escapeHtml(avatar)}" class="chat-avatar" onerror="this.src='/pictures/bot_avatar.jpg'" />
                    <div class="chat-body">
                        <div class="chat-meta-line">
                            ${whalePill}
                            <span class="chat-username">${escapeHtml(userDisplay)}</span>
                            <span class="mono muted" style="font-size:10.5px;">@${escapeHtml(m.username)}</span>
                            ${streamerTag}
                            <span class="chat-time">${escapeHtml(timeStr)}</span>
                        </div>
                        <div class="chat-text-line">${commentHighlighted}</div>
                    </div>
                </div>
            `;
        });

        elements.chatStreamArea.innerHTML = html;
    }

    function scrollChatToBottom() {
        if (elements.chatStreamArea) {
            elements.chatStreamArea.scrollTop = elements.chatStreamArea.scrollHeight;
        }
    }

    function startPolling() {
        clearInterval(state.pollTimer);
        state.pollTimer = setInterval(() => {
            pollNewMessages();
        }, 3000);
    }

    // 5. Export Download Trigger
    function triggerExportDownload(format) {
        const effectiveQuery = state.activeFilterWord || state.searchTerm;
        let url = `/api/chat-intelligence/export?format=${encodeURIComponent(format)}`;
        if (state.sessionId) {
            url += `&session_id=${encodeURIComponent(state.sessionId)}`;
        } else if (state.streamerId) {
            url += `&streamer_id=${encodeURIComponent(state.streamerId)}`;
        }
        if (effectiveQuery) {
            url += `&search=${encodeURIComponent(effectiveQuery)}`;
        }
        if (state.onlyWhales) {
            url += `&only_whales=true`;
        }

        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    // Run on DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
