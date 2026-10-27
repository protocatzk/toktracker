<template>
  <div class="toktracker-public-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <a href="/public" class="brand-block">
          <div class="brand-logo-wrap">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" />
            <span class="brand-live-indicator"></span>
          </div>
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-badge-public">PUBLIC RADAR</span>
            </div>
            <span class="brand-subtitle">Live TikTok Earnings &amp; Leaderboard</span>
          </div>
        </a>

        <div class="header-actions">
          <a href="/miniapp" target="_blank" class="btn-glass sm">
            <span class="icon">📱</span> Mini-App
          </a>
          <button type="button" class="btn-glass sm" @click="toggleTheme">
            {{ currentTheme === 'dark' ? '🌙 Dark' : '☀️ Light' }}
          </button>
          <a href="/login" class="btn-gradient sm">
            Admin-Login →
          </a>
        </div>
      </div>
    </header>

    <main class="app-body">
      <!-- Ankündigungsbanner -->
      <div
        v-if="bannerEnabled"
        :class="['announcement-banner', bannerStyle]"
      >
        <div class="banner-tag">{{ bannerTagText }}</div>
        <div class="banner-content">
          <strong>{{ bannerTitle }}</strong>
          <p>{{ bannerText }}</p>
        </div>
        <div class="banner-action" v-if="bannerBtnText">
          <a :href="bannerBtnUrl || '#'" target="_blank" class="btn-primary sm">
            {{ bannerBtnText }}
          </a>
        </div>
      </div>

      <!-- Toolbar -->
      <section class="toolbar-section">
        <div class="toolbar-left">
          <div class="period-control">
            <label for="publicPeriodSelect" class="control-label">Zeitraum</label>
            <div class="select-wrapper">
              <select
                id="publicPeriodSelect"
                v-model="period"
                @change="loadData"
                class="modern-select"
              >
                <option value="today">Heute (ab 00:00)</option>
                <option value="24h">Letzte 24 Stunden</option>
                <option value="7d">Letzte 7 Tage</option>
                <option value="all">Gesamt (All-Time)</option>
              </select>
            </div>
          </div>
          <button
            type="button"
            class="btn-refresh"
            @click="loadData"
            :disabled="isLoading"
            title="Daten aktualisieren"
          >
            <span :class="['refresh-icon', { spinning: isLoading }]">🔄</span>
            <span class="btn-text">{{ isLoading ? 'Lädt...' : 'Aktualisieren' }}</span>
          </button>
        </div>

        <div class="toolbar-right">
          <div class="search-input-wrapper">
            <span class="search-icon">🔍</span>
            <input
              v-model="searchQuery"
              type="search"
              placeholder="Streamer nach Namen filtern..."
              class="modern-search"
            />
          </div>
        </div>
      </section>

      <!-- Metric Cards Grid -->
      <section class="metrics-grid">
        <MetricCard
          label="Netto Creator-Auszahlung"
          :value="formatEUR(totals.eur_net)"
          :subtext="`${formatUSD(totals.usd_net)} USD (~50% Quote)`"
          icon="💰"
          variant="emerald"
        />
        <MetricCard
          label="Erfasste Diamanten &amp; Coins"
          :value="formatNumber(totals.total_coins)"
          :subtext="`${totals.streamer_count} Streamer (${totals.live_count} LIVE)`"
          icon="💎"
          variant="primary"
        />
        <MetricCard
          label="Brutto Zuschauer-Kaufwert"
          :value="formatEUR(totals.eur_gross)"
          :subtext="`${formatUSD(totals.usd_gross)} USD Ausgaben`"
          icon="🛍️"
          variant="purple"
        />
        <MetricCard
          label="Erfasste Geschenke"
          :value="formatNumber(totals.total_gifts_sent)"
          :subtext="`${formatNumber(totals.gift_events_count)} Transaktionen`"
          icon="🎁"
          variant="amber"
        />
      </section>

      <!-- Streamer Rangliste -->
      <div class="leaderboard-card">
        <div class="card-header-bar">
          <div class="header-title-group">
            <h3 class="card-title">Streamer Leaderboard</h3>
            <span class="live-pill" v-if="totals.live_count > 0">
              <span class="live-dot-pulse"></span>
              {{ totals.live_count }} JETZT LIVE
            </span>
          </div>
          <span class="count-badge">
            {{ filteredStreamers.length }} von {{ streamers.length }} Streamern
          </span>
        </div>

        <div class="table-responsive">
          <table class="modern-table">
            <thead>
              <tr>
                <th style="width: 70px; text-align: center;">RANG</th>
                <th>STREAMER</th>
                <th style="width: 120px;">STATUS</th>
                <th class="num-col">ZUSCHAUER</th>
                <th class="num-col">COINS</th>
                <th class="num-col">NETTO (EUR)</th>
                <th class="num-col hide-sm">NETTO (USD)</th>
                <th class="hide-sm">TOP GESCHENK</th>
                <th style="width: 100px; text-align: right;">AKTION</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="filteredStreamers.length === 0">
                <td colspan="9" class="empty-cell">
                  <div class="empty-state">
                    <span class="empty-icon">⏳</span>
                    <p>{{ isLoading ? 'Lade Streamer-Daten...' : 'Keine Streamer für diesen Filter gefunden.' }}</p>
                  </div>
                </td>
              </tr>
              <tr
                v-for="(s, index) in filteredStreamers"
                :key="s.id"
                class="streamer-row"
                @click="selectedStreamerId = s.id"
              >
                <td class="rank-col">
                  <span :class="['rank-pill', index < 3 ? `rank-top-${index + 1}` : '']">
                    {{ index === 0 ? '👑 1' : index === 1 ? '🥈 2' : index === 2 ? '🥉 3' : `#${index + 1}` }}
                  </span>
                </td>
                <td>
                  <div class="streamer-profile">
                    <img
                      :src="s.avatar_url || '/pictures/bot_avatar.jpg'"
                      :alt="s.username"
                      class="streamer-avatar"
                      loading="lazy"
                      @error="(e) => (e.target as HTMLImageElement).src = '/pictures/bot_avatar.jpg'"
                    />
                    <div class="streamer-names">
                      <span class="streamer-display-name">
                        {{ s.display_name || s.username }}
                      </span>
                      <span class="streamer-handle">@{{ s.username }}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <StatusTag
                    :state="s.worker_diagnostics?.state || (s.is_live ? 'live' : 'stopped')"
                    :is-live="Boolean(s.is_live)"
                  >
                    {{ s.is_live ? 'LIVE' : 'OFFLINE' }}
                  </StatusTag>
                </td>
                <td class="num-col">
                  <span class="viewer-count" v-if="s.is_live">
                    <span class="live-pulse-dot"></span>
                    {{ formatNumber(s.current_viewers || 0) }}
                  </span>
                  <span v-else class="muted-dash">-</span>
                </td>
                <td class="num-col coins-col">
                  {{ formatNumber(s.total_coins) }}
                </td>
                <td class="num-col revenue-eur">
                  {{ formatEUR(s.eur_net) }}
                </td>
                <td class="num-col hide-sm revenue-usd">
                  {{ formatUSD(s.usd_net) }}
                </td>
                <td class="hide-sm">
                  <span v-if="s.top_gift" class="top-gift-badge">
                    🎁 {{ s.top_gift.gift_name }}
                    <span class="gift-coins">({{ formatNumber(s.top_gift.coins) }})</span>
                  </span>
                  <span v-else class="muted-dash">-</span>
                </td>
                <td style="text-align: right;">
                  <button
                    type="button"
                    class="btn-stats"
                    @click.stop="selectedStreamerId = s.id"
                  >
                    Stats →
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Streamer Detail Modal -->
      <StreamerDetailModal
        :streamer-id="selectedStreamerId"
        :period="period"
        @close="selectedStreamerId = null"
      />
    </main>

    <!-- Footer -->
    <footer class="app-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="footer-logo">toktracker</span>
          <span class="footer-tag">Public Analytics Radar</span>
        </div>
        <div class="footer-links">
          <a href="/public" class="footer-link">Öffentliche Ansicht</a>
          <a href="/miniapp" target="_blank" class="footer-link">Telegram Mini-App</a>
          <a href="/login" class="footer-link admin-link">Admin-Console →</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { api } from "./services/api";
