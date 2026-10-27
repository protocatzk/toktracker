<template>
  <div class="ma-app-wrapper">
    <!-- Header -->
    <header class="ma-header">
      <div class="ma-brand">
        <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="ma-brand-logo" onerror="this.src='/static/avatar_default.png'" />
        <div>
          <div class="ma-brand-title">
            toktracker <span class="ma-badge">Mini-App</span>
            <span v-if="isAdmin" class="ma-admin-indicator">👑 ADMIN</span>
          </div>
          <div class="ma-brand-sub">{{ totals.live_count }} LIVE · {{ totals.streamer_count }} ÜBERWACHT</div>
        </div>
      </div>

      <div class="ma-header-actions">
        <button
          type="button"
          class="btn-icon-refresh"
          @click="loadData"
          :disabled="isLoading"
          title="Aktualisieren"
        >
          <span :class="['refresh-icon', { spinning: isLoading }]">🔄</span>
        </button>
      </div>
    </header>

    <!-- Period Pills -->
    <div class="ma-period-selector">
      <button
        v-for="p in ['today', '24h', '7d', '30d', 'all']"
        :key="p"
        type="button"
        :class="['period-pill', { active: period === p }]"
        @click="setPeriod(p)"
      >
        {{ getPeriodLabel(p) }}
      </button>
    </div>

    <!-- Live Status Pulse Banner -->
    <div class="ma-live-banner" :class="totals.live_count > 0 ? 'has-active' : 'no-active'">
      <div class="live-pulse-dot" v-if="totals.live_count > 0"></div>
      <span>{{ totals.live_count > 0 ? `Echtzeit-Tracking aktiv · ${totals.live_count} Streamer LIVE` : 'Bereit · Aktuell keine Streamer online' }}</span>
    </div>

    <!-- Compact KPI Grid -->
    <div class="ma-kpi-grid">
      <div class="ma-kpi-card full-width">
        <div>
          <div class="kpi-label">💰 Netto Creator-Auszahlung</div>
          <div class="kpi-value highlight">{{ formatEUR(totals.eur_net) }}</div>
        </div>
        <div class="kpi-right">
          <div class="kpi-sub">{{ formatUSD(totals.usd_net) }}</div>
          <div class="kpi-quote">~50% Netto-Quote</div>
        </div>
      </div>

      <div class="ma-kpi-card">
        <div class="kpi-label">💎 Erfasste Coins</div>
        <div class="kpi-value text-cyan">{{ formatNumber(totals.total_coins) }}</div>
        <div class="kpi-sub">Diamonds gesamt</div>
      </div>

      <div class="ma-kpi-card">
        <div class="kpi-label">🎁 Geschenke</div>
        <div class="kpi-value text-purple">{{ formatNumber(totals.gift_events_count) }}</div>
        <div class="kpi-sub">Live Gift-Events</div>
      </div>
    </div>

    <!-- Quick Action Hub Buttons -->
    <div class="ma-quick-actions">
      <a href="/donor-radar" class="quick-btn btn-radar">
        <span class="icon">🎯</span>
        <div class="btn-text">
          <strong>Spender-Radar</strong>
          <span>Whale &amp; Loyalty Hub</span>
        </div>
      </a>
      <a href="/chat-intelligence" class="quick-btn btn-ci">
        <span class="icon">💬</span>
        <div class="btn-text">
          <strong>Chat-Intelligence</strong>
          <span>Sentiment &amp; Wortwolke</span>
        </div>
      </a>
    </div>

    <!-- Navigation Tabs -->
    <div class="ma-tabs-bar">
      <button
        type="button"
        :class="['ma-tab-btn', { active: activeTab === 'streamers' }]"
        @click="activeTab = 'streamers'"
      >
        👥 Streamer <span class="tab-badge">{{ streamersList.length }}</span>
      </button>
      <button
        type="button"
        :class="['ma-tab-btn', { active: activeTab === 'gifts' }]"
        @click="activeTab = 'gifts'"
      >
        🎁 Geschenke
      </button>
      <button
        type="button"
        :class="['ma-tab-btn', { active: activeTab === 'info' }]"
        @click="activeTab = 'info'"
      >
        ℹ️ Info
      </button>
    </div>

    <!-- TAB 1: Streamer Leaderboard -->
    <div v-show="activeTab === 'streamers'" class="ma-tab-pane">
      <div class="search-wrap">
        <input
          v-model="searchQuery"
          type="search"
          placeholder="Streamer nach Namen filtern..."
          class="ma-search-input"
        />
      </div>

      <div class="streamer-list">
        <div v-if="filteredStreamers.length === 0" class="ma-empty">
          Keine Streamer gefunden.
        </div>

        <div
          v-for="(s, idx) in filteredStreamers"
          :key="s.id"
          class="ma-streamer-card"
          @click="selectedStreamerId = s.id"
        >
          <div class="card-left">
            <span :class="['ma-rank-pill', getRankClass(idx + 1)]">#{{ idx + 1 }}</span>
            <div class="avatar-wrap">
              <img
                :src="s.avatar_url || '/static/avatar_default.png'"
                class="ma-avatar"
                alt="Avatar"
                onerror="this.src='/static/avatar_default.png'"
              />
              <span v-if="s.is_live" class="live-dot-pulse-mini"></span>
            </div>
            <div class="streamer-info">
              <div class="streamer-name-row">
                <strong class="streamer-display">{{ s.display_name || s.username }}</strong>
                <span v-if="s.is_live" class="badge-live">LIVE</span>
              </div>
              <span class="streamer-handle">@{{ s.username }}</span>
            </div>
          </div>

          <div class="card-right">
            <span class="coins-val text-cyan">{{ formatNumber(s.total_coins) }} 💎</span>
            <span class="net-val">{{ formatEUR(s.eur_net) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: Geschenke Feed -->
    <div v-show="activeTab === 'gifts'" class="ma-tab-pane">
      <div class="gifts-list">
        <div v-if="recentGifts.length === 0" class="ma-empty">
          Keine kürzlichen Geschenke aufgezeichnet.
        </div>

        <div
          v-for="gift in recentGifts"
          :key="gift.id"
          class="ma-gift-item"
        >
          <div class="gift-left">
            <span class="gift-icon">🎁</span>
            <div class="gift-details">
              <strong>{{ gift.gift_name }} <span class="repeat-tag" v-if="gift.repeat_count > 1">x{{ gift.repeat_count }}</span></strong>
              <span class="gift-sub">von @{{ gift.sender_username }} an @{{ gift.streamer_username }}</span>
            </div>
          </div>
          <div class="gift-right">
            <strong class="gift-coins text-cyan">+{{ formatNumber(gift.total_diamonds || gift.total_coins) }} 💎</strong>
            <span class="gift-time">{{ formatTime(gift.timestamp || gift.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: Bot & App Info -->
    <div v-show="activeTab === 'info'" class="ma-tab-pane">
      <div class="info-card modern-card">
        <div class="info-header">
          <img :src="'/pictures/bot_avatar.jpg'" class="info-logo" alt="toktracker" onerror="this.src='/static/avatar_default.png'" />
          <div>
            <h4>toktracker System</h4>
            <span>TikTok Live Analytics &amp; Telegram Gateway</span>
          </div>
        </div>

        <div class="info-details">
          <div class="info-row">
            <span class="info-label">Telegram Bot:</span>
            <strong class="info-val">@{{ botUsername || 'toktrackeragent' }}</strong>
          </div>
          <div class="info-row">
            <span class="info-label">Gateway Status:</span>
            <span class="status-pill-ok">🟢 ONLINE</span>
          </div>
          <div class="info-row">
            <span class="info-label">Überwachte Streamer:</span>
            <strong>{{ totals.streamer_count }} Profile</strong>
          </div>
          <div class="info-row">
            <span class="info-label">Aktuell Live:</span>
            <strong class="text-emerald">{{ totals.live_count }} Streamer</strong>
          </div>
        </div>

        <div class="info-links">
          <a :href="`https://t.me/${(botUsername || 'toktrackeragent').replace('@', '')}`" target="_blank" class="btn-tg">
            Telegram Bot öffnen ↗
          </a>
          <a href="/public" target="_blank" class="btn-public">
            Vollständiges Public Portal ↗
          </a>
        </div>
      </div>
    </div>

    <!-- Streamer Detail Modal -->
    <StreamerDetailModal
      :streamer-id="selectedStreamerId"
      :period="period"
      @close="selectedStreamerId = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { formatEUR, formatUSD, formatNumber } from "./utils/formatters";
import StreamerDetailModal from "./components/dashboard/StreamerDetailModal.vue";

// State
const period = ref("24h");
const activeTab = ref<"streamers" | "gifts" | "info">("streamers");
const isLoading = ref(false);
const searchQuery = ref("");
const selectedStreamerId = ref<number | null>(null);
const isAdmin = ref(false);
const botUsername = ref("");

const totals = ref({
  streamer_count: 0,
  live_count: 0,
  total_coins: 0,
  eur_net: 0,
  usd_net: 0,
  gift_events_count: 0,
});

const streamersList = ref<any[]>([]);
const recentGifts = ref<any[]>([]);

const filteredStreamers = computed(() => {
  if (!searchQuery.value.trim()) return streamersList.value;
  const q = searchQuery.value.toLowerCase().trim();
  return streamersList.value.filter(
    (s) =>
      s.username.toLowerCase().includes(q) ||
      (s.display_name && s.display_name.toLowerCase().includes(q))
  );
});

function setPeriod(p: string) {
  period.value = p;
  loadData();
}

function getPeriodLabel(p: string) {
  switch (p) {
    case "today": return "Heute";
    case "24h": return "24 Std.";
    case "7d": return "7 Tage";
    case "30d": return "30 Tage";
    default: return "Gesamt";
  }
}

function getRankClass(rank: number) {
  if (rank === 1) return "rank-top-1";
  if (rank === 2) return "rank-top-2";
  if (rank === 3) return "rank-top-3";
  return "";
}

function formatTime(str?: string) {
  if (!str) return "-";
  try {
    const d = new Date(str);
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return str;
  }
}

async function loadData() {
  isLoading.value = true;
  try {
    const res = await fetch(`/api/public/overview?period=${encodeURIComponent(period.value)}`);
    if (res.ok) {
      const data = await res.json();
      if (data.totals) totals.value = data.totals;
      streamersList.value = data.streamers || [];
      recentGifts.value = data.recent_gifts || [];
    }
  } catch (err) {
    console.error("Fehler beim Laden der Mini-App Daten:", err);
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  // Telegram WebApp Initialization
  try {
    const tg = (window as any).Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      if (tg.initDataUnsafe?.user) {
        isAdmin.value = Boolean(tg.initDataUnsafe.user.is_admin);
      }
    }
  } catch {}

  loadData();
});
</script>

<style scoped>
.ma-app-wrapper {
  max-width: 680px;
  margin: 0 auto;
  min-height: 100vh;
  padding: 12px 14px 48px;
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  color: #f1f5f9;
  box-sizing: border-box;
}

/* Header */
.ma-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0 14px;
}

.ma-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ma-brand-logo {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.15);
}

.ma-brand-title {
  font-size: 17px;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1.2;
}

.ma-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.2);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: #7dd3fc;
}

