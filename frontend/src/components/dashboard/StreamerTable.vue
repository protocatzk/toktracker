<template>
  <div class="streamer-section">
    <!-- Streamer hinzufügen Formular -->
    <div class="modern-card add-streamer-card">
      <div class="card-header">
        <div class="header-left">
          <span class="header-icon">➕</span>
          <div>
            <h3 class="card-title">Streamer Überwachen</h3>
            <p class="card-subtitle">Fügt ein TikTok-Profil zum Live-Radar hinzu und startet die Hintergrund-Überwachung.</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="handleAddStreamer" class="form-row-modern">
        <div class="input-wrap">
          <input
            v-model="newUsername"
            type="text"
            placeholder="TikTok Benutzername (z.B. user123)"
            required
            class="modern-input"
          />
        </div>
        <div class="input-wrap">
          <input
            v-model="newDisplayName"
            type="text"
            placeholder="Anzeigename (optional)"
            class="modern-input"
          />
        </div>
        <label class="modern-checkbox">
          <input v-model="newStartWorker" type="checkbox" />
          <span>Worker sofort starten</span>
        </label>
        <label class="modern-checkbox">
          <input v-model="newAutoMonitor" type="checkbox" />
          <span>Auto-Poll / Reconnect</span>
        </label>
        <button type="submit" class="btn-primary" :disabled="isSubmitting">
          {{ isSubmitting ? 'Wird hinzugefügt...' : 'Streamer hinzufügen' }}
        </button>
      </form>
    </div>

    <!-- Tabelle mit Filtern -->
    <div class="modern-card">
      <div class="card-header-bar">
        <div class="header-title-group">
          <h3 class="card-title">Überwachte Streamer &amp; Einnahmen</h3>
          <span class="live-pill" v-if="store.liveStreamersCount > 0">
            <span class="live-dot-pulse"></span>
            {{ store.liveStreamersCount }} LIVE
          </span>
        </div>
        <div class="header-controls">
          <div class="search-input-wrapper">
            <span class="search-icon">🔍</span>
            <input
              v-model="store.streamerFilter"
              type="search"
              placeholder="Tabelle durchsuchen..."
              class="modern-search"
            />
          </div>
          <span class="count-badge">
            {{ store.filteredStreamers.length }} von {{ store.streamers.length }}
          </span>
        </div>
      </div>

      <div class="table-responsive">
        <table class="modern-table">
          <thead>
            <tr>
              <th class="hide-sm" style="width: 50px;">ID</th>
              <th>STREAMER</th>
              <th class="hide-sm">STATUS / WORKER</th>
              <th class="num-col hide-md">ZUSCHAUER</th>
              <th class="num-col">COINS</th>
              <th class="num-col">NETTO (EUR)</th>
              <th class="num-col hide-sm">NETTO (USD)</th>
              <th class="hide-sm">TOP GESCHENK</th>
              <th style="text-align: right;">AKTIONEN</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="store.filteredStreamers.length === 0">
              <td colspan="9" class="empty-cell">
                <div class="empty-state">
                  <span class="empty-icon">⏳</span>
                  <p>{{ store.isLoading ? 'Lade Daten...' : 'Keine passenden Streamer gefunden.' }}</p>
                </div>
              </td>
            </tr>
            <tr
              v-for="s in store.filteredStreamers"
              :key="s.id"
              class="streamer-row"
            >
              <td class="id-col hide-sm">#{{ s.id }}</td>
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
                    <a href="#" @click.prevent="$emit('selectStreamer', s.id)" class="streamer-display-name">
                      {{ s.display_name || s.username }}
                    </a>
                    <span class="streamer-handle">
                      @{{ s.username }}{{ s.room_id ? ` · Room ${s.room_id}` : '' }}
                    </span>
                  </div>
                </div>
              </td>
              <td class="hide-sm">
                <div class="status-stack">
                  <StatusTag
                    :state="s.worker_diagnostics?.state || (s.is_live ? 'live' : 'stopped')"
                    :is-live="Boolean(s.is_live)"
                  >
                    {{ (s.worker_diagnostics?.state || (s.is_live ? 'live' : 'stopped')).toUpperCase() }}
                  </StatusTag>
                  <span
                    v-if="s.auto_monitor || s.is_tracking"
                    class="auto-start-badge"
                    title="Automatischer Start aktiv"
                  >
                    AUTO
                  </span>
                </div>
              </td>
              <td class="num-col hide-md">
                <span class="viewer-count" v-if="s.is_live">
                  <span class="live-pulse-dot"></span>
                  {{ formatNumber(s.current_viewers || 0) }}
                </span>
                <span v-else class="muted-dash">-</span>
                <div class="sub-muted">
                  {{ formatNumber(s.follower_count || 0) }} Follower
                </div>
              </td>
              <td class="num-col coins-col">
                {{ formatNumber(s.total_coins) }}
                <div class="sub-muted">
                  {{ formatNumber(s.total_gifts_sent || 0) }} Gifts
                </div>
              </td>
              <td class="num-col revenue-eur">
                {{ formatEUR(s.eur_net) }}
              </td>
              <td class="num-col hide-sm revenue-usd">
                {{ formatUSD(s.usd_net) }}
              </td>
              <td class="hide-sm">
                <div v-if="s.top_gift" class="top-gift-badge">
                  🎁 {{ s.top_gift.gift_name }}
                  <span class="gift-coins">({{ formatNumber(s.top_gift.coins) }})</span>
                </div>
                <div v-else class="muted-dash">-</div>
              </td>
              <td style="text-align: right;">
                <div class="action-buttons">
                  <button
                    type="button"
                    :class="['btn-action', s.is_tracking_active ? 'btn-stop' : 'btn-start']"
                    @click="handleToggleWorker(s.id)"
                    :title="s.is_tracking_active ? 'Worker stoppen' : 'Worker starten'"
                  >
                    {{ s.is_tracking_active ? 'Stop' : 'Start' }}
                  </button>
                  <button
                    type="button"
                    class="btn-action btn-details"
                    @click="$emit('selectStreamer', s.id)"
                  >
                    Details
                  </button>
                  <button
                    type="button"
                    class="btn-action btn-sync"
                    @click="store.refreshStreamer(s.id)"
                    title="TikTok Profil aktualisieren"
                  >
                    Sync
                  </button>
                  <button
                    type="button"
                    class="btn-action btn-delete"
                    @click="handleDeleteStreamer(s.id, s.username)"
                    title="Streamer entfernen"
                  >
                    ✕
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useDashboardStore } from "../../stores/dashboardStore";
import { formatEUR, formatUSD, formatNumber } from "../../utils/formatters";
import StatusTag from "../common/StatusTag.vue";