import { formatEUR, formatUSD, formatNumber } from "./utils/formatters";
import type { Streamer, OverviewTotals } from "./types";
import MetricCard from "./components/common/MetricCard.vue";
import StatusTag from "./components/common/StatusTag.vue";
import StreamerDetailModal from "./components/dashboard/StreamerDetailModal.vue";

const period = ref("24h");
const isLoading = ref(false);
const searchQuery = ref("");
const selectedStreamerId = ref<number | null>(null);
const currentTheme = ref("dark");

const totals = ref<OverviewTotals>({
  streamer_count: 0,
  live_count: 0,
  active_workers_count: 0,
  total_diamonds_collected: 0,
  total_coins: 0,
  eur_net: 0,
  usd_net: 0,
  eur_gross: 0,
  usd_gross: 0,
  total_gifts_sent: 0,
  gift_events_count: 0,
});

const streamers = ref<Streamer[]>([]);
const bannerData = ref<Record<string, any>>({});

const bannerEnabled = computed(() => Boolean(bannerData.value.enabled));
const bannerTitle = computed(() => bannerData.value.title || "");
const bannerText = computed(() => bannerData.value.text || "");
const bannerStyle = computed(() => bannerData.value.style || "highlight");
const bannerBtnText = computed(() => bannerData.value.btn_text || "");
const bannerBtnUrl = computed(() => bannerData.value.btn_url || "");
const bannerTagText = computed(() => {
  if (bannerData.value.tag_text) return bannerData.value.tag_text;
  switch (bannerStyle.value) {
    case "warning":
      return "⚠️ WICHTIG";
    case "success":
      return "🟢 STATUS";
    case "info":
      return "ℹ️ INFO";
    default:
      return "✨ WHITELIST PROMO";
  }
});

