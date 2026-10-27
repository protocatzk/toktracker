<template>
  <div v-if="isOpen" class="modal-backdrop" @click.self="close">
    <div class="modal-dialog modal-lg">
      <div class="modal-header">
        <div class="modal-title-wrap">
          <img
            :src="detailData?.streamer?.avatar_url || '/pictures/bot_avatar.jpg'"
            :alt="detailData?.streamer?.username"
            class="modal-avatar"
            @error="(e) => (e.target as HTMLImageElement).src = '/pictures/bot_avatar.jpg'"
          />
          <div>
            <h3 class="modal-title">{{ detailData?.streamer?.display_name || detailData?.streamer?.username || 'Streamer Detail' }}</h3>
            <p class="modal-subtitle">
              @{{ detailData?.streamer?.username }}
              {{ detailData?.streamer?.room_id ? ` · Room ${detailData?.streamer?.room_id}` : '' }}
            </p>
          </div>
        </div>
        <button type="button" class="close-btn" @click="close">&times;</button>
      </div>

      <div class="modal-body" v-if="isLoading">
        <div class="loading-state">
          <span class="loading-icon">⏳</span>
          <p>Lade Streamer-Details...</p>
        </div>
      </div>

      <div class="modal-body" v-else-if="detailData">
        <!-- Schnell-Übersicht Karten -->
        <div class="metrics-grid-compact">
          <div class="compact-card">
            <div class="compact-label">NETTO EUR</div>
            <div class="compact-val text-emerald">{{ formatEUR(detailData.summary?.eur_net) }}</div>
          </div>
          <div class="compact-card">
            <div class="compact-label">NETTO USD</div>
            <div class="compact-val">{{ formatUSD(detailData.summary?.usd_net) }}</div>
          </div>
          <div class="compact-card">
            <div class="compact-label">GESAMT COINS</div>
            <div class="compact-val text-cyan">{{ formatNumber(detailData.summary?.total_coins) }}</div>
          </div>
          <div class="compact-card">
            <div class="compact-label">BRUTTO EUR</div>
            <div class="compact-val">{{ formatEUR(detailData.summary?.eur_gross) }}</div>
          </div>
        </div>

        <!-- Geschenke Aufschlüsselung -->
        <div class="section-title-wrap">
          <h4>Erfasste Geschenke (Top Gifts)</h4>
        </div>
        <div class="table-responsive modal-table-wrap">
          <table class="modal-table">
            <thead>
              <tr>
                <th>GESCHENK</th>
                <th class="num-col">EINZELWERT</th>
                <th class="num-col">ANZAHL</th>
                <th class="num-col">GESAMT (COINS)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!detailData.gift_breakdown || detailData.gift_breakdown.length === 0">
                <td colspan="4" class="empty-text">Keine Geschenke im Zeitraum aufgezeichnet.</td>
              </tr>
              <tr v-for="(g, idx) in detailData.gift_breakdown" :key="idx">
                <td><strong class="gift-name">🎁 {{ g.gift_name }}</strong></td>
                <td class="num-col muted">{{ formatNumber(g.diamond_count) }}</td>
                <td class="num-col">{{ formatNumber(g.total_quantity || g.count || g.events_count || 1) }}x</td>
                <td class="num-col font-bold text-cyan">{{ formatNumber(g.total_coins) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Sessions Aufschlüsselung -->
        <div class="section-title-wrap" style="margin-top: 20px;">
          <h4>Kürzliche Stream-Sessions</h4>
        </div>
        <div class="table-responsive modal-table-wrap">
          <table class="modal-table">
            <thead>
              <tr>
                <th>SESSION ID</th>
                <th>STARTZEIT</th>
                <th>ENDE</th>
                <th class="num-col">PEAK VIEWERS</th>
                <th class="num-col">COINS GESAMMELT</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="sessionList.length === 0">
                <td colspan="5" class="empty-text">Keine beendeten Sessions erfasst.</td>
              </tr>
              <tr v-for="sess in sessionList" :key="sess.id">
                <td class="muted">#{{ sess.id }}</td>
                <td>{{ sess.start_time || '-' }}</td>
                <td>{{ sess.end_time || 'Aktiv' }}</td>
                <td class="num-col font-bold text-red">{{ formatNumber(sess.peak_viewers || 0) }}</td>
                <td class="num-col font-bold text-cyan">{{ formatNumber(sess.diamonds_collected || sess.session_coins || 0) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="modal-footer">
        <button type="button" class="btn-close" @click="close">Schließen</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { api } from "../../services/api";
import { formatEUR, formatUSD, formatNumber } from "../../utils/formatters";
import type { StreamerDetailResponse } from "../../types";

const props = defineProps<{
  streamerId: number | null;
  period?: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const isOpen = ref(false);
const isLoading = ref(false);
const detailData = ref<StreamerDetailResponse | null>(null);

const sessionList = computed(() => {
  if (!detailData.value) return [];
  return detailData.value.sessions || detailData.value.recent_sessions || [];
});

watch(
  () => props.streamerId,
  async (newId) => {
    if (newId) {
      isOpen.value = true;
      isLoading.value = true;
      try {
        detailData.value = await api.getStreamerDetails(newId, props.period || "24h");
      } catch (err) {
        console.error("Fehler beim Laden der Details:", err);
      } finally {
        isLoading.value = false;
      }
    } else {
      isOpen.value = false;
      detailData.value = null;
    }
  }
);

function close() {
  isOpen.value = false;
  emit("close");
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1050;
  padding: 16px;
}

.modal-dialog {
  background: #0f1523;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  width: 100%;
  max-width: 820px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 24px rgba(56, 189, 248, 0.15);
  overflow: hidden;
}

.modal-header {
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.02);
}

.modal-title-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
}

.modal-avatar {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  object-fit: cover;
  border: 1px solid rgba(56, 189, 248, 0.3);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.modal-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 18px;
  font-weight: 800;
  color: #ffffff;
  margin: 0;
  line-height: 1.2;
}

.modal-subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin: 2px 0 0;
}

.close-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  font-size: 20px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  line-height: 1;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.modal-body::-webkit-scrollbar,
.modal-table-wrap::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.modal-body::-webkit-scrollbar-track,
.modal-table-wrap::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
}

.modal-body::-webkit-scrollbar-thumb,
.modal-table-wrap::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.16);
  border-radius: 4px;
}