defineEmits<{
  (e: "selectStreamer", streamerId: number): void;
}>();

const store = useDashboardStore();

const newUsername = ref("");
const newDisplayName = ref("");
const newStartWorker = ref(true);
const newAutoMonitor = ref(true);
const isSubmitting = ref(false);

async function handleAddStreamer() {
  if (!newUsername.value.trim()) return;
  isSubmitting.value = true;
  try {
    await store.addStreamer(
      newUsername.value.trim(),
      newDisplayName.value.trim() || undefined,
      newStartWorker.value,
      newAutoMonitor.value
    );
    newUsername.value = "";
    newDisplayName.value = "";
  } finally {
    isSubmitting.value = false;
  }
}

async function handleToggleWorker(streamerId: number) {
  await store.toggleWorker(streamerId);
}

async function handleDeleteStreamer(streamerId: number, username: string) {
  if (confirm(`Streamer @${username} wirklich entfernen?`)) {
    await store.deleteStreamer(streamerId);
  }
}
</script>

<style scoped>
.modern-card {
  background: var(--bg-surface, #0f1523);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 32px -4px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  margin-bottom: 24px;
}

.add-streamer-card {
  padding: 22px 24px;
}

.card-header {
  margin-bottom: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  font-size: 20px;
  background: rgba(56, 189, 248, 0.12);
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px solid rgba(56, 189, 248, 0.25);
}

.card-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 16px;
  font-weight: 800;
  color: #ffffff;
  margin: 0;
  letter-spacing: -0.2px;
}

.card-subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin: 2px 0 0;
}

.form-row-modern {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}

.input-wrap {
  flex: 1;
  min-width: 200px;
}

.modern-input {
  width: 100%;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 9px 14px;
  color: #f1f5f9;
  font-size: 13px;
  outline: none;
  transition: all 0.2s ease;
}

.modern-input:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

.modern-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: #cbd5e1;
  cursor: pointer;
  user-select: none;
}

.modern-checkbox input {
  accent-color: #38bdf8;
  cursor: pointer;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  padding: 9px 18px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%);
  color: #090d16;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  box-shadow: 0 4px 14px rgba(14, 165, 233, 0.3);
  transition: all 0.2s ease;
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
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
  gap: 12px;
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

.header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
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
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 8px 14px 8px 34px;
  color: #f1f5f9;
  font-size: 13px;
  width: 220px;
  outline: none;
  transition: all 0.2s ease;
}

.modern-search:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
  width: 260px;
}

.count-badge {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

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

.streamer-row:hover {
  background: rgba(56, 189, 248, 0.04);
}

.id-col {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
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
  text-decoration: none;
  line-height: 1.2;
}

.streamer-display-name:hover {
  color: #38bdf8;
}

.streamer-handle {
  font-size: 12px;
  color: #94a3b8;
}

.status-stack {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.auto-start-badge {
  font-size: 9.5px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.3);
  color: #38bdf8;
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

.sub-muted {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
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

.action-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.btn-action {
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #f1f5f9;
  transition: all 0.15s ease;
}

.btn-action:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}

.btn-start {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.35);
  color: #34d399;
}

.btn-start:hover {
  background: rgba(16, 185, 129, 0.25);
  border-color: rgba(16, 185, 129, 0.5);
}

.btn-stop {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}

.btn-stop:hover {
  background: rgba(245, 158, 11, 0.25);
}

.btn-details {
  background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.3);
  color: #38bdf8;
}

.btn-details:hover {
  background: rgba(56, 189, 248, 0.22);
}

.btn-delete {
  color: #f87171;
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.5);
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

@media (max-width: 768px) {
  .hide-sm {
    display: none !important;
  }
}

@media (max-width: 992px) {
  .hide-md {
    display: none !important;
  }
}
</style>