const filteredStreamers = computed(() => {
  if (!searchQuery.value.trim()) return streamers.value;
  const q = searchQuery.value.toLowerCase().trim();
  return streamers.value.filter(
    (s) =>
      s.username.toLowerCase().includes(q) ||
      (s.display_name && s.display_name.toLowerCase().includes(q))
  );
});

async function loadData() {
  isLoading.value = true;
  try {
    const res = await api.getPublicOverview(period.value);
    totals.value = res.totals || totals.value;
    streamers.value = res.streamers || [];
    bannerData.value = res.banner || res.public_banner || {};
  } catch (err) {
    console.error("Fehler beim Laden der Public-Daten:", err);
  } finally {
    isLoading.value = false;
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
  currentTheme.value = document.documentElement.getAttribute("data-theme") || "dark";
  loadData();
});
</script>

<style scoped>
.toktracker-public-app {
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

.brand-badge-public {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.35);
  color: #34d399;
}

.brand-subtitle {
  font-size: 11.5px;
  letter-spacing: 0.2px;
  color: #94a3b8;
  font-weight: 500;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
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

.btn-gradient {
  display: inline-flex;
  align-items: center;
  padding: 8px 16px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%);
  color: #090d16;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  text-decoration: none;
  border: none;
  box-shadow: 0 4px 14px rgba(14, 165, 233, 0.3);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-gradient:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
}

/* App Body */
.app-body {
  flex: 1;
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 24px 48px;
}

/* Announcement Banner */
.announcement-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 22px;
  border-radius: 14px;
  margin-bottom: 24px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
  transition: all 0.25s ease;
}

.announcement-banner.highlight {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.16), rgba(217, 119, 6, 0.08));
  border: 1px solid rgba(245, 158, 11, 0.35);
  box-shadow: 0 4px 24px rgba(245, 158, 11, 0.12);
}

.announcement-banner.warning {
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.16), rgba(220, 38, 38, 0.08));
  border: 1px solid rgba(239, 68, 68, 0.35);
  box-shadow: 0 4px 24px rgba(239, 68, 68, 0.12);
}

.announcement-banner.info {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.16), rgba(2, 132, 199, 0.08));
  border: 1px solid rgba(14, 165, 233, 0.35);
  box-shadow: 0 4px 24px rgba(14, 165, 233, 0.12);
}

.announcement-banner.success {
  background: linear-gradient(90deg, rgba(16, 185, 129, 0.16), rgba(5, 150, 105, 0.08));
  border: 1px solid rgba(16, 185, 129, 0.35);
  box-shadow: 0 4px 24px rgba(16, 185, 129, 0.12);
}