.ma-admin-indicator {
  font-size: 10px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(245, 158, 11, 0.2);
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: #fbbf24;
}

.ma-brand-sub {
  font-size: 11.5px;
  color: #94a3b8;
  font-weight: 600;
}

.btn-icon-refresh {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Period Pills */
.ma-period-selector {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 4px 0 12px;
  scrollbar-width: none;
}

.ma-period-selector::-webkit-scrollbar {
  display: none;
}

.period-pill {
  padding: 6px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.period-pill.active {
  background: #38bdf8;
  border-color: #38bdf8;
  color: #090d16;
}

/* Live Banner */
.ma-live-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 14px;
}

.ma-live-banner.has-active {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #f87171;
}

.ma-live-banner.no-active {
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid rgba(148, 163, 184, 0.15);
  color: #94a3b8;
}

.live-pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 6px #ef4444;
  animation: pulseDot 1.6s infinite;
}

@keyframes pulseDot {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

/* KPI Grid */
.ma-kpi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.ma-kpi-card {
  background: rgba(15, 21, 35, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 14px;
}

.ma-kpi-card.full-width {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(15, 21, 35, 0.8));
  border-color: rgba(16, 185, 129, 0.3);
}

.kpi-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 2px;
}

.kpi-value {
  font-size: 22px;
  font-weight: 800;
}

