<template>
  <div class="card">
    <div class="card-header-bar">
      <h3>LETZTE GIFT-TRANSAKTIONEN (DATENBANK-LOG)</h3>
      <div class="header-controls">
        <input
          v-model="store.giftFilter"
          type="search"
          placeholder="Transaktionen filtern..."
          class="sm-input"
        />
        <span class="mono muted">
          {{ store.filteredGifts.length }} von {{ store.recentGifts.length }} Transaktionen
        </span>
      </div>
    </div>

    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>ZEITPUNKT</th>
            <th>STREAMER</th>
            <th>ABSENDER</th>
            <th class="hide-sm">GESCHENK</th>
            <th class="num-col">COINS</th>
            <th class="num-col">NETTO (EUR)</th>
            <th class="num-col hide-sm">NETTO (USD)</th>
            <th class="hide-sm">QUELLE</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="store.filteredGifts.length === 0">
            <td colspan="8" class="muted text-center" style="padding: 24px;">
              {{ store.isLoading ? 'Lade Daten...' : 'Keine Transaktionen für diesen Zeitraum vorhanden.' }}
            </td>
          </tr>
          <tr v-for="g in store.filteredGifts" :key="g.id">
            <td class="mono muted" style="font-size:11px;">
              {{ (g.created_at || g.timestamp || '').replace('T', ' ') }}
            </td>
            <td class="mono">
              <strong>@{{ g.streamer_username }}</strong>
            </td>
            <td>
              <span>{{ g.sender_nickname || g.sender_username }}</span>
              <span class="mono muted hide-sm" style="font-size:11px;">
                (@{{ g.sender_username }})
              </span>
              <span v-if="g.is_super_fan" class="status-tag polling" style="margin-left: 4px;">
                SUPERFAN
              </span>
            </td>
            <td class="hide-sm">
              <strong>{{ g.repeat_count }}x</strong> {{ g.gift_name }}
            </td>
            <td class="num-col">
              <strong>{{ formatNumber(g.total_coins) }}</strong>
            </td>
            <td class="num-col">
              <strong>{{ formatEUR(g.eur_net) }}</strong>
            </td>
            <td class="num-col hide-sm">
              {{ formatUSD(g.usd_net) }}
            </td>
            <td class="mono muted hide-sm" style="font-size:11px;">
              {{ g.source }}
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