.banner-tag {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 5px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
  white-space: nowrap;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.banner-content {
  flex: 1;
}

.banner-content strong {
  display: block;
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 14.5px;
  font-weight: 800;
  color: #f8fafc;
  margin-bottom: 3px;
  letter-spacing: -0.01em;
}

.banner-content p {
  margin: 0;
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.45;
}

.banner-action {
  flex-shrink: 0;
}

.btn-primary.sm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
  border: none;
  border-radius: 10px;
  color: #ffffff;
  font-size: 12.5px;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
}

.btn-primary.sm:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.5);
  text-decoration: none;
}

@media (max-width: 768px) {
  .announcement-banner {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
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

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 12px;
  font-size: 13px;
  opacity: 0.6;
  pointer-events: none;
}

.modern-search {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 8px 14px 8px 34px;
  color: #f1f5f9;
  font-size: 13px;
  width: 260px;
  outline: none;
  transition: all 0.2s ease;
}

.modern-search:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
  width: 300px;
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

/* Leaderboard Card */
.leaderboard-card {
  background: var(--bg-surface, #0f1523);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 32px -4px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-wrap: wrap;
  gap: 12px;
}

.header-title-group {
  display: flex;
  align-items: center;
  gap: 14px;
}

.card-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 17px;
  font-weight: 800;
  letter-spacing: -0.3px;
  color: #ffffff;
  margin: 0;
}

.live-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 9999px;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #f87171;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.6px;
}

.live-dot-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 6px #ef4444;
  animation: pulseRed 1.6s infinite;
}

@keyframes pulseRed {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.count-badge {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

/* Modern Table */
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.modern-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}

.modern-table th {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  padding: 14px 18px;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}

.modern-table td {
  padding: 14px 18px;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.streamer-row {
  cursor: pointer;
  transition: background 0.15s ease;
}

.streamer-row:hover {
  background: rgba(56, 189, 248, 0.04);
}

.rank-col {
  text-align: center;
}

.rank-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 24px;
  padding: 0 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.04);
}

.rank-top-1 {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(217, 119, 6, 0.35));
  border: 1px solid rgba(245, 158, 11, 0.5);
  color: #fbbf24;
  font-weight: 800;
}

.rank-top-2 {
  background: linear-gradient(135deg, rgba(148, 163, 184, 0.2), rgba(100, 116, 139, 0.3));
  border: 1px solid rgba(148, 163, 184, 0.4);
  color: #e2e8f0;
}

.rank-top-3 {
  background: linear-gradient(135deg, rgba(180, 83, 9, 0.2), rgba(120, 53, 15, 0.3));
  border: 1px solid rgba(180, 83, 9, 0.4);
  color: #f97316;
}

.streamer-profile {
  display: flex;
  align-items: center;
  gap: 12px;
}

.streamer-avatar {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: #090d16;
  flex-shrink: 0;
}

.streamer-names {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.streamer-display-name {
  font-weight: 700;
  color: #ffffff;
  font-size: 14px;
  line-height: 1.2;
}

.streamer-handle {
  font-size: 12px;
  color: #94a3b8;
}

.viewer-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 700;
  color: #f87171;
}

.live-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 6px #ef4444;
  animation: pulseRed 1.8s infinite;
}

.coins-col {
  font-weight: 700;
  color: #e2e8f0;
}

.revenue-eur {
  font-weight: 800;
  color: #34d399;
  font-size: 14px;
}

.revenue-usd {
  color: #94a3b8;
  font-size: 12.5px;
}

.top-gift-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 12px;
  color: #e2e8f0;
}

.gift-coins {
  color: #94a3b8;
  font-size: 11px;
}

.muted-dash {
  color: #64748b;
}

.btn-stats {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-stats:hover {
  background: #38bdf8;
  color: #090d16;
  border-color: #38bdf8;
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.35);
}

.num-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty-cell {
  text-align: center;
  padding: 48px 16px !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
}

.empty-icon {
  font-size: 28px;
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

.admin-link {
  color: #38bdf8;
  font-weight: 600;
}

/* Responsive */
@media (max-width: 768px) {
  .hide-sm {
    display: none !important;
  }
  .modern-search {
    width: 100%;
  }
  .toolbar-section {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
