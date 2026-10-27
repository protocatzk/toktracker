<template>
  <div class="toktracker-app">
    <!-- Kopfbereich: toktracker Brand & Systemstatus-Pills -->
    <header class="app-header">
      <div class="header-inner">
        <a href="/panel" class="brand-block">
          <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" />
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-mode-tag">ADMIN CONSOLE</span>
            </div>
            <span class="brand-subtitle">LIVE EARNINGS · ANALYTICS · BOT BACKEND</span>
          </div>
        </a>

        <div class="status-strip">
          <span class="pill">
            Admin: <strong>@admin</strong>
          </span>
          <span class="pill">
            TikTokLive: <strong style="color:#10b981;">AKTIV</strong>
          </span>
          <span class="pill">
            Worker: <strong>{{ store.activeWorkersCount }} aktiv</strong> ({{ store.liveStreamersCount }} LIVE)
          </span>
          <span class="pill">
            Telegram-Bot: <strong :style="{ color: store.system?.telegram_bot?.state === 'running' ? '#10b981' : '#f59e0b' }">
              {{ (store.system?.telegram_bot?.state || 'OFFLINE').toUpperCase() }}
            </strong>
          </span>
          <span class="pill">
            Bot-Zugriff: <strong>{{ (store.settings?.telegram_access_mode || 'whitelist').toUpperCase() }}</strong>
          </span>
          <a href="/radar" class="pill nav-pill">🎯 Spender-Radar</a>
          <a href="/chat-intelligence" class="pill nav-pill">💬 Chat-Intelligence</a>
          <a href="/public" class="pill nav-pill">Öffentliches User-Panel →</a>
          <a href="/logout" class="pill nav-pill danger-pill">Abmelden</a>
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
          Streamer &amp; Einnahmen
          <span class="tab-badge">{{ store.streamers.length }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'gifts' }]"
          @click="currentTab = 'gifts'"
        >
          Gift-Protokoll &amp; Buchung
          <span class="tab-badge">{{ store.totals.gift_events_count }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'telegram' }]"
          @click="currentTab = 'telegram'"
        >
          Telegram-Bot &amp; Whitelist
          <span class="tab-badge">{{ store.telegramUsers.length }}</span>
        </button>
        <button
          type="button"
          :class="['tab-btn', { active: currentTab === 'settings' }]"
          @click="currentTab = 'settings'"
        >
          System, Kurse &amp; Banner
        </button>
      </nav>

      <!-- Aktions- und Filter-Leiste -->
      <section class="toolbar">
        <div class="toolbar-left">
          <label for="periodSelect">Zeitraum:</label>
          <select
            id="periodSelect"
            :value="store.period"
            @change="onPeriodChange"
            class="sm-input"
          >
            <option value="today">Heute (ab 00:00)</option>
            <option value="24h">Letzte 24 Stunden</option>
            <option value="7d">Letzte 7 Tage</option>
            <option value="30d">Letzte 30 Tage</option>
            <option value="all">Gesamt (All-Time)</option>
          </select>

          <button
            type="button"
            class="sm"
            @click="store.loadOverview()"
            :disabled="store.isLoading"
          >
            {{ store.isLoading ? 'Lädt...' : 'Aktualisieren' }}
          </button>
          <a class="btn-link sm hide-sm" href="/api/export/gifts.csv" target="_blank">Gifts CSV</a>
          <a class="btn-link sm hide-sm" href="/api/export/battles.csv" target="_blank">Battles CSV</a>
          <a class="btn-link sm hide-sm" href="/docs" target="_blank">API Docs</a>
        </div>

        <div class="toolbar-right">
          <button type="button" class="sm secondary" @click="toggleTheme">
            Theme: {{ currentTheme.toUpperCase() }}
          </button>
        </div>
      </section>

      <!-- Kennzahlen-Karten (Summary Cards) -->
      <section class="metrics-grid">
        <MetricCard
          label="NETTO CREATOR-AUSZAHLUNG"
          :value="formatEUR(store.totals.eur_net)"
          :subtext="`${formatUSD(store.totals.usd_net)} USD`"
        />
        <MetricCard
          label="GESAMT COINS / DIAMONDS"
          :value="formatNumber(store.totals.total_coins)"
          :subtext="`${store.totals.streamer_count} Streamer (${store.totals.live_count} LIVE)`"
        />
        <MetricCard
          label="BRUTTO ZUSCHAUER-KAUFWERT"
          :value="formatEUR(store.totals.eur_gross)"
          :subtext="`${formatUSD(store.totals.usd_gross)} USD`"
        />
        <MetricCard
          label="ERFASSTE GESCHENKE"
          :value="formatNumber(store.totals.total_gifts_sent)"
          :subtext="`${formatNumber(store.totals.gift_events_count)} Transaktionen`"
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

      <div v-show="currentTab === 'settings'" class="settings-grid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(380px, 1fr)); gap:20px;">
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
        <span class="mono muted">toktracker · LIVE EARNINGS · ANALYTICS</span>
        <div class="footer-links">
          <a href="/radar">Spender-Radar</a>
          <a href="/chat-intelligence">Chat-Intelligence</a>
          <a href="/public">Öffentliches User-Panel</a>
          <a href="/docs">API Dokumentation</a>
          <a href="/logout">Abmelden</a>
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
}
.app-body {
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  padding: 16px 20px 40px;
}
.status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.nav-pill {
  text-decoration: none;
  transition: opacity 0.2s;
}
.nav-pill:hover {
  opacity: 0.8;
}
.danger-pill {
  color: #ef4444;
}
.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-subtle, #2a2e39);
  margin-bottom: 16px;
  overflow-x: auto;
}
.tab-btn {
  background: none;
  border: none;
  color: var(--text-muted, #94a3b8);
  padding: 10px 16px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}
.tab-btn.active {
  color: #38bdf8;
  border-bottom-color: #38bdf8;
}
.tab-badge {
  background: var(--bg-card, #1e222d);
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 11px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.app-footer {
  border-top: 1px solid var(--border-subtle, #2a2e39);
  padding: 20px;
  margin-top: auto;
}
.footer-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.footer-links {
  display: flex;
  gap: 16px;
}
.footer-links a {
  color: var(--text-muted, #94a3b8);
  text-decoration: none;
  font-size: 13px;
}
.footer-links a:hover {
  color: #38bdf8;
}
</style>
