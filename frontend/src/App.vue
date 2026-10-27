<template>
  <div class="toktracker-app">
    <!-- Kopfbereich: toktracker Brand & Systemstatus-Pills -->
    <header class="app-header">
      <div class="header-inner">
        <a href="/panel" class="brand-block">
          <div class="brand-logo-wrap">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" />
            <span class="brand-live-indicator"></span>
          </div>
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-badge-admin">ADMIN CONSOLE</span>
            </div>
            <span class="brand-subtitle">Live Earnings · Analytics · Microservices</span>
          </div>
        </a>

        <div class="status-strip">
          <span class="pill">
            <span class="pill-dot"></span>
            TikTokLive: <strong style="color: #34d399;">AKTIV</strong>
          </span>
          <span class="pill">
            Worker: <strong>{{ store.activeWorkersCount }} aktiv</strong> ({{ store.liveStreamersCount }} LIVE)
          </span>
          <span class="pill">
            Telegram-Bot: <strong :style="{ color: store.system?.telegram_bot?.state === 'running' ? '#34d399' : '#fbbf24' }">
              {{ (store.system?.telegram_bot?.state || 'OFFLINE').toUpperCase() }}
            </strong>
          </span>
          <a href="/donor-radar" class="pill nav-pill highlight-pill">
            🐋 Spender-Radar
          </a>
          <a href="/chat-intelligence" class="pill nav-pill highlight-purple">
            💬 Chat-Intelligence
          </a>
          <a href="/miniapp" target="_blank" class="pill nav-pill">
            📱 Mini-App ↗
          </a>
          <a href="/public" class="pill nav-pill">
            Öffentliches Portal →
          </a>
          <a href="/logout" class="pill nav-pill danger-pill">
            Abmelden
          </a>
        </div>
      </div>
    </header>

    <main class="app-body">
      <!-- Tab Navigation Leiste -->
      <nav class="tab-nav">
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'streamers' }]"
          @click="currentTab = 'streamers'"
        >
          <span class="tab-icon">👥</span>
          Streamer &amp; Einnahmen
          <span class="tab-badge">{{ store.streamers.length }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'gifts' }]"
          @click="currentTab = 'gifts'"
        >
          <span class="tab-icon">🎁</span>
          Gift-Protokoll &amp; Buchung
          <span class="tab-badge">{{ store.totals.gift_events_count }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'telegram' }]"
          @click="currentTab = 'telegram'"
        >
          <span class="tab-icon">🤖</span>
          Telegram-Bot &amp; Whitelist
          <span class="tab-badge">{{ store.telegramUsers.length }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'settings' }]"
          @click="currentTab = 'settings'"
        >
          <span class="tab-icon">⚙️</span>
          System, Kurse &amp; Banner
        </button>
      </nav>

      <!-- Aktions- und Filter-Leiste -->
      <section class="toolbar-section">
        <div class="toolbar-left">
          <div class="period-control">
            <label for="periodSelect" class="control-label">Zeitraum</label>
            <div class="select-wrapper">
              <select
                id="periodSelect"
                :value="store.period"
                @change="onPeriodChange"
                class="modern-select"
              >
                <option value="today">Heute (ab 00:00)</option>
                <option value="24h">Letzte 24 Stunden</option>
                <option value="7d">Letzte 7 Tage</option>
                <option value="30d">Letzte 30 Tage</option>
                <option value="all">Gesamt (All-Time)</option>
              </select>
            </div>
          </div>

          <button
            type="button"
            class="btn-refresh"
            @click="store.loadOverview()"
            :disabled="store.isLoading"
          >
            <span :class="['refresh-icon', { spinning: store.isLoading }]">🔄</span>
            <span>{{ store.isLoading ? 'Lädt...' : 'Aktualisieren' }}</span>
          </button>
          <a class="btn-glass sm hide-sm" href="/api/export/gifts.csv" target="_blank">📥 Gifts CSV</a>
          <a class="btn-glass sm hide-sm" href="/api/export/battles.csv" target="_blank">📥 Battles CSV</a>
          <a class="btn-glass sm hide-sm" href="/docs" target="_blank">📖 API Docs</a>
        </div>

        <div class="toolbar-right">
          <button type="button" class="btn-glass sm" @click="toggleTheme">
            {{ currentTheme === 'dark' ? '🌙 Dark' : '☀️ Light' }}
          </button>
        </div>
      </section>

      <!-- Kennzahlen-Karten (Summary Cards) -->
      <section class="metrics-grid">
        <MetricCard
          label="Netto Creator-Auszahlung"
          :value="formatEUR(store.totals.eur_net)"
          :subtext="`${formatUSD(store.totals.usd_net)} USD (~50% Quote)`"
          icon="💰"
          variant="emerald"
        />
        <MetricCard
          label="Erfasste Diamanten &amp; Coins"
          :value="formatNumber(store.totals.total_coins)"
          :subtext="`${store.totals.streamer_count} Streamer (${store.totals.live_count} LIVE)`"
          icon="💎"
          variant="primary"
        />
        <MetricCard
          label="Brutto Zuschauer-Kaufwert"
          :value="formatEUR(store.totals.eur_gross)"
          :subtext="`${formatUSD(store.totals.usd_gross)} USD Ausgaben`"
          icon="🛍️"
          variant="purple"
        />
        <MetricCard
          label="Erfasste Geschenke"
          :value="formatNumber(store.totals.total_gifts_sent)"
          :subtext="`${formatNumber(store.totals.gift_events_count)} Transaktionen`"
          icon="🎁"
          variant="amber"
        />
      </section>

      <!-- Aktiver Tab-Inhalt -->
      <div v-show="currentTab === 'streamers'">
        <StreamerTable @select-streamer="openDetailModal" />
      </div>

      <div v-show="currentTab === 'gifts'">
        <GiftLogTable />
      </div>

      <div v-show="currentTab === 'telegram'">
        <TelegramWhitelist />
      </div>

      <div v-show="currentTab === 'settings'" class="settings-grid">
        <CurrencySettings />
        <PublicBannerSettings />
      </div>

      <!-- Streamer Detail Modal -->
      <StreamerDetailModal
        :streamer-id="selectedStreamerId"
        :period="store.period"
        @close="selectedStreamerId = null"
      />
    </main>

    <!-- Footer -->
    <footer class="app-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="footer-logo">toktracker</span>
          <span class="footer-tag">Live Earnings &amp; Microservice Platform</span>
        </div>
        <div class="footer-links">
          <a href="/donor-radar" class="footer-link">🐋 Spender-Radar</a>
          <a href="/chat-intelligence" class="footer-link">💬 Chat-Intelligence</a>
          <a href="/miniapp" target="_blank" class="footer-link">📱 Mini-App</a>
          <a href="/public" class="footer-link">Öffentliches Portal</a>
          <a href="/docs" target="_blank" class="footer-link">API Dokumentation</a>
          <a href="/logout" class="footer-link danger-link">Abmelden</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useDashboardStore } from "./stores/dashboardStore";
