<template>
  <div class="toktracker-ci-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <div class="brand-block">
          <div class="brand-logo-wrap">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" onerror="this.src='/static/avatar_default.png'" />
            <span class="brand-ci-indicator"></span>
          </div>
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-badge-ci">CHAT-INTELLIGENCE</span>
            </div>
            <span class="brand-subtitle">Echtzeit-Sentiment, Wortwolken &amp; Chatter-Intelligence</span>
          </div>
        </div>

        <nav class="nav-links">
          <a href="/admin" class="nav-pill">
            <span class="icon">📊</span> Admin-Panel
          </a>
          <a href="/donor-radar" class="nav-pill">
            <span class="icon">🎯</span> Spender-Radar
          </a>
          <a href="/public" target="_blank" class="nav-pill">
            <span class="icon">🌐</span> Public Radar ↗
          </a>
          <a href="/miniapp" target="_blank" class="nav-pill">
            <span class="icon">📱</span> Mini-App
          </a>
          <button type="button" class="btn-theme-toggle" @click="toggleTheme">
            {{ currentTheme === 'dark' ? '🌙 Dark' : '☀️ Light' }}
          </button>
        </nav>
      </div>
    </header>

    <!-- Main Body -->
    <main class="app-body">
      <!-- Controls Toolbar -->
      <section class="toolbar-box modern-card">
        <div class="toolbar-top">
          <!-- Session Selector -->
          <div class="control-item flex-grow">
            <label for="ciSessionSelect" class="control-label">Stream-Session auswählen:</label>
            <select
              id="ciSessionSelect"
              v-model="selectedSessionId"
              @change="onSessionChange"
              class="modern-select full-width"
            >
              <option value="">Alle Streams des Zeitraums</option>
              <option v-for="ss in sessionsList" :key="ss.id" :value="ss.id">
                {{ ss.status === 'active' ? '🔴 LIVE: ' : '' }}@{{ ss.streamer_username }} · {{ formatTime(ss.started_at) }} ({{ formatNumber(ss.chat_count) }} Nachrichten)
              </option>
            </select>
          </div>

          <!-- Streamer Filter (if not session specific) -->
          <div class="control-item" v-if="!selectedSessionId">
            <label for="ciStreamerSelect" class="control-label">Streamer:</label>
            <select
              id="ciStreamerSelect"
              v-model="selectedStreamerId"
              @change="loadAnalysis"
              class="modern-select"
            >
              <option value="">Alle Streamer</option>
              <option v-for="s in streamerOptions" :key="s.id" :value="s.id">
                @{{ s.username }}
              </option>
            </select>
          </div>

          <!-- Period Buttons -->
          <div class="control-item" v-if="!selectedSessionId">
            <label class="control-label">Zeitraum:</label>
            <div class="period-pills">
              <button
                v-for="p in ['today', '24h', '7d', '30d', 'all']"
                :key="p"
                type="button"
                :class="['period-btn', { active: period === p }]"
                @click="setPeriod(p)"
              >
                {{ p.toUpperCase() }}
              </button>
            </div>
          </div>
        </div>

        <div class="toolbar-bottom">
          <div class="min-word-control">
            <span class="sub-label">Min. Wortlänge:</span>
            <div class="pill-group">
              <button
                v-for="len in [3, 4, 5]"
                :key="len"
                type="button"
                :class="['pill-btn', { active: minWordLen === len }]"
                @click="setMinWordLen(len)"
              >
                {{ len }}+ Zeichen
              </button>
            </div>
          </div>

          <div class="toolbar-actions">
            <button
              type="button"
              class="btn-refresh"
              @click="refreshAll"
              :disabled="isLoading"
            >
              <span :class="['refresh-icon', { spinning: isLoading }]">🔄</span>
              <span>{{ isLoading ? 'Analysiere...' : 'Neu analysieren' }}</span>
            </button>
          </div>
        </div>
      </section>

      <!-- KPI Grid -->
      <section class="ci-kpi-grid">
        <div class="kpi-card card-messages">
          <div class="kpi-top">
            <span class="kpi-icon">💬</span>
            <span class="kpi-label">Erfasste Nachrichten</span>
          </div>
          <div class="kpi-value text-purple">{{ formatNumber(kpis.total_messages) }}</div>
          <div class="kpi-sub">Im gewählten Stream-Zeitraum</div>
        </div>

        <div class="kpi-card card-chatters">
          <div class="kpi-top">
            <span class="kpi-icon">👥</span>
            <span class="kpi-label">Aktive Chatter</span>
          </div>
          <div class="kpi-value text-cyan">{{ formatNumber(kpis.unique_chatters) }}</div>
          <div class="kpi-sub">Einzigartige Teilnehmer</div>
        </div>

        <div class="kpi-card card-whales">
          <div class="kpi-top">
            <span class="kpi-icon">🐋</span>
            <span class="kpi-label">Whale-Nachrichten</span>
          </div>
          <div class="kpi-value text-gold">{{ formatNumber(kpis.whale_messages) }}</div>
          <div class="kpi-sub">Von Top-Spendern verfasst</div>
        </div>

        <div class="kpi-card card-diversity">
          <div class="kpi-top">
            <span class="kpi-icon">📊</span>
            <span class="kpi-label">Chat-Diversität</span>
          </div>
          <div class="kpi-value text-emerald">{{ (kpis.chatter_diversity_pct || 0).toFixed(1) }}%</div>
          <div class="kpi-sub">&Oslash; {{ (kpis.avg_chars_per_msg || 0).toFixed(1) }} Zeichen / Nachricht</div>
        </div>
      </section>

      <!-- Navigation Tabs -->
      <div class="tab-list-row">
        <div class="tab-pills">
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'wordcloud' }]"
            @click="activeTab = 'wordcloud'"
          >
            ☁️ Interaktive Wortwolke
          </button>
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'phrases' }]"
            @click="activeTab = 'phrases'"
          >
            💬 Phrasen &amp; Emojis
          </button>
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'chatters' }]"
            @click="activeTab = 'chatters'"
          >
            👑 Top-Chatter
            <span class="badge-mini" v-if="topChatters.length > 0">{{ topChatters.length }}</span>
          </button>
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'logs' }]"
            @click="activeTab = 'logs'; loadChatLogs()"
          >
            📜 Live Chat-Log &amp; Suche
          </button>
        </div>
      </div>

      <!-- TAB 1: Wortwolke & Keywords -->
      <div v-show="activeTab === 'wordcloud'" class="tab-content">
        <div class="wordcloud-grid">
          <!-- Interactive Cloud -->
          <div class="modern-card wordcloud-card">
            <div class="card-header-bar">
              <h4>Häufigste Keywords im Chat</h4>
              <span class="sub-hint">Klicke auf ein Wort, um relevante Nachrichten zu filtern</span>
            </div>

            <div class="wordcloud-box" v-if="wordsList.length > 0">
              <span
                v-for="w in wordsList"
                :key="w.word"
                :class="['cloud-word', getWordClass(w.weight)]"
                :style="{ fontSize: getWordFontSize(w.weight) }"
                @click="filterChatByWord(w.word)"
                :title="`${w.count}x im Chat erwähnt`"
              >
                {{ w.word }}
                <span class="word-count-badge">{{ w.count }}</span>
              </span>
            </div>
            <div v-else class="empty-state">
              Keine ausreichenden Chatnachrichten für eine Wortwolke im gewählten Zeitraum.
            </div>
          </div>

          <!-- Top Keywords List -->
          <div class="modern-card keywords-rank-card">
            <div class="card-header-bar">
              <h4>Top Begriffe</h4>
              <span class="count-pill">{{ wordsList.length }} Wörter</span>
            </div>

            <div class="keywords-list">
              <div
                v-for="(w, idx) in wordsList.slice(0, 30)"
                :key="w.word"
                class="keyword-row"
                @click="filterChatByWord(w.word)"
              >
                <div class="keyword-left">
                  <span class="rank-index">#{{ idx + 1 }}</span>
                  <strong class="keyword-text">{{ w.word }}</strong>
                </div>
                <div class="keyword-right">
                  <div class="bar-wrap">
                    <div class="bar-fill" :style="{ width: getKeywordBarWidth(w.count) }"></div>
                  </div>
                  <span class="keyword-count">{{ formatNumber(w.count) }}x</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 2: Phrasen & Emojis -->
      <div v-show="activeTab === 'phrases'" class="tab-content">
        <div class="phrases-grid">
          <!-- Recurring Phrases -->
          <div class="modern-card phrases-card">
            <div class="card-header-bar">
              <h4>Häufige Phrasen &amp; N-Gramme</h4>
              <span class="sub-hint">Wiederkehrende 2- bis 3-Wort-Kombinationen</span>
            </div>

            <div class="phrases-list" v-if="phrasesList.length > 0">
              <div
                v-for="(ph, idx) in phrasesList"
                :key="ph.phrase"
                class="phrase-row"
                @click="filterChatByWord(ph.phrase)"
              >
                <span class="phrase-idx">#{{ idx + 1 }}</span>
                <span class="phrase-text">"{{ ph.phrase }}"</span>
                <span class="phrase-count font-bold text-cyan">{{ formatNumber(ph.count) }}x</span>
              </div>
            </div>
            <div v-else class="empty-state">
              Keine wiederkehrenden Phrasen gefunden.
            </div>
          </div>

          <!-- Top Emojis -->
          <div class="modern-card emojis-card">
            <div class="card-header-bar">
              <h4>Top Chat Emojis</h4>
              <span class="count-pill">{{ emojisList.length }} Emojis</span>
            </div>

            <div class="emojis-grid" v-if="emojisList.length > 0">
              <div
                v-for="em in emojisList"
                :key="em.emoji"
                class="emoji-item"
              >
                <span class="emoji-symbol">{{ em.emoji }}</span>
                <span class="emoji-count">{{ formatNumber(em.count) }}</span>
              </div>
            </div>
            <div v-else class="empty-state">
              Keine Emojis im ausgewählten Zeitraum erfasst.
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 3: Top-Chatter -->
      <div v-show="activeTab === 'chatters'" class="tab-content">
        <div class="modern-card table-card">
          <div class="card-header-bar">
            <h4>Aktivste Chat-Teilnehmer</h4>
            <span class="count-pill">{{ topChatters.length }} Chatter</span>
          </div>

          <div class="table-responsive">
            <table class="modern-table">
              <thead>
                <tr>
                  <th class="rank-col">RANG</th>
                  <th>CHATTER</th>
                  <th>STATUS</th>
                  <th class="num-col">GESENDETE NACHRICHTEN</th>
                  <th>AKTION</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="topChatters.length === 0">
                  <td colspan="5" class="empty-cell">
                    Keine aktiven Chatter für die Auswahl gefunden.
                  </td>
                </tr>

                <tr
                  v-for="(chatter, idx) in topChatters"
                  :key="chatter.username"
                  class="chatter-row"
                >
                  <td class="rank-col">
                    <span :class="['rank-pill', getRankClass(idx + 1)]">
                      #{{ idx + 1 }}
                    </span>
                  </td>
                  <td>
                    <div class="chatter-profile">
                      <img
                        :src="chatter.avatar_url || '/static/avatar_default.png'"
                        class="chatter-avatar"
                        alt="Avatar"
                        onerror="this.src='/static/avatar_default.png'"
                      />
                      <div class="chatter-names">
                        <strong class="chatter-username">@{{ chatter.username }}</strong>
                        <span class="chatter-nickname" v-if="chatter.nickname">
                          {{ chatter.nickname }}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span v-if="chatter.is_whale" class="whale-tag">
                      🐋 {{ chatter.whale_tier?.toUpperCase() || 'WHALE' }}
                    </span>
                    <span v-else class="regular-tag">Chatter</span>
                  </td>
                  <td class="num-col font-bold text-cyan">
                    {{ formatNumber(chatter.count) }} Nachrichten
                  </td>
                  <td>
                    <a
                      :href="`/donor-radar?search=${encodeURIComponent(chatter.username)}`"
                      class="btn-radar-link"
                    >
                      Im Radar öffnen ↗
                    </a>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 4: Live Chat-Log & Suche -->
      <div v-show="activeTab === 'logs'" class="tab-content">
        <div class="modern-card chat-log-card">
          <div class="log-toolbar">
            <div class="log-search-wrap">
              <span class="search-icon">🔍</span>
              <input
                v-model="logSearchQuery"
                type="search"
                placeholder="Chat-Nachrichten durchsuchen..."
                class="modern-input-search"
                @input="debouncedLogSearch"
              />
            </div>

            <div class="log-actions">
              <a
                :href="`/api/chat-intelligence/export?session_id=${selectedSessionId || ''}&streamer_id=${selectedStreamerId || ''}&search=${encodeURIComponent(logSearchQuery)}`"
                target="_blank"
                class="btn-export"
              >
                📥 Als CSV exportieren
              </a>
              <button
                type="button"
                class="btn-primary sm"
                @click="loadChatLogs"
              >
                Aktualisieren
              </button>
            </div>
          </div>

          <div class="log-table-wrap">
            <table class="modern-table">
              <thead>
                <tr>
                  <th>ZEIT</th>
                  <th>STREAMER</th>
                  <th>SENDER</th>
                  <th>NACHRICHT / EVENT</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="chatLogsList.length === 0">
                  <td colspan="4" class="empty-cell">
                    Keine Nachrichten für den Suchfilter gefunden.
                  </td>
                </tr>

                <tr
                  v-for="msg in chatLogsList"
                  :key="msg.id"
                  :class="{ 'highlight-whale': msg.is_whale }"
                >
                  <td class="time-col">{{ formatTimeOnly(msg.created_at) }}</td>
                  <td>
                    <span class="streamer-badge">@{{ msg.streamer_username }}</span>
                  </td>
                  <td>
                    <div class="sender-wrap">
                      <strong>@{{ msg.sender_username }}</strong>
                      <span v-if="msg.is_whale" class="whale-dot" title="Whale">🐋</span>
                    </div>
                  </td>
                  <td class="msg-content-col">
                    <span v-if="msg.is_gift" class="gift-highlight">
                      🎁 {{ msg.gift_name }} (+{{ formatNumber(msg.total_coins) }} 💎)
                    </span>
                    <span v-else class="msg-text">{{ msg.message }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { formatNumber } from "./utils/formatters";

// State
const period = ref("all");
const selectedSessionId = ref<string | number>("");
const selectedStreamerId = ref<string | number>("");
const minWordLen = ref(3);
const activeTab = ref<"wordcloud" | "phrases" | "chatters" | "logs">("wordcloud");
const isLoading = ref(false);
const currentTheme = ref("dark");

// KPI & Analysis Data
const kpis = ref({
  total_messages: 0,
  unique_chatters: 0,
  whale_messages: 0,
  avg_chars_per_msg: 0,
  chatter_diversity_pct: 0,
});

const wordsList = ref<any[]>([]);
const phrasesList = ref<any[]>([]);
const emojisList = ref<any[]>([]);
const topChatters = ref<any[]>([]);
const sessionsList = ref<any[]>([]);
const streamerOptions = ref<any[]>([]);

// Chat Logs
const chatLogsList = ref<any[]>([]);
const logSearchQuery = ref("");

function setPeriod(p: string) {
  period.value = p;
  loadAnalysis();
}

function setMinWordLen(len: number) {
  minWordLen.value = len;
  loadAnalysis();
}

function onSessionChange() {
  loadAnalysis();
}

function formatTime(str?: string) {
  if (!str) return "-";
  try {
    const d = new Date(str);
    return d.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return str;
  }
}

function formatTimeOnly(str?: string) {
  if (!str) return "";
  try {
    const d = new Date(str);
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function getRankClass(rank: number) {
  if (rank === 1) return "rank-top-1";
  if (rank === 2) return "rank-top-2";
  if (rank === 3) return "rank-top-3";
  return "";
}

function getWordClass(weight: number) {
  if (weight >= 0.75) return "word-huge";
  if (weight >= 0.5) return "word-large";
  if (weight >= 0.25) return "word-medium";
  return "word-small";
}

function getWordFontSize(weight: number) {
  const min = 13;
  const max = 34;
  const size = Math.round(min + (max - min) * (weight || 0.1));
  return `${size}px`;
}

function getKeywordBarWidth(count: number) {
  const max = wordsList.value[0]?.count || 1;
  const pct = Math.min(100, Math.round((count / max) * 100));
  return `${pct}%`;
}

function filterChatByWord(word: string) {
  activeTab.value = "logs";
  logSearchQuery.value = word;
  loadChatLogs();
}

async function loadSessions() {
  try {
    const res = await fetch("/api/chat-intelligence/sessions?limit=80");
    if (res.ok) {
      const json = await res.json();
      sessionsList.value = json.sessions || [];
    }
  } catch (err) {
    console.error("Fehler beim Laden der Sessions:", err);
  }
}

async function loadAnalysis() {
  isLoading.value = true;
  try {
    const params = new URLSearchParams({
      period: period.value,
      min_word_len: String(minWordLen.value),
    });
    if (selectedSessionId.value) {
      params.append("session_id", String(selectedSessionId.value));
    } else if (selectedStreamerId.value) {
      params.append("streamer_id", String(selectedStreamerId.value));
    }

    const res = await fetch(`/api/chat-intelligence/analysis?${params.toString()}`);
    if (res.ok) {
      const json = await res.json();
      const d = json.data || {};

      kpis.value = {
        total_messages: d.total_messages || 0,
        unique_chatters: d.unique_chatters || 0,
        whale_messages: d.whale_messages || 0,
        avg_chars_per_msg: d.avg_chars_per_msg || 0,
        chatter_diversity_pct: d.chatter_diversity_pct || 0,
      };

      wordsList.value = d.words || [];
      phrasesList.value = d.phrases || [];
      emojisList.value = d.emojis || [];
      topChatters.value = d.top_chatters || [];
    }
  } catch (err) {
    console.error("Fehler bei der Analyse:", err);
  } finally {
    isLoading.value = false;
  }
}

async function loadChatLogs() {
  try {
    const params = new URLSearchParams({ limit: "60" });
    if (selectedSessionId.value) params.append("session_id", String(selectedSessionId.value));
    if (selectedStreamerId.value) params.append("streamer_id", String(selectedStreamerId.value));
    if (logSearchQuery.value.trim()) params.append("search", logSearchQuery.value.trim());

    const res = await fetch(`/api/chat-logs?${params.toString()}`);
    if (res.ok) {
      const json = await res.json();
      chatLogsList.value = json.logs || [];
    }
  } catch (err) {
    console.error("Fehler chat logs:", err);
  }
}

let searchTimer: any = null;
function debouncedLogSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    loadChatLogs();
  }, 350);
}