.kpi-value.highlight {
  color: #34d399;
}

.kpi-right {
  text-align: right;
}

.kpi-sub {
  font-size: 12px;
  color: #94a3b8;
}

.kpi-quote {
  font-size: 10.5px;
  color: #38bdf8;
  font-weight: 600;
}

.text-cyan { color: #38bdf8; }
.text-purple { color: #c084fc; }

/* Quick Actions */
.ma-quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}

.quick-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  text-decoration: none;
  color: #fff;
  transition: all 0.2s ease;
}

.btn-radar {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.15), rgba(15, 21, 35, 0.7));
  border: 1px solid rgba(168, 85, 247, 0.3);
}

.btn-ci {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(15, 21, 35, 0.7));
  border: 1px solid rgba(56, 189, 248, 0.3);
}

.quick-btn .icon {
  font-size: 22px;
}

.quick-btn .btn-text strong {
  display: block;
  font-size: 12.5px;
}

.quick-btn .btn-text span {
  font-size: 10.5px;
  color: #94a3b8;
}

/* Tabs Bar */
.ma-tabs-bar {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 14px;
}

.ma-tab-btn {
  flex: 1;
  padding: 10px 0;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.ma-tab-btn.active {
  color: #38bdf8;
  border-bottom-color: #38bdf8;
}

.tab-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

/* Search */
.search-wrap {
  margin-bottom: 12px;
}

.ma-search-input {
  width: 100%;
  padding: 10px 14px;
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #ffffff;
  font-size: 13px;
  box-sizing: border-box;
  outline: none;
}

/* Streamer List */
.streamer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ma-streamer-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.15s ease;
}

