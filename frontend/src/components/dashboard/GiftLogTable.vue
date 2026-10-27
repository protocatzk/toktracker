<template>
  <div class="modern-card">
    <div class="card-header-bar">
      <div class="header-title-group">
        <h3 class="card-title">Letzte Gift-Transaktionen (Live-Log)</h3>
      </div>
      <div class="header-controls">
        <div class="search-input-wrapper">
          <span class="search-icon">🔍</span>
          <input
            v-model="store.giftFilter"
            type="search"
            placeholder="Transaktionen filtern..."
            class="modern-search"
          />
        </div>
        <span class="count-badge">
          {{ store.filteredGifts.length }} von {{ store.recentGifts.length }}
        </span>
      </div>
    </div>

    <div class="table-responsive">
      <table class="modern-table">
        <thead>
          <tr>
            <th>ZEITPUNKT</th>
            <th>STREAMER</th>
            <th>ABSENDER / SPENDER</th>
            <th class="hide-sm">GESCHENK</th>
            <th class="num-col">COINS</th>
            <th class="num-col">NETTO (EUR)</th>
            <th class="num-col hide-sm">NETTO (USD)</th>
            <th class="hide-sm">QUELLE</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="store.filteredGifts.length === 0">
            <td colspan="8" class="empty-cell">
              <div class="empty-state">
                <span class="empty-icon">🎁</span>
                <p>{{ store.isLoading ? 'Lade Daten...' : 'Keine Transaktionen für diesen Zeitraum vorhanden.' }}</p>
              </div>
            </td>
          </tr>
          <tr v-for="g in store.filteredGifts" :key="g.id" class="gift-row">
            <td class="timestamp-col">
              {{ (g.created_at || g.timestamp || '').replace('T', ' ').substring(0, 19) }}
            </td>
            <td>
              <span class="streamer-tag">@{{ g.streamer_username }}</span>
            </td>
            <td>
              <div class="sender-info">
                <span class="sender-name">{{ g.sender_nickname || g.sender_username }}</span>
                <span class="sender-handle hide-sm">(@{{ g.sender_username }})</span>
                <span v-if="g.is_super_fan" class="super-fan-badge">
                  ⭐ FAN
                </span>
              </div>
            </td>
            <td class="hide-sm">
              <span class="gift-pill">
                🎁 <strong>{{ g.repeat_count }}x</strong> {{ g.gift_name }}
              </span>
            </td>
            <td class="num-col font-bold text-cyan">
              {{ formatNumber(g.total_coins) }}
            </td>
            <td class="num-col font-bold text-emerald">
              {{ formatEUR(g.eur_net) }}
            </td>
            <td class="num-col hide-sm muted">
              {{ formatUSD(g.usd_net) }}
            </td>
            <td class="hide-sm">
              <span class="source-tag">{{ g.source || 'ws' }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDashboardStore } from "../../stores/dashboardStore";
import { formatEUR, formatUSD, formatNumber } from "../../utils/formatters";

const store = useDashboardStore();
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

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-wrap: wrap;
  gap: 12px;
}

.card-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 16px;
  font-weight: 800;
  color: #ffffff;
  margin: 0;
  letter-spacing: -0.2px;
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
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}

.modern-table td {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.gift-row:hover {
  background: rgba(56, 189, 248, 0.04);
}

.timestamp-col {
  color: #94a3b8;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.streamer-tag {
  color: #38bdf8;
  font-weight: 700;
  font-size: 13px;
}

.sender-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.sender-name {
  font-weight: 700;
  color: #ffffff;
}

.sender-handle {
  color: #94a3b8;
  font-size: 12px;
}

.super-fan-badge {
  font-size: 9.5px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}

.gift-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 12px;
  color: #e2e8f0;
}

.source-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: #64748b;
  text-transform: uppercase;
}

.text-cyan {
  color: #38bdf8;
}

.text-emerald {
  color: #34d399;
}

.muted {
  color: #94a3b8;
}

.font-bold {
  font-weight: 700;
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
</style>
