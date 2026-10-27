<template>
  <div class="modern-card banner-settings-card">
    <div class="card-header">
      <div class="header-left">
        <span class="header-icon">📢</span>
        <div>
          <h3 class="card-title">Öffentliches Ankündigungs- &amp; Whitelist-Banner</h3>
          <p class="card-subtitle">
            Dieses Banner wird auf der öffentlichen Seite (<code>/public</code>) prominent über dem Leaderboard platziert.
          </p>
        </div>
      </div>
      <div class="header-status">
        <span :class="['status-pill', bannerEnabled ? 'active' : 'inactive']">
          <span class="dot"></span>
          {{ bannerEnabled ? 'BANNER AKTIV' : 'DEAKTIVIERT' }}
        </span>
      </div>
    </div>

    <!-- Live Preview -->
    <div class="preview-section">
      <div class="preview-label">
        <span>👁️ Live-Vorschau</span>
        <span class="preview-sub">(Echtzeitdarstellung wie im Public-Portal)</span>
      </div>
      <div
        :class="['announcement-banner', bannerStyle]"
        :style="{ opacity: bannerEnabled ? '1' : '0.45' }"
      >
        <div class="banner-tag">{{ bannerTagText }}</div>
        <div class="banner-content">
          <strong>{{ bannerTitle || 'Exklusive Whitelist-Features freischalten' }}</strong>
          <p>{{ bannerText || 'Verbinde dich mit unserem Telegram-Bot für Echtzeit-Alerts und Spender-Intelligence.' }}</p>
        </div>
        <div class="banner-action" v-if="bannerBtnText">
          <span class="btn-banner">{{ bannerBtnText }}</span>
        </div>
      </div>
    </div>

    <!-- Formular -->
    <form @submit.prevent="handleSaveBanner" class="banner-form">
      <div class="form-grid">
        <div class="form-group toggle-group">
          <label class="toggle-label">
            <input type="checkbox" v-model="bannerEnabled" class="custom-checkbox" />
            <span class="checkbox-text">Banner im Public-Portal anzeigen</span>
          </label>
        </div>

        <div class="form-group">
          <label for="bannerStyleSelect">Banner-Stil &amp; Farbakzent</label>
          <select id="bannerStyleSelect" v-model="bannerStyle" class="modern-select">
            <option value="highlight">✨ Highlight (Gold / VIP-Glow)</option>
            <option value="info">ℹ️ Info (Sleek Cyan / Blue)</option>
            <option value="success">🟢 Status (Emerald / Alles Normal)</option>
            <option value="warning">⚠️ Warnung (Amber / Wichtig)</option>
          </select>
        </div>

        <div class="form-group full-width">
          <label for="bannerTitleInput">Banner-Titel</label>
          <input
            id="bannerTitleInput"
            type="text"
            v-model="bannerTitle"
            class="modern-input"
            placeholder="z.B. Telegram-Community &amp; Whitelist Zugang"
            required
          />
        </div>

        <div class="form-group full-width">
          <label for="bannerTextInput">Banner-Text &amp; Call-to-Action</label>
          <textarea
            id="bannerTextInput"
            v-model="bannerText"
            rows="2"
            class="modern-input"
            placeholder="Beschreibe kurz den Mehrwert..."
            required
          ></textarea>
        </div>

        <div class="form-group">
          <label for="bannerBtnTextInput">Button-Beschriftung</label>
          <input
            id="bannerBtnTextInput"
            type="text"
            v-model="bannerBtnText"
            class="modern-input"
            placeholder="z.B. Jetzt beitreten 🚀"
          />
        </div>

        <div class="form-group">
          <label for="bannerBtnUrlInput">Button-Ziel-URL (optional)</label>
          <input
            id="bannerBtnUrlInput"
            type="text"
            v-model="bannerBtnUrl"
            placeholder="Leer lassen für automatischen Telegram-Link"
            class="modern-input"
          />
        </div>
      </div>

      <div class="form-actions">
        <button type="submit" class="btn-primary" :disabled="isSaving">
          <span v-if="isSaving" class="spinner"></span>
          <span>{{ isSaving ? 'Speichere...' : 'Banner-Einstellungen speichern' }}</span>
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

<style scoped>
.modern-card {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 24px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  margin-bottom: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  font-size: 24px;
  padding: 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: -0.01em;
}

.card-subtitle {
  margin: 4px 0 0 0;
  font-size: 12.5px;
  color: #94a3b8;
}

.card-subtitle code {
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  color: #38bdf8;
  font-size: 11.5px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.status-pill.active {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
}

.status-pill.inactive {
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.status-pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.preview-section {
  background: rgba(10, 15, 28, 0.6);
  border: 1px dashed rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 24px;
}

.preview-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 12px;
}

.preview-sub {
  font-size: 11px;
  color: #64748b;
  font-weight: 400;
}

.announcement-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-radius: 12px;
  transition: all 0.3s ease;
}

.announcement-banner.highlight {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.15), rgba(217, 119, 6, 0.08));
  border: 1px solid rgba(245, 158, 11, 0.3);
  box-shadow: 0 4px 20px rgba(245, 158, 11, 0.08);
}

.announcement-banner.info {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.15), rgba(2, 132, 199, 0.08));
  border: 1px solid rgba(14, 165, 233, 0.3);
}

.announcement-banner.success {
  background: linear-gradient(90deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.08));
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.announcement-banner.warning {
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.15), rgba(220, 38, 38, 0.08));
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.banner-tag {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  white-space: nowrap;
}

.banner-content {
  flex: 1;
}

.banner-content strong {
  display: block;
  font-size: 13.5px;
  color: #f8fafc;
  margin-bottom: 2px;
}

.banner-content p {
  margin: 0;
  font-size: 12px;
  color: #cbd5e1;
}

.btn-banner {
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.full-width {
  grid-column: 1 / -1;
}

.toggle-group {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.custom-checkbox {
  width: 18px;
  height: 18px;
  accent-color: #38bdf8;
  cursor: pointer;
}

.checkbox-text {
  font-size: 13.5px;
  font-weight: 600;
  color: #f1f5f9;
}

.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 6px;
}

.modern-input,
.modern-select {
  width: 100%;
  padding: 10px 14px;
  background: rgba(10, 15, 28, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #f8fafc;
  font-size: 13px;
  box-sizing: border-box;
  font-family: inherit;
  transition: all 0.2s ease;
}

.modern-input:focus,
.modern-select:focus {
  outline: none;
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
  background: rgba(10, 15, 28, 0.9);
}

.form-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
  border: none;
  border-radius: 10px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.95;
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