.ma-streamer-card:hover {
  background: rgba(255, 255, 255, 0.06);
}

.card-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ma-rank-pill {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  min-width: 24px;
  text-align: center;
}

.rank-top-1 { color: #fbbf24; font-weight: 800; }
.rank-top-2 { color: #f1f5f9; font-weight: 800; }
.rank-top-3 { color: #f97316; font-weight: 800; }

.avatar-wrap {
  position: relative;
}

.ma-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.live-dot-pulse-mini {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 6px #ef4444;
}

.streamer-info {
  display: flex;
  flex-direction: column;
}

.streamer-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.streamer-display {
  font-size: 13.5px;
  color: #fff;
}

.badge-live {
  font-size: 9px;
  font-weight: 800;
  padding: 1px 4px;
  border-radius: 4px;
  background: #ef4444;
  color: #fff;
}

.streamer-handle {
  font-size: 11.5px;
  color: #94a3b8;
}

.card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.coins-val {
  font-size: 13px;
  font-weight: 700;
}

.net-val {
  font-size: 11.5px;
  font-weight: 700;
  color: #34d399;
}

/* Gifts List */
.gifts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ma-gift-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.gift-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gift-icon {
  font-size: 20px;
}

.gift-details strong {
  display: block;
  font-size: 13px;
  color: #fff;
}

.repeat-tag {
  color: #38bdf8;
  font-size: 11px;
}

.gift-sub {
  font-size: 11px;
  color: #94a3b8;
}

.gift-right {
  text-align: right;
  display: flex;
  flex-direction: column;
}

.gift-coins {
  font-size: 12.5px;
}

.gift-time {
  font-size: 10.5px;
  color: #64748b;
}

/* Info Tab */
.info-card {
  padding: 18px;
}

.info-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.info-logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
}

.info-header h4 {
  margin: 0;
  font-size: 16px;
  color: #fff;
}

.info-header span {
  font-size: 11.5px;
  color: #94a3b8;
}

.info-details {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 18px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.info-label {
  color: #94a3b8;
}

.status-pill-ok {
  font-size: 11px;
  font-weight: 700;
  color: #34d399;
}

.info-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn-tg, .btn-public {
  display: block;
  text-align: center;
  padding: 10px;
  border-radius: 10px;
  font-size: 12.5px;
  font-weight: 700;
  text-decoration: none;
}

.btn-tg {
  background: #2563eb;
  color: #fff;
}

.btn-public {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
}

.ma-empty {
  text-align: center;
  padding: 36px 12px;
  color: #94a3b8;
  font-size: 12.5px;
}
</style>
