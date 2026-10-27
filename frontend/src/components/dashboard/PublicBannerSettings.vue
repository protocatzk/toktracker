<template>
  <div class="card public-banner-settings">
    <div class="card-header">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <h3>ÖFFENTLICHES ANKÜNDIGUNGS- &amp; WHITELIST-BANNER</h3>
          <p class="muted">
            Dieses Banner wird auf der öffentlichen Seite (<code>/public</code>) über der Streamer-Tabelle angezeigt.
          </p>
        </div>
        <span :class="['status-tag', bannerEnabled ? 'live' : 'off']">
          {{ bannerEnabled ? 'BANNER AKTIV' : 'BANNER DEAKTIVIERT' }}
        </span>
      </div>
    </div>

    <!-- Live Preview -->
    <div style="margin-bottom: 20px;">
      <div class="muted" style="margin-bottom: 6px; font-size: 11px; text-transform: uppercase;">
        Live-Vorschau (wie im Public-Panel zu sehen):
      </div>
      <div
        :class="['announcement-banner', bannerStyle]"
        :style="{ opacity: bannerEnabled ? '1' : '0.45' }"
      >
        <div class="banner-tag">{{ bannerTagText }}</div>
        <div class="banner-content">
          <strong>{{ bannerTitle || 'Exklusive Whitelist-Features' }}</strong>
          <p>{{ bannerText || 'Schalte erweiterte Analysen wie Chat-Intelligence frei.' }}</p>
        </div>
        <div class="banner-action" v-if="bannerBtnText">
          <span class="btn-primary sm">{{ bannerBtnText }}</span>
        </div>
      </div>
    </div>

    <!-- Formular -->
    <form @submit.prevent="handleSaveBanner" class="banner-form">
      <div class="form-grid">
        <div class="form-group">
          <label>
            <input type="checkbox" v-model="bannerEnabled" />
            <strong>Banner auf /public anzeigen</strong>
          </label>
        </div>
        <div class="form-group">
          <label>Banner-Stil / Akzentfarbe</label>
          <select v-model="bannerStyle" class="sm-input">
            <option value="highlight">Highlight (Gold / VIP-Look)</option>
            <option value="info">Info (Blau / Hinweis)</option>
            <option value="success">Status (Grün / Alles OK)</option>
            <option value="warning">Warnung (Orange / Wichtig)</option>
          </select>
        </div>
        <div class="form-group" style="grid-column: 1 / -1;">
          <label>Banner-Titel</label>
          <input type="text" v-model="bannerTitle" class="sm-input" required />
        </div>
        <div class="form-group" style="grid-column: 1 / -1;">
          <label>Banner-Text / Beschreibung</label>
          <textarea v-model="bannerText" rows="2" class="sm-input" required></textarea>
        </div>
        <div class="form-group">
          <label>Button-Beschriftung</label>
          <input type="text" v-model="bannerBtnText" class="sm-input" />
        </div>
        <div class="form-group">
          <label>Button-URL (optional)</label>
          <input type="text" v-model="bannerBtnUrl" placeholder="Leer = autom. Telegram-Link" class="sm-input" />
        </div>
      </div>
      <div style="margin-top: 12px; text-align: right;">
        <button type="submit" class="primary sm" :disabled="isSaving">
          {{ isSaving ? 'Speichere...' : 'Banner-Einstellungen speichern' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { useDashboardStore } from "../../stores/dashboardStore";

const store = useDashboardStore();

const bannerEnabled = ref(true);
const bannerStyle = ref("highlight");
const bannerTitle = ref("");
const bannerText = ref("");
const bannerBtnText = ref("");
const bannerBtnUrl = ref("");
const isSaving = ref(false);

watch(
  () => store.settings,
  (s) => {
    if (s) {
      bannerEnabled.value = Boolean(s.public_banner_enabled);
      bannerStyle.value = s.public_banner_style || "highlight";
      bannerTitle.value = s.public_banner_title || "";
      bannerText.value = s.public_banner_text || "";
      bannerBtnText.value = s.public_banner_btn_text || "";
      bannerBtnUrl.value = s.public_banner_btn_url || "";
    }
  },
  { immediate: true }
);

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

async function handleSaveBanner() {
  isSaving.value = true;
  try {
    await store.updateSettings({
      public_banner_enabled: bannerEnabled.value ? 1 : 0,
      public_banner_style: bannerStyle.value,
      public_banner_title: bannerTitle.value.trim(),
      public_banner_text: bannerText.value.trim(),
      public_banner_btn_text: bannerBtnText.value.trim(),
      public_banner_btn_url: bannerBtnUrl.value.trim(),
    });
    alert("Banner-Einstellungen erfolgreich gespeichert!");
  } finally {
    isSaving.value = false;
  }
}
</script>
