<template>
  <div v-if="isOpen" class="modal-backdrop" @click.self="close">
    <div class="modal-dialog modal-lg">
      <div class="modal-header">
        <div>
          <h3>{{ detailData?.streamer?.display_name || detailData?.streamer?.username || 'Streamer Detail' }}</h3>
          <p class="muted">
            @{{ detailData?.streamer?.username }}
            {{ detailData?.streamer?.room_id ? ` · Room ${detailData?.streamer?.room_id}` : '' }}
          </p>
        </div>
        <button type="button" class="close-btn" @click="close">&times;</button>
      </div>

      <div class="modal-body" v-if="isLoading">
        <div class="muted text-center" style="padding: 32px;">Lade Streamer-Details...</div>
      </div>

      <div class="modal-body" v-else-if="detailData">
        <!-- Schnell-Übersicht Karten -->
        <div class="metrics-grid-compact" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:12px; margin-bottom:20px;">
          <div class="card compact">
            <div class="muted" style="font-size:11px;">NETTO EUR</div>
            <strong>{{ formatEUR(detailData.summary?.eur_net) }}</strong>
          </div>
          <div class="card compact">
            <div class="muted" style="font-size:11px;">NETTO USD</div>
            <strong>{{ formatUSD(detailData.summary?.usd_net) }}</strong>
          </div>
          <div class="card compact">
            <div class="muted" style="font-size:11px;">GESAMT COINS</div>
            <strong>{{ formatNumber(detailData.summary?.total_coins) }}</strong>
          </div>
          <div class="card compact">
            <div class="muted" style="font-size:11px;">BRUTTO EUR</div>
            <strong>{{ formatEUR(detailData.summary?.eur_gross) }}</strong>
          </div>
        </div>

        <!-- Geschenke Aufschlüsselung -->
        <h4>ERFASSTE GESCHENKE (TOP GIFTS)</h4>
        <div class="table-responsive" style="max-height: 220px; overflow-y:auto; margin-bottom: 20px;">
          <table class="data-table sm">
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
                <td colspan="4" class="muted text-center">Keine Geschenke im Zeitraum aufgezeichnet.</td>
              </tr>
              <tr v-for="(g, idx) in detailData.gift_breakdown" :key="idx">
                <td><strong>{{ g.gift_name }}</strong></td>
                <td class="num-col">{{ formatNumber(g.diamond_count) }}</td>
                <td class="num-col">{{ formatNumber(g.count) }}x</td>
                <td class="num-col"><strong>{{ formatNumber(g.total_coins) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Stream Sessions -->
        <h4>LETZTE LIVE-SITZUNGEN</h4>
        <div class="table-responsive" style="max-height: 180px; overflow-y:auto;">
          <table class="data-table sm">
            <thead>
              <tr>
                <th>BEGINN</th>
                <th>ENDE</th>
                <th class="num-col">PEAK ZUSCHAUER</th>
                <th class="num-col">DIAMONDS</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!detailData.sessions || detailData.sessions.length === 0">
                <td colspan="4" class="muted text-center">Keine Sitzungsdaten vorhanden.</td>
              </tr>
              <tr v-for="s in detailData.sessions" :key="s.id">
                <td class="mono" style="font-size:11px;">{{ formatDateTime(s.start_time) }}</td>
                <td class="mono" style="font-size:11px;">{{ s.end_time ? formatDateTime(s.end_time) : 'Noch LIVE' }}</td>
                <td class="num-col">{{ formatNumber(s.peak_viewers) }}</td>
                <td class="num-col"><strong>{{ formatNumber(s.diamonds_collected) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="modal-footer">
        <button type="button" class="sm" @click="close">Schließen</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../../services/api";
import { formatEUR, formatUSD, formatNumber, formatDateTime } from "../../utils/formatters";

const props = defineProps<{
  streamerId: number | null;
  period?: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const isOpen = ref(false);
const isLoading = ref(false);
const detailData = ref<any>(null);

watch(
  () => props.streamerId,
  async (id) => {
    if (id) {
      isOpen.value = true;
      isLoading.value = true;
      try {
        detailData.value = await api.getStreamerDetail(id, props.period || "all");
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
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1050;
}
.modal-dialog {
  background: var(--bg-card, #131722);
  border: 1px solid var(--border-subtle, #2a2e39);
  border-radius: 8px;
  width: 90%;
  max-width: 780px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6);
}
.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle, #2a2e39);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.close-btn {
  background: none;
  border: none;
  color: var(--text-muted, #94a3b8);
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
}
.modal-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border-subtle, #2a2e39);
  text-align: right;
}
</style>