function refreshAll() {
  loadSessions();
  loadAnalysis();
  if (activeTab.value === "logs") {
    loadChatLogs();
  }
}

function toggleTheme() {
  const next = currentTheme.value === "light" ? "dark" : "light";
  currentTheme.value = next;
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("toktracker_theme", next);
  } catch {}
}

onMounted(() => {
  try {
    currentTheme.value = localStorage.getItem("toktracker_theme") || "dark";
    document.documentElement.setAttribute("data-theme", currentTheme.value);
  } catch {}

  loadSessions();
  loadAnalysis();
});
</script>

<style scoped>
.toktracker-ci-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-body, #090d16);
  color: var(--text-main, #f1f5f9);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Header */
.app-header {
  background: rgba(15, 21, 35, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 12px 24px;
}

.header-inner {
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-logo-wrap {
  position: relative;
}

.brand-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  object-fit: cover;
}

.brand-ci-indicator {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 8px #38bdf8;
}

.brand-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: #ffffff;
  margin: 0;
}

.brand-badge-ci {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.8px;
  padding: 2px 7px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.3), rgba(37, 99, 235, 0.4));
  border: 1px solid rgba(56, 189, 248, 0.5);
  color: #7dd3fc;
}

.brand-subtitle {
  font-size: 11.5px;
  color: #94a3b8;
  display: block;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s ease;
}

