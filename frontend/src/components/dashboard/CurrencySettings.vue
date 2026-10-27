<template>
  <div class="card currency-settings">
    <div class="card-header">
      <h3>SYSTEM-EINSTELLUNGEN &amp; WÄHRUNGSKURSE</h3>
      <p class="muted">
        Definiert die Umrechnungsfaktoren für Creator-Nettoeinnahmen und Zuschauer-Bruttoausgaben.
      </p>
    </div>

    <form @submit.prevent="handleSaveSettings" class="settings-form">
      <div class="form-grid">
        <div class="form-group">
          <label for="inputUsdPerDiamond">Netto USD pro Coin/Diamond</label>
          <input
            id="inputUsdPerDiamond"
            v-model.number="usdPerDiamond"
            type="number"
            step="0.0001"
            class="sm-input"
            required
          />
          <span class="muted" style="font-size:11px;">TikTok Creator Standard: $0.005 (50%)</span>
        </div>

        <div class="form-group">
          <label for="inputGrossPerCoin">Brutto USD Kaufpreis pro Coin</label>
          <input
            id="inputGrossPerCoin"
            v-model.number="grossUsdPerCoin"
            type="number"
            step="0.0001"
            class="sm-input"
            required
          />
          <span class="muted" style="font-size:11px;">Web-Kaufwert ca. $0.0106 pro Coin</span>
        </div>

        <div class="form-group">
          <label for="inputUsdToEur">USD zu EUR Wechselkurs</label>
          <input
            id="inputUsdToEur"
            v-model.number="usdToEurRate"
            type="number"
            step="0.001"
            class="sm-input"
            required
          />
          <span class="muted" style="font-size:11px;">1 USD = x EUR</span>
        </div>

        <div class="form-group">
          <label for="inputPollInterval">Offline-Poll Intervall (Sekunden)</label>
          <input
            id="inputPollInterval"
            v-model.number="pollInterval"
            type="number"
            min="10"
            max="600"
            class="sm-input"
            required
          />
          <span class="muted" style="font-size:11px;">Wartezeit für Live-Recheck bei Offline-Streamern</span>
        </div>
      </div>

      <div style="margin-top: 16px; text-align: right;">
        <button type="submit" class="primary sm" :disabled="isSaving">
          {{ isSaving ? 'Speichere...' : 'Währungskurse aktualisieren' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useDashboardStore } from "../../stores/dashboardStore";

const store = useDashboardStore();

const usdPerDiamond = ref(0.005);
const grossUsdPerCoin = ref(0.0106);
const usdToEurRate = ref(0.92);
const pollInterval = ref(45);
const isSaving = ref(false);

watch(
  () => store.settings,
  (s) => {
    if (s) {
      usdPerDiamond.value = s.usd_per_diamond ?? 0.005;
      grossUsdPerCoin.value = s.gross_usd_per_coin ?? 0.0106;
      usdToEurRate.value = s.usd_to_eur_rate ?? 0.92;
      pollInterval.value = s.poll_interval_seconds ?? 45;
    }
  },
  { immediate: true }
);

async function handleSaveSettings() {
  isSaving.value = true;
  try {
    await store.updateSettings({
      usd_per_diamond: usdPerDiamond.value,
      gross_usd_per_coin: grossUsdPerCoin.value,
      usd_to_eur_rate: usdToEurRate.value,
      poll_interval_seconds: pollInterval.value,
    });
    alert("Einstellungen erfolgreich gespeichert!");
  } finally {
    isSaving.value = false;
  }
}
</script>