.modal-body::-webkit-scrollbar-thumb:hover,
.modal-table-wrap::-webkit-scrollbar-thumb:hover {
  background: rgba(56, 189, 248, 0.45);
}

.metrics-grid-compact {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

@media (max-width: 640px) {
  .metrics-grid-compact {
    grid-template-columns: repeat(2, 1fr);
  }
}

.compact-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.compact-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: #94a3b8;
  text-transform: uppercase;
}

.compact-val {
  font-size: 20px;
  font-weight: 800;
  color: #ffffff;
  font-variant-numeric: tabular-nums;
}

.section-title-wrap {
  margin-bottom: 12px;
}

.section-title-wrap h4 {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #cbd5e1;
  margin: 0;
}

.modal-table-wrap {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  overflow-y: auto;
  overflow-x: auto;
  max-height: 280px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.modal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.modal-table th {
  position: sticky;
  top: 0;
  z-index: 5;
  background: #121929;
  color: #94a3b8;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  text-align: left;
}

.modal-table td {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.gift-name {
  color: #ffffff;
}

.text-emerald {
  color: #34d399;
}

.text-cyan {
  color: #38bdf8;
}

.text-red {
  color: #f87171;
}

.num-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty-text {
  text-align: center;
  color: #94a3b8;
  padding: 24px 14px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px;
  color: #94a3b8;
}

.loading-icon {
  font-size: 32px;
}

.modal-footer {
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  text-align: right;
  background: rgba(255, 255, 255, 0.02);
}

.btn-close {
  padding: 8px 18px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #f1f5f9;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}
</style>