.nav-pill:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

.btn-theme-toggle {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

/* App Body */
.app-body {
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 24px 60px;
  flex: 1;
}

/* Modern Card */
.modern-card {
  background: rgba(15, 21, 35, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  backdrop-filter: blur(14px);
  overflow: hidden;
}

/* Toolbar Box */
.toolbar-box {
  padding: 16px 20px;
  margin-bottom: 24px;
}

.toolbar-top {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.control-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.flex-grow {
  flex: 1;
  min-width: 280px;
}

.control-label {
  font-size: 11.5px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.4px;
}

.modern-select {
  padding: 9px 14px;
  background: rgba(10, 15, 28, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #f1f5f9;
  font-size: 13px;
  font-weight: 600;
  outline: none;
}

.full-width {
  width: 100%;
}

.period-pills {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 2px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.period-btn {
  padding: 6px 12px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
}

.period-btn.active {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
}

.toolbar-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 14px;
  flex-wrap: wrap;
  gap: 12px;
}

.min-word-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sub-label {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
}

.pill-group {
  display: flex;
  gap: 6px;
}

.pill-btn {
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
}

.pill-btn.active {
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.4);
  color: #7dd3fc;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #ffffff;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* KPI Grid */
.ci-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 900px) {
  .ci-kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 540px) {
  .ci-kpi-grid {
    grid-template-columns: 1fr;
  }
}

.kpi-card {
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 18px;
  backdrop-filter: blur(12px);
}

.kpi-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.kpi-icon {
  font-size: 16px;
}

.kpi-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #94a3b8;
}

.kpi-value {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 26px;
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 4px;
}

.kpi-sub {
  font-size: 11.5px;
  color: #64748b;
}

.text-purple { color: #c084fc; }
.text-cyan { color: #38bdf8; }
.text-gold { color: #f59e0b; }
.text-emerald { color: #34d399; }

/* Tabs */
.tab-list-row {
  margin-bottom: 20px;
}

.tab-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tab-pill {
  padding: 9px 18px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.tab-pill.active {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.25), rgba(37, 99, 235, 0.2));
  border-color: rgba(56, 189, 248, 0.5);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(56, 189, 248, 0.2);
}

.badge-mini {
  background: #38bdf8;
  color: #090d16;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 10px;
}

/* Word Cloud */
.wordcloud-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

@media (max-width: 960px) {
  .wordcloud-grid {
    grid-template-columns: 1fr;
  }
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.card-header-bar h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: #ffffff;
}

.sub-hint {
  font-size: 11px;
  color: #94a3b8;
}

.count-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
}

.wordcloud-box {
  padding: 28px;
  min-height: 380px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 16px;
  line-height: 1.4;
}

.cloud-word {
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 8px;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  user-select: none;
}

.cloud-word:hover {
  transform: scale(1.1);
  background: rgba(255, 255, 255, 0.1);
}

.word-huge {
  font-weight: 800;
  color: #c084fc;
  text-shadow: 0 0 16px rgba(192, 132, 252, 0.4);
}

.word-large {
  font-weight: 800;
  color: #38bdf8;
  text-shadow: 0 0 12px rgba(56, 189, 248, 0.3);
}

.word-medium {
  font-weight: 700;
  color: #34d399;
}

.word-small {
  font-weight: 600;
  color: #cbd5e1;
}

.word-count-badge {
  font-size: 10px;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.15);
  padding: 1px 5px;
  border-radius: 4px;
}

.keywords-list {
  padding: 12px;
  max-height: 480px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.keyword-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.15s ease;
}

.keyword-row:hover {
  background: rgba(56, 189, 248, 0.1);
}

.keyword-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rank-index {
  font-size: 11px;
  color: #64748b;
  width: 24px;
}

.keyword-text {
  font-size: 13px;
  color: #ffffff;
}

.keyword-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bar-wrap {
  width: 60px;
  height: 5px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: #38bdf8;
  border-radius: 3px;
}

.keyword-count {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  min-width: 35px;
  text-align: right;
}

/* Phrases & Emojis */
.phrases-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

@media (max-width: 960px) {
  .phrases-grid {
    grid-template-columns: 1fr;
  }
}

.phrases-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.phrase-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.15s ease;
}

.phrase-row:hover {
  background: rgba(255, 255, 255, 0.08);
}

.phrase-idx {
  font-size: 11px;
  color: #64748b;
  width: 24px;
}

.phrase-text {
  flex: 1;
  font-size: 13px;
  color: #ffffff;
  font-style: italic;
}

.emojis-grid {
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.emoji-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
}

.emoji-symbol {
  font-size: 26px;
}

.emoji-count {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
}

/* Table Card */
.table-responsive {
  overflow-x: auto;
}

.modern-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.modern-table th {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}

.modern-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.chatter-profile {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chatter-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.chatter-names {
  display: flex;
  flex-direction: column;
}

.chatter-username {
  font-size: 13.5px;
  color: #ffffff;
}

.chatter-nickname {
  font-size: 11.5px;
  color: #94a3b8;
}

.whale-tag {
  font-size: 11px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(168, 85, 247, 0.2);
  border: 1px solid rgba(168, 85, 247, 0.4);
  color: #d8b4fe;
}

.regular-tag {
  font-size: 11px;
  color: #94a3b8;
}

.btn-radar-link {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #38bdf8;
  font-size: 11.5px;
  font-weight: 600;
  text-decoration: none;
}

.btn-radar-link:hover {
  background: rgba(56, 189, 248, 0.15);
}

/* Chat Logs Tab */
.log-toolbar {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.log-search-wrap {
  position: relative;
  min-width: 280px;
}

.search-icon {
  position: absolute;
  left: 14px;
  top: 10px;
  font-size: 14px;
  opacity: 0.6;
}

.modern-input-search {
  width: 100%;
  padding: 9px 14px 9px 38px;
  background: rgba(10, 15, 28, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #ffffff;
  font-size: 13px;
  outline: none;
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn-export {
  padding: 8px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.btn-export:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.btn-primary.sm {
  background: linear-gradient(135deg, #0284c7, #38bdf8);
  border: none;
  border-radius: 8px;
  color: #ffffff;
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.log-table-wrap {
  max-height: 520px;
  overflow-y: auto;
}

.time-col {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
}

.streamer-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: #94a3b8;
  font-size: 11.5px;
}

.sender-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.whale-dot {
  font-size: 12px;
}

.gift-highlight {
  font-weight: 700;
  color: #38bdf8;
}

.msg-text {
  color: #cbd5e1;
}

.highlight-whale {
  background: rgba(168, 85, 247, 0.05);
}

.empty-state {
  text-align: center;
  padding: 48px 16px;
  color: #94a3b8;
  font-size: 13px;
}

.rank-col {
  text-align: center;
  width: 50px;
}

.rank-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 24px;
  padding: 0 6px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 700;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.06);
}

.rank-top-1 {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.35), rgba(217, 119, 6, 0.5));
  border: 1px solid rgba(245, 158, 11, 0.6);
  color: #fbbf24;
}

.rank-top-2 {
  background: linear-gradient(135deg, rgba(148, 163, 184, 0.3), rgba(100, 116, 139, 0.45));
  border: 1px solid rgba(148, 163, 184, 0.5);
  color: #f1f5f9;
}

.rank-top-3 {
  background: linear-gradient(135deg, rgba(180, 83, 9, 0.3), rgba(120, 53, 15, 0.45));
  border: 1px solid rgba(180, 83, 9, 0.5);
  color: #f97316;
}

.num-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty-cell {
  text-align: center;
  padding: 36px 16px;
  color: #94a3b8;
}
</style>
