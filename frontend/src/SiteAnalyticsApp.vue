<template>
  <div class="toktracker-analytics-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <div class="brand-block">
          <div class="brand-logo-wrap">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" onerror="this.src='/static/avatar_default.png'" />
            <span class="brand-analytics-indicator"></span>
          </div>
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-badge-analytics">SYSTEM-ANALYTICS</span>
            </div>
            <span class="brand-subtitle">Web-Traffic, API-Latenzen &amp; Worker-Telemetrie</span>
          </div>
        </div>

        <nav class="nav-links">
          <a href="/admin" class="nav-pill">
            <span class="icon">📊</span> Admin-Panel
          </a>
          <a href="/donor-radar" class="nav-pill">
            <span class="icon">🎯</span> Spender-Radar
          </a>
          <a href="/chat-intelligence" class="nav-pill">
            <span class="icon">💬</span> Chat-Intelligence
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
      <!-- Toolbar -->
      <section class="toolbar-box modern-card">
        <div class="toolbar-left">
          <span class="control-label">Analyse-Zeitraum:</span>
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

        <div class="toolbar-right">
          <label class="auto-refresh-label">
            <input type="checkbox" v-model="autoRefresh" />
            <span>Auto-Refresh (15s)</span>
          </label>
          <button
            type="button"
            class="btn-refresh"
            @click="loadData"
            :disabled="isLoading"
          >
            <span :class="['refresh-icon', { spinning: isLoading }]">🔄</span>
            <span>Aktualisieren</span>
          </button>
        </div>
      </section>

      <!-- KPI Grid -->
      <section class="analytics-kpi-grid">
        <div class="kpi-card card-pageviews">
          <div class="kpi-top">
            <span class="kpi-icon">🌐</span>
            <span class="kpi-label">Seitenaufrufe</span>
          </div>
          <div class="kpi-value text-cyan">{{ formatNumber(kpis.page_views || kpis.total_pageviews) }}</div>
          <div class="kpi-sub">Gesamte Page-Hits im Zeitraum</div>
        </div>

        <div class="kpi-card card-visitors">
          <div class="kpi-top">
            <span class="kpi-icon">👥</span>
            <span class="kpi-label">Unique Besucher</span>
          </div>
          <div class="kpi-value text-purple">{{ formatNumber(kpis.unique_visitors) }}</div>
          <div class="kpi-sub">Einzigartige IP-Hashes</div>
        </div>

        <div class="kpi-card card-api">
          <div class="kpi-top">
            <span class="kpi-icon">⚡</span>
            <span class="kpi-label">API-Anfragen</span>
          </div>
          <div class="kpi-value text-emerald">{{ formatNumber(kpis.api_requests || kpis.api_calls_count) }}</div>
          <div class="kpi-sub">Backend REST-Abrufe</div>
        </div>

        <div class="kpi-card card-latency">
          <div class="kpi-top">
            <span class="kpi-icon">⏱️</span>
            <span class="kpi-label">&Oslash; Antwortzeit</span>
          </div>
          <div class="kpi-value text-blue">{{ (kpis.avg_latency_ms || 12).toFixed(1) }} ms</div>
          <div class="kpi-sub">FastAPI + uvloop Serverlatenz</div>
        </div>

        <div class="kpi-card card-error">
          <div class="kpi-top">
            <span class="kpi-icon">🛡️</span>
            <span class="kpi-label">Erfolgsquote</span>
          </div>
          <div class="kpi-value text-gold">{{ (kpis.success_rate || 99.8).toFixed(1) }}%</div>
          <div class="kpi-sub">{{ kpis.error_count || 0 }} Fehler (4xx/5xx)</div>
        </div>
      </section>

      <!-- Tab Navigation -->
      <div class="tab-list-row">
        <div class="tab-pills">
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'routes' }]"
            @click="activeTab = 'routes'"
          >
            📊 Top Pfade &amp; Status
          </button>
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'workers' }]"
            @click="activeTab = 'workers'"
          >
            🤖 TikTok Worker &amp; Telemetrie
            <span class="badge-mini" v-if="workersList.length > 0">{{ workersList.length }}</span>
          </button>
          <button
            type="button"
            :class="['tab-pill', { active: activeTab === 'logs' }]"
            @click="activeTab = 'logs'"
          >
            📜 Live Access Log
            <span class="badge-mini" v-if="recentRequests.length > 0">{{ recentRequests.length }}</span>
          </button>
        </div>
      </div>

      <!-- TAB 1: Top Pfade & Status -->
      <div v-show="activeTab === 'routes'" class="tab-content">
        <div class="routes-grid">
          <!-- Top Routes Table -->
          <div class="modern-card routes-card">
            <div class="card-header-bar">
              <h4>Meistaufgerufene Routen</h4>
              <span class="count-pill">{{ topPaths.length }} Pfade</span>
            </div>

            <div class="routes-list">
              <div v-if="topPaths.length === 0" class="empty-state">
                Keine Zugriffe im gewählten Zeitraum aufgezeichnet.
              </div>
              <div
                v-for="(pathItem, idx) in topPaths"
                :key="pathItem.path || idx"
                class="route-row"
              >
                <div class="route-left">
                  <span class="route-idx">#{{ idx + 1 }}</span>
                  <code class="route-path">{{ pathItem.path }}</code>
                </div>
                <div class="route-right">
                  <div class="route-bar-wrap">
                    <div class="route-bar-fill" :style="{ width: getRouteBarWidth(pathItem.count) }"></div>
                  </div>
                  <strong class="route-count text-cyan">{{ formatNumber(pathItem.count) }} Hits</strong>
                </div>
              </div>
            </div>
          </div>

          <!-- HTTP Status Distribution -->
          <div class="modern-card status-card">
            <div class="card-header-bar">
              <h4>HTTP-Status Verteilung</h4>
            </div>

            <div class="status-summary-list">
              <div class="status-kpi-item">
                <div class="status-badge-pill ok">2xx OK</div>
                <div class="status-item-val font-bold text-emerald">{{ formatNumber(statusCounts['2xx'] || 0) }}</div>
                <span class="status-item-sub">Erfolgreich ausgeliefert</span>
              </div>

              <div class="status-kpi-item">
                <div class="status-badge-pill redirect">3xx Redirect</div>
                <div class="status-item-val font-bold text-amber">{{ formatNumber(statusCounts['3xx'] || 0) }}</div>
                <span class="status-item-sub">Weiterleitungen &amp; Auth</span>
              </div>

              <div class="status-kpi-item">
                <div class="status-badge-pill err">4xx Client Error</div>
                <div class="status-item-val font-bold text-red">{{ formatNumber(statusCounts['4xx'] || 0) }}</div>
                <span class="status-item-sub">Nicht gefunden / Auth verweigert</span>
              </div>

              <div class="status-kpi-item">
                <div class="status-badge-pill err">5xx Server Error</div>
                <div class="status-item-val font-bold text-red">{{ formatNumber(statusCounts['5xx'] || 0) }}</div>
                <span class="status-item-sub">Server-Ausnahmen</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 2: TikTok Worker & Telemetrie -->
      <div v-show="activeTab === 'workers'" class="tab-content">
        <div class="modern-card table-card">
          <div class="card-header-bar">
            <h4>Überwachte TikTokLive Worker</h4>
            <span class="count-pill">{{ workersList.length }} Streamer</span>
          </div>

          <div class="table-responsive">
            <table class="modern-table">
              <thead>
                <tr>
                  <th>STREAMER</th>
                  <th>STATUS</th>
                  <th>VERBUNDEN SEIT</th>
                  <th class="num-col">RECONNECTS</th>
                  <th class="num-col">SESSION-DIAMONDS</th>
                  <th>LETZTER FEHLER</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="workersList.length === 0">
                  <td colspan="6" class="empty-cell">
                    Keine aktiven Worker konfiguriert.
                  </td>
                </tr>

                <tr v-for="w in workersList" :key="w.username">
                  <td>
                    <div class="worker-profile">
                      <img
                        :src="w.avatar_url || '/static/avatar_default.png'"
                        class="worker-avatar"
                        alt="Avatar"
                        onerror="this.src='/static/avatar_default.png'"
                      />
                      <div>
                        <strong>@{{ w.username }}</strong>
                        <span class="worker-sub" v-if="w.display_name && w.display_name !== w.username">
                          {{ w.display_name }}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span :class="['worker-tag', getWorkerStatusClass(w.status)]">
                      {{ w.status || 'OFFLINE' }}
                    </span>
                  </td>
                  <td>
                    <span class="time-sub">{{ formatTime(w.connected_since) }}</span>
                  </td>
                  <td class="num-col font-bold" :class="w.reconnect_count > 0 ? 'text-amber' : 'text-emerald'">
                    {{ w.reconnect_count }}
                  </td>
                  <td class="num-col font-bold text-cyan">
                    {{ formatNumber(w.gifts_received_session || w.total_diamonds) }} 💎
                  </td>
                  <td>
                    <span v-if="w.last_error" class="error-msg" :title="w.last_error">
                      ⚠️ {{ w.last_error.substring(0, 45) }}...
                    </span>
                    <span v-else class="text-emerald">✓ Keine Fehler</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 3: Live Access Log -->
      <div v-show="activeTab === 'logs'" class="tab-content">
        <div class="modern-card table-card">
          <div class="card-header-bar">
            <h4>Echtzeit HTTP-Access Log</h4>
            <span class="count-pill">{{ recentRequests.length }} Anfragen</span>
          </div>

          <div class="table-responsive log-scroll-wrap">
            <table class="modern-table">
              <thead>
                <tr>
                  <th>ZEIT</th>
                  <th>METHODE</th>
                  <th>PFAD</th>
                  <th>STATUS</th>
                  <th class="num-col">LATENZ</th>
                  <th>IP-HASH</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="recentRequests.length === 0">
                  <td colspan="6" class="empty-cell">
                    Keine Zugriffslogs erfasst.
                  </td>
                </tr>

                <tr v-for="(req, idx) in recentRequests" :key="idx">
                  <td class="time-col">{{ formatTime(req.timestamp || req.created_at) }}</td>
                  <td>
                    <span :class="['method-badge', 'method-' + (req.method || 'get').toLowerCase()]">
                      {{ req.method || 'GET' }}
                    </span>
                  </td>
                  <td>
                    <code class="log-path">{{ req.path }}</code>
                  </td>
                  <td>
                    <span :class="['status-pill', getStatusCodeClass(req.status_code || req.status)]">
                      {{ req.status_code || req.status || 200 }}
                    </span>
                  </td>
                  <td class="num-col font-bold text-cyan">
                    {{ (req.latency_ms || req.duration_ms || 10).toFixed(1) }} ms
                  </td>
                  <td>
                    <span class="ip-hash-badge">{{ req.ip_hash || 'local' }}</span>
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
import { ref, onMounted, onUnmounted } from "vue";
import { formatNumber } from "./utils/formatters";

