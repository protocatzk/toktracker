<template>
  <div class="modern-card settings-card">
    <div class="card-header">
      <div class="header-left">
        <span class="header-icon">💱</span>
        <div>
          <h3 class="card-title">System-Einstellungen &amp; Währungskurse</h3>
          <p class="card-subtitle">
            Definiert die Umrechnungsfaktoren für Creator-Nettoeinnahmen und Zuschauer-Bruttoausgaben.
          </p>
        </div>
      </div>
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
            class="modern-input"
            required
          />
          <span class="field-hint">TikTok Standard: $0.005 (~50% Netto-Quote)</span>
        </div>

        <div class="form-group">
          <label for="inputGrossPerCoin">Brutto USD Kaufpreis pro Coin</label>
          <input
            id="inputGrossPerCoin"
            v-model.number="grossUsdPerCoin"
            type="number"
            step="0.0001"
            class="modern-input"
            required
          />
          <span class="field-hint">Viewer-Kaufwert ca. $0.0106 pro Coin</span>
        </div>

        <div class="form-group">
          <label for="inputUsdToEur">USD zu EUR Wechselkurs</label>
          <input
            id="inputUsdToEur"
            v-model.number="usdToEurRate"
            type="number"
            step="0.001"
            class="modern-input"
            required
          />
          <span class="field-hint">1 USD in EUR (z.B. 0.92)</span>
        </div>

        <div class="form-group">
          <label for="inputPollInterval">Offline-Poll Intervall (Sek.)</label>
          <input
            id="inputPollInterval"
            v-model.number="pollInterval"
            type="number"
            min="10"
            max="600"
            class="modern-input"
            required
          />
          <span class="field-hint">Abfrage-Zyklus für Offline-Streams</span>
        </div>
      </div>

      <div class="form-actions">
        <button type="submit" class="btn-primary" :disabled="isSubmitting">
          {{ isSubmitting ? 'Wird gespeichert...' : 'Kurse & Einstellungen speichern' }}
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
const pollInterval = ref(30);
const isSubmitting = ref(false);

watch(
  () => store.settings,
  (s) => {
    if (s) {
      usdPerDiamond.value = Number(s.usd_per_diamond) || 0.005;
      grossUsdPerCoin.value = Number(s.gross_usd_per_coin) || 0.0106;
      usdToEurRate.value = Number(s.usd_to_eur_rate) || 0.92;
      pollInterval.value = Number(s.poll_interval_seconds) || 30;
    }
  },
  { immediate: true }
);

async function handleSaveSettings() {
  isSubmitting.value = true;
  try {
    await store.updateSettings({
      usd_per_diamond: usdPerDiamond.value,
      gross_usd_per_coin: grossUsdPerCoin.value,
      usd_to_eur_rate: usdToEurRate.value,
      poll_interval_seconds: pollInterval.value,
    });
    alert("Einstellungen erfolgreich gespeichert!");
  } catch (err: any) {
    alert("Fehler beim Speichern: " + err.message);
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<style scoped>
.modern-card {
  background: var(--bg-surface, #0f1523);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 32px -4px rgba(0, 0, 0, 0.4);
  padding: 22px 24px;
  margin-bottom: 24px;
}

.card-header {
  margin-bottom: 20px;
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

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 12.5px;
  font-weight: 600;
  color: #e2e8f0;
}

.modern-input {
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

.field-hint {
  font-size: 11px;
  color: #94a3b8;
}

.form-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  padding: 9px 20px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%);
  color: #090d16;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  box-shadow: 0 4px 14px rgba(14, 165, 233, 0.3);
  transition: all 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
}
</style>