import { formatEUR, formatUSD, formatNumber } from "./utils/formatters";
import MetricCard from "./components/common/MetricCard.vue";
import StreamerTable from "./components/dashboard/StreamerTable.vue";
import GiftLogTable from "./components/dashboard/GiftLogTable.vue";
import TelegramWhitelist from "./components/dashboard/TelegramWhitelist.vue";
import PublicBannerSettings from "./components/dashboard/PublicBannerSettings.vue";
import CurrencySettings from "./components/dashboard/CurrencySettings.vue";
import StreamerDetailModal from "./components/dashboard/StreamerDetailModal.vue";

const store = useDashboardStore();

const currentTab = ref<"streamers" | "gifts" | "telegram" | "settings">("streamers");
const selectedStreamerId = ref<number | null>(null);
const currentTheme = ref<string>("dark");

onMounted(async () => {
  currentTheme.value = document.documentElement.getAttribute("data-theme") || "dark";
  await store.loadOverview();
  store.startPolling();
});

onUnmounted(() => {
  store.stopPolling();
});

function onPeriodChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  store.setPeriod(target.value);
}

function openDetailModal(streamerId: number) {
  selectedStreamerId.value = streamerId;
}

function toggleTheme() {
  const next = currentTheme.value === "light" ? "dark" : "light";
  currentTheme.value = next;
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("toktracker_theme", next);
  } catch {}
}
</script>

