<template>
  <div class="toktracker-public-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <a href="/public" class="brand-block">
          <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" />
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-mode-tag" style="background: rgba(16, 185, 129, 0.15); color: #10b981;">
                PUBLIC RADAR
              </span>
            </div>
            <span class="brand-subtitle">LIVE EARNINGS · TIKTOK LEADERBOARD</span>
          </div>
        </a>

        <div class="header-actions" style="display:flex; gap:10px; align-items:center;">
          <button type="button" class="sm secondary" @click="toggleTheme">
            Theme: {{ currentTheme.toUpperCase() }}
          </button>
          <a href="/login" class="btn-link sm primary">Admin-Login →</a>
        </div>
      </div>
    </header>

    <main class="app-body">
      <!-- Ankündigungsbanner -->
      <div
        v-if="bannerEnabled"
        :class="['announcement-banner', bannerStyle]"
        style="margin-bottom: 24px;"
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
      <section class="toolbar">
        <div class="toolbar-left">
          <label for="publicPeriodSelect">Zeitraum:</label>
          <select
            id="publicPeriodSelect"
            v-model="period"
            @change="loadData"
            class="sm-input"
          >
            <option value="today">Heute</option>
            <option value="24h">Letzte 24 Stunden</option>
            <option value="7d">Letzte 7 Tage</option>
            <option value="all">Gesamt (All-Time)</option>
          </select>
          <button type="button" class="sm" @click="loadData" :disabled="isLoading">
            {{ isLoading ? 'Lädt...' : 'Aktualisieren' }}
          </button>
        </div>

        <div class="toolbar-right">
          <input
            v-model="searchQuery"
            type="search"
            placeholder="Streamer suchen..."
            class="sm-input"
            style="min-width: 200px;"
          />
        </div>
      </section>

      <!-- Metric Cards -->
      <section class="metrics-grid">
        <MetricCard
          label="NETTO CREATOR-AUSZAHLUNG"
          :value="formatEUR(totals.eur_net)"
          :subtext="`${formatUSD(totals.usd_net)} USD`"
        />
        <MetricCard
          label="GESAMT COINS / DIAMONDS"
          :value="formatNumber(totals.total_coins)"
          :subtext="`${totals.streamer_count} Streamer (${totals.live_count} LIVE)`"
        />
        <MetricCard
          label="BRUTTO ZUSCHAUER-KAUFWERT"
          :value="formatEUR(totals.eur_gross)"
          :subtext="`${formatUSD(totals.usd_gross)} USD`"
        />
        <MetricCard
          label="ERFASSTE GESCHENKE"
          :value="formatNumber(totals.total_gifts_sent)"
          :subtext="`${formatNumber(totals.gift_events_count)} Transaktionen`"
        />
      </section>

      <!-- Streamer Rangliste -->
      <div class="card">
        <div class="card-header-bar">
          <h3>STREAMER LEADERBOARD</h3>
          <span class="mono muted">
            {{ filteredStreamers.length }} von {{ streamers.length }} Streamern
          </span>
        </div>

        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px;">RANG</th>
                <th>STREAMER</th>
                <th>STATUS</th>
                <th class="num-col">ZUSCHAUER</th>
                <th class="num-col">COINS</th>
                <th class="num-col">NETTO (EUR)</th>
                <th class="num-col hide-sm">NETTO (USD)</th>
                <th class="hide-sm">TOP GESCHENK</th>
                <th>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="filteredStreamers.length === 0">
                <td colspan="9" class="muted text-center" style="padding: 32px;">
                  {{ isLoading ? 'Lade Daten...' : 'Keine Streamer gefunden.' }}
                </td>
              </tr>
              <tr v-for="(s, index) in filteredStreamers" :key="s.id">
                <td class="mono font-bold" style="color: #38bdf8;">
                  #{{ index + 1 }}
                </td>
                <td>
                  <strong>
                    <a href="#" @click.prevent="selectedStreamerId = s.id">
                      {{ s.display_name || s.username }}
                    </a>
                  </strong>
                  <div class="mono muted">@{{ s.username }}</div>
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
                  <strong>{{ formatNumber(s.current_viewers || 0) }}</strong>
                </td>
                <td class="num-col">
                  <strong>{{ formatNumber(s.total_coins) }}</strong>
                </td>
                <td class="num-col">
                  <strong>{{ formatEUR(s.eur_net) }}</strong>
                </td>
                <td class="num-col hide-sm">
                  {{ formatUSD(s.usd_net) }}
                </td>
                <td class="hide-sm">
                  {{ s.top_gift ? `${s.top_gift.gift_name} (${formatNumber(s.top_gift.coins)})` : '-' }}
                </td>
                <td>
                  <button
                    type="button"
                    class="sm"
                    @click="selectedStreamerId = s.id"
                  >
                    Stats
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
        <span class="mono muted">toktracker · PUBLIC RADAR</span>
        <div class="footer-links">
          <a href="/public">Öffentliche Ansicht</a>
          <a href="/login">Admin-Login</a>
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
  total_coins: 0,
  eur_net: 0,
  usd_net: 0,
  eur_gross: 0,
  usd_gross: 0,
  gift_events_count: 0,
  total_gifts_sent: 0,
});

const streamers = ref<Streamer[]>([]);

// Banner
const bannerEnabled = ref(false);
const bannerTitle = ref("");
const bannerText = ref("");
const bannerStyle = ref("highlight");
const bannerBtnText = ref("");
const bannerBtnUrl = ref("");

const filteredStreamers = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return streamers.value;
  return streamers.value.filter((s) => {
    const u = (s.username || "").toLowerCase();
    const d = (s.display_name || "").toLowerCase();
    return u.includes(q) || d.includes(q);
  });
});

const bannerTagText = computed(() => {
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

async function loadData() {
  isLoading.value = true;
  try {
    const res = await api.getPublicOverview(period.value);
    totals.value = res.totals || totals.value;
    streamers.value = res.streamers || [];
    if (res.settings) {
      bannerEnabled.value = Boolean(res.settings.public_banner_enabled);
      bannerTitle.value = res.settings.public_banner_title || "";
      bannerText.value = res.settings.public_banner_text || "";
      bannerStyle.value = res.settings.public_banner_style || "highlight";
      bannerBtnText.value = res.settings.public_banner_btn_text || "";
      bannerBtnUrl.value = res.settings.public_banner_btn_url || "";
    }
  } catch (err) {
    console.error("Fehler beim Laden der Public-Daten:", err);
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  currentTheme.value = document.documentElement.getAttribute("data-theme") || "dark";
  loadData();
});

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
.toktracker-public-app {
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
</style>