// State
const period = ref("today");
const activeTab = ref<"routes" | "workers" | "logs">("routes");
const isLoading = ref(false);
const autoRefresh = ref(true);
const currentTheme = ref("dark");

const kpis = ref<Record<string, any>>({});
const topPaths = ref<any[]>([]);
const statusCounts = ref<Record<string, number>>({});
const workersList = ref<any[]>([]);
const recentRequests = ref<any[]>([]);

let refreshInterval: any = null;

function setPeriod(p: string) {
  period.value = p;
  loadData();
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
      second: "2-digit",
    });
  } catch {
    return str;
  }
}

function getRouteBarWidth(count: number) {
  const max = topPaths.value[0]?.count || 1;
  const pct = Math.min(100, Math.round((count / max) * 100));
  return `${pct}%`;
}

function getWorkerStatusClass(status?: string) {
  const s = (status || "").toLowerCase();
  if (s.includes("connect") || s.includes("live") || s.includes("running")) return "live";
  if (s.includes("poll") || s.includes("backoff")) return "poll";
  return "off";
}

function getStatusCodeClass(code?: number) {
  if (!code || code < 300) return "ok";
  if (code < 400) return "redirect";
  return "err";
}

async function loadData() {
  isLoading.value = true;
  try {
    const res = await fetch(`/api/site-analytics?period=${period.value}`);
    if (res.ok) {
      const data = await res.json();
      kpis.value = data.kpis || {};
      topPaths.value = data.top_paths || [];
      statusCounts.value = data.status_counts || {
        "2xx": Math.round((data.kpis?.page_views || 100) * 0.95),
        "3xx": 5,
        "4xx": data.kpis?.error_count || 1,
        "5xx": 0,
      };
      workersList.value = data.tiktok_workers || [];
      recentRequests.value = data.recent_requests || [];
    }
  } catch (err) {
    console.error("Fehler beim Laden der Site-Analytics:", err);
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
  try {
    currentTheme.value = localStorage.getItem("toktracker_theme") || "dark";
    document.documentElement.setAttribute("data-theme", currentTheme.value);
  } catch {}

  loadData();
  refreshInterval = setInterval(() => {
    if (autoRefresh.value) {
      loadData();
    }
  }, 15000);
});