<style scoped>
.toktracker-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-body, #090d16);
  color: var(--text-main, #f1f5f9);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Glass Header */
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(9, 13, 22, 0.82);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 14px 24px;
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
  gap: 14px;
  text-decoration: none;
}

.brand-logo-wrap {
  position: relative;
}

.brand-logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid rgba(56, 189, 248, 0.3);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  display: block;
}

.brand-live-indicator {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #10b981;
  border: 2px solid #090d16;
  box-shadow: 0 0 8px #10b981;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.brand-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.6px;
  margin: 0;
  line-height: 1;
  color: #ffffff;
}

.brand-badge-admin {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.15);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #38bdf8;
}

.brand-subtitle {
  font-size: 11.5px;
  letter-spacing: 0.2px;
  color: #94a3b8;
  font-weight: 500;
}

.status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 11.5px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  transition: all 0.2s ease;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
}

.nav-pill {
  text-decoration: none;
  font-weight: 600;
  cursor: pointer;
}

.nav-pill:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}

.highlight-pill {
  border-color: rgba(56, 189, 248, 0.35);
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.08);
}

.highlight-purple {
  border-color: rgba(168, 85, 247, 0.35);
  color: #c084fc;
  background: rgba(168, 85, 247, 0.08);
}

.danger-pill {
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.08);
}

/* Body */
.app-body {
  flex: 1;
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 24px 48px;
}

/* Tab Navigation */
.tab-nav {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  overflow-x: auto;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 8px;
}

.tab-btn {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 12px;
  color: #94a3b8;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
}

.tab-btn:hover {
  color: #f1f5f9;
  background: rgba(255, 255, 255, 0.04);
}

.tab-btn.active {
  color: #ffffff;
  background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.35);
  box-shadow: 0 4px 14px rgba(56, 189, 248, 0.15);
}

.tab-icon {
  font-size: 15px;
}

.tab-badge {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
}

.tab-btn.active .tab-badge {
  background: #38bdf8;
  color: #090d16;
}

/* Toolbar */
.toolbar-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.period-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.control-label {
  font-size: 12.5px;
  font-weight: 600;
  color: #94a3b8;
}

.select-wrapper {
  position: relative;
}

.modern-select {
  appearance: none;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 8px 32px 8px 14px;
  color: #f1f5f9;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 14px;
}

.modern-select:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 8px 14px;
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

.btn-glass {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-glass:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

@media (max-width: 1024px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

/* Footer */
.app-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: 24px;
  margin-top: auto;
  background: rgba(9, 13, 22, 0.5);
}

.footer-inner {
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.footer-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.footer-logo {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-weight: 800;
  color: #ffffff;
  font-size: 14px;
}

.footer-tag {
  font-size: 12px;
  color: #64748b;
}

.footer-links {
  display: flex;
  gap: 18px;
  align-items: center;
  flex-wrap: wrap;
}

.footer-link {
  color: #94a3b8;
  text-decoration: none;
  font-size: 13px;
  transition: color 0.15s ease;
}

.footer-link:hover {
  color: #38bdf8;
}

.danger-link {
  color: #f87171;
}

@media (max-width: 768px) {
  .hide-sm {
    display: none !important;
  }
  .toolbar-section {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
