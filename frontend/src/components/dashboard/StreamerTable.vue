<template>
  <div class="streamer-section">
    <!-- Streamer hinzufügen Formular -->
    <div class="card add-streamer-card" style="margin-bottom: 20px;">
      <div class="card-header">
        <h3>STREAMER ÜBERWACHEN</h3>
        <p class="muted">Fügt ein TikTok-Profil hinzu und startet optional den Hintergrund-Worker.</p>
      </div>
      <form @submit.prevent="handleAddStreamer" class="form-row-compact">
        <input
          v-model="newUsername"
          type="text"
          placeholder="TikTok Benutzername"
          required
          style="max-width: 200px;"
        />
        <input
          v-model="newDisplayName"
          type="text"
          placeholder="Anzeigename (optional)"
          style="max-width: 200px;"
        />
        <label class="checkbox-label">
          <input v-model="newStartWorker" type="checkbox" /> Worker direkt starten
        </label>
        <label class="checkbox-label">
          <input v-model="newAutoMonitor" type="checkbox" /> Auto-Poll / Reconnect
        </label>
        <button type="submit" class="primary" :disabled="isSubmitting">
          Streamer hinzufügen
        </button>
      </form>
    </div>

    <!-- Tabelle mit Filtern -->
    <div class="card">
      <div class="card-header-bar">
        <h3>ÜBERWACHTE STREAMER &amp; EINNAHMEN</h3>
        <div class="header-controls">
          <input
            v-model="store.streamerFilter"
            type="search"
            placeholder="Tabelle filtern..."
            class="sm-input"
          />
          <span class="mono muted">
            {{ store.filteredStreamers.length }} von {{ store.streamers.length }} Streamern
          </span>
        </div>
      </div>

      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th class="hide-sm">ID</th>
              <th>STREAMER</th>
              <th class="hide-sm">WORKER / LIVE-STATUS</th>
              <th class="num-col hide-md">ZUSCHAUER</th>
              <th class="num-col">COINS</th>
              <th class="num-col">NETTO (EUR)</th>
              <th class="num-col hide-sm">NETTO (USD)</th>
              <th class="num-col hide-md">BRUTTO (EUR)</th>
              <th class="hide-sm">TOP GIFT / SPENDER</th>
              <th>AKTIONEN</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="store.filteredStreamers.length === 0">
              <td colspan="10" class="muted text-center" style="padding: 24px;">
                {{ store.isLoading ? 'Lade Daten...' : 'Keine passenden Streamer gefunden.' }}
              </td>
            </tr>
            <tr v-for="s in store.filteredStreamers" :key="s.id">
              <td class="mono muted hide-sm">#{{ s.id }}</td>
              <td>
                <strong>
                  <a href="#" @click.prevent="$emit('selectStreamer', s.id)">
                    {{ s.display_name || s.username }}
                  </a>
                </strong>
                <div class="mono muted">
                  @{{ s.username }}{{ s.room_id ? ` · Room ${s.room_id}` : '' }}
                </div>
              </td>
              <td class="hide-sm">
                <div style="display:flex; gap:4px; flex-wrap:wrap; align-items:center;">
                  <StatusTag
                    :state="s.worker_diagnostics?.state || (s.is_live ? 'live' : 'stopped')"
                    :is-live="Boolean(s.is_live)"
                  >
                    {{ (s.worker_diagnostics?.state || (s.is_live ? 'live' : 'stopped')).toUpperCase() }}
                  </StatusTag>
                  <span
                    v-if="s.auto_monitor || s.is_tracking"
                    class="status-tag live"
                    title="Automatischer Start aktiv"
                  >
                    AUTO-START
                  </span>
                  <span v-else class="status-tag" title="Manueller Modus">MANUELL</span>
                </div>
                <div class="mono muted" style="margin-top:3px; font-size:11px;">
                  {{ s.monitor_status || '' }}
                </div>
              </td>
              <td class="num-col hide-md">
                <strong>{{ formatNumber(s.current_viewers || 0) }}</strong>
                <div class="muted" style="font-size:11px;">
                  {{ formatNumber(s.follower_count || 0) }} Follower
                </div>
              </td>
              <td class="num-col">
                <strong>{{ formatNumber(s.total_coins) }}</strong>
                <div class="muted" style="font-size:11px;">
                  {{ formatNumber(s.total_gifts_sent || 0) }} Gifts / {{ s.unique_gifters || 0 }} Gifter
                </div>
              </td>
              <td class="num-col"><strong>{{ formatEUR(s.eur_net) }}</strong></td>
              <td class="num-col hide-sm">{{ formatUSD(s.usd_net) }}</td>
              <td class="num-col hide-md">{{ formatEUR(s.eur_gross) }}</td>
              <td class="mono hide-sm" style="font-size:11px;">
                <div>
                  Gift: {{ s.top_gift ? `${s.top_gift.gift_name} (${formatNumber(s.top_gift.coins)})` : '-' }}
                </div>
                <div class="muted">
                  Spender: {{ s.top_gifter ? `@${s.top_gifter.sender_username} (${formatNumber(s.top_gifter.coins)})` : '-' }}
                </div>
              </td>
              <td>
                <div class="action-group">
                  <button
                    type="button"
                    class="sm"
                    @click="handleToggleWorker(s.id)"
                  >
                    {{ s.is_tracking_active ? 'Stop' : 'Start' }}
                  </button>
                  <button
                    type="button"
                    class="sm"
                    @click="$emit('selectStreamer', s.id)"
                  >
                    Details
                  </button>
                  <button
                    type="button"
                    class="sm"
                    @click="store.refreshStreamer(s.id)"
                    title="TikTok Profil aktualisieren"
                  >
                    Sync
                  </button>
                  <a
                    class="btn-link sm mono hide-sm"
                    :href="`/api/v1/streamers/${encodeURIComponent(s.username)}/report?hours=24`"
                    target="_blank"
                  >
                    JSON
                  </a>
                  <button
                    type="button"
                    class="sm danger"
                    @click="handleDeleteStreamer(s.id, s.username)"
                  >
                    X
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