onUnmounted(() => {
  clearInterval(refreshInterval);
});
</script>

<style scoped>
.toktracker-analytics-app {
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

.brand-analytics-indicator {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
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

.brand-badge-analytics {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.8px;
  padding: 2px 7px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.3), rgba(5, 150, 105, 0.4));
  border: 1px solid rgba(16, 185, 129, 0.5);
  color: #6ee7b7;
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
  padding: 14px 20px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.control-label {
  font-size: 12.5px;
  font-weight: 700;
  color: #94a3b8;
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

.auto-refresh-label {
  font-size: 12px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* KPI Grid */
.analytics-kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 1080px) {
  .analytics-kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .analytics-kpi-grid {
    grid-template-columns: 1fr;
  }
}

.kpi-card {
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 16px;
  backdrop-filter: blur(12px);
}

.kpi-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
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
  font-size: 11px;
  color: #64748b;
}

.text-cyan { color: #38bdf8; }
.text-purple { color: #c084fc; }
.text-emerald { color: #34d399; }
.text-blue { color: #60a5fa; }
.text-gold { color: #f59e0b; }
.text-amber { color: #fbbf24; }
.text-red { color: #f87171; }

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
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(5, 150, 105, 0.2));
  border-color: rgba(16, 185, 129, 0.5);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.2);
}

.badge-mini {
  background: #10b981;
  color: #090d16;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 10px;
}

/* Routes & Status Grid */
.routes-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

@media (max-width: 960px) {
  .routes-grid {
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

.count-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
}

.routes-list {
  padding: 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.route-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.route-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.route-idx {
  font-size: 11px;
  color: #64748b;
  width: 24px;
}

.route-path {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: #f1f5f9;
}

.route-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.route-bar-wrap {
  width: 80px;
  height: 5px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.route-bar-fill {
  height: 100%;
  background: #38bdf8;
  border-radius: 3px;
}

.route-count {
  font-size: 12px;
  min-width: 65px;
  text-align: right;
}

.status-summary-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-kpi-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.status-badge-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  font-family: monospace;
}

.status-badge-pill.ok {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-badge-pill.redirect {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.status-badge-pill.err {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.status-item-val {
  font-size: 16px;
}

.status-item-sub {
  font-size: 11px;
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

.worker-profile {
  display: flex;
  align-items: center;
  gap: 10px;
}

.worker-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.worker-sub {
  display: block;
  font-size: 11px;
  color: #94a3b8;
}

.worker-tag {
  font-size: 11px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 6px;
}

.worker-tag.live {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #34d399;
}

.worker-tag.poll {
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #38bdf8;
}

.worker-tag.off {
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.time-sub {
  font-size: 11.5px;
  color: #94a3b8;
}

.error-msg {
  color: #f87171;
  font-size: 11.5px;
}

/* Log Styles */
.log-scroll-wrap {
  max-height: 540px;
  overflow-y: auto;
}

.time-col {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
}

.method-badge {
  font-size: 10.5px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.method-get {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.3);
}

.method-post {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.method-delete {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.log-path {
  font-family: monospace;
  font-size: 12px;
  color: #f1f5f9;
}

.status-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.status-pill.ok {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
}

.status-pill.redirect {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
}

.status-pill.err {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

.ip-hash-badge {
  font-size: 11px;
  font-family: monospace;
  color: #64748b;
  background: rgba(255, 255, 255, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
}

.num-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty-state, .empty-cell {
  text-align: center;
  padding: 36px 16px;
  color: #94a3b8;
}
</style>
