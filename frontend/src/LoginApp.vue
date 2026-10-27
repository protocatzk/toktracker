<template>
  <div class="login-wrapper">
    <!-- Header link to public -->
    <header class="login-top-bar">
      <a href="/public" class="brand-link">
        <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="bar-logo" onerror="this.src='/static/avatar_default.png'" />
        <span>toktracker</span>
      </a>
      <div class="top-bar-right">
        <a href="/public" class="btn-ghost">🌐 Zum Public Radar ↗</a>
        <button type="button" class="btn-ghost" @click="toggleTheme">
          {{ currentTheme === 'dark' ? '🌙 Dark' : '☀️ Light' }}
        </button>
      </div>
    </header>

    <div class="login-container">
      <div class="modern-card login-card">
        <!-- Logo & Title -->
        <div class="login-header">
          <div class="avatar-ring">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="login-avatar" onerror="this.src='/static/avatar_default.png'" />
            <span class="avatar-pulse"></span>
          </div>
          <h2 class="login-title">Admin-Authentifizierung</h2>
          <p class="login-subtitle">
            Sicherer 2FA-Zugang über das Telegram-Gateway
          </p>
        </div>

        <!-- Status Message Banner -->
        <div v-if="statusMessage" :class="['status-box', statusType]">
          <span class="status-icon">{{ statusType === 'success' ? '✅' : (statusType === 'error' ? '❌' : 'ℹ️') }}</span>
          <span>{{ statusMessage }}</span>
        </div>

        <!-- STEP 1: Idle / Request Push Challenge -->
        <div v-if="authStep === 'idle'" class="step-box">
          <div class="method-card" @click="requestChallenge">
            <div class="method-icon">📲</div>
            <div class="method-info">
              <strong>1-Click Telegram 2FA</strong>
              <span>Sendet eine Genehmigungsanfrage an deinen Telegram-Bot</span>
            </div>
            <span class="method-arrow">→</span>
          </div>

          <div class="divider">
            <span>ODER MANUELLER CODE</span>
          </div>

          <!-- Direct Code Input -->
          <div class="manual-code-form">
            <label for="codeInput">6-stelliger Bestätigungscode:</label>
            <div class="input-with-button">
              <input
                id="codeInput"
                v-model="manualCode"
                type="text"
                maxlength="6"
                placeholder="z.B. 123456"
                class="modern-input center-text"
                @keydown.enter.prevent="submitManualCode"
              />
              <button
                type="button"
                class="btn-primary"
                :disabled="manualCode.length !== 6 || isVerifying"
                @click="submitManualCode"
              >
                {{ isVerifying ? 'Prüfe...' : 'Einloggen' }}
              </button>
            </div>
          </div>

          <div class="divider">
            <span>ADMIN-PASSWORT / API-KEY</span>
          </div>

          <!-- API Key / Password -->
          <form @submit.prevent="submitApiKey" class="api-key-form">
            <input
              v-model="apiKeyInput"
              type="password"
              placeholder="Admin-Passwort oder API-Key..."
              class="modern-input"
              required
            />
            <button type="submit" class="btn-ghost full-width" :disabled="isVerifying">
              Mit API-Key anmelden
            </button>
          </form>
        </div>

        <!-- STEP 2: Waiting for Telegram Approval -->
        <div v-else-if="authStep === 'waiting'" class="step-box waiting-box">
          <div class="radar-ping">
            <div class="ping-circle"></div>
            <div class="ping-dot"></div>
          </div>

          <h3>Warte auf Bestätigung...</h3>
          <p class="waiting-text">
            Wir haben eine Bestätigungsanfrage an deinen hinterlegten Telegram-Account gesendet. Bitte tippe in Telegram auf <strong>"Zulassen"</strong>.
          </p>

          <div class="challenge-code-display" v-if="challengeCode">
            <span class="code-sub">Alternativer 6-stelliger Code:</span>
            <span class="code-digits">{{ challengeCode }}</span>
          </div>

          <div class="countdown-bar-wrap">
            <div class="countdown-bar" :style="{ width: `${(timeLeft / 120) * 100}%` }"></div>
          </div>
          <span class="countdown-text">Gültig für: {{ timeLeft }}s</span>

          <div class="waiting-actions">
            <button type="button" class="btn-ghost" @click="cancelChallenge">
              Abbrechen &amp; Zurück
            </button>
          </div>
        </div>

        <!-- STEP 3: Success -->
        <div v-else-if="authStep === 'success'" class="step-box success-box">
          <div class="success-icon">🎉</div>
          <h3>Erfolgreich autorisiert!</h3>
          <p>Weiterleitung zum Dashboard...</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";

// State
const authStep = ref<"idle" | "waiting" | "success">("idle");
const statusMessage = ref("");
const statusType = ref<"info" | "error" | "success">("info");
const manualCode = ref("");
const apiKeyInput = ref("");
const isVerifying = ref(false);
const challengeId = ref("");
const challengeCode = ref("");
const timeLeft = ref(120);
const currentTheme = ref("dark");

let pollTimer: any = null;
let countdownTimer: any = null;

function setStatus(msg: string, type: "info" | "error" | "success" = "info") {
  statusMessage.value = msg;
  statusType.value = type;
}

async function requestChallenge() {
  setStatus("Erstelle Telegram-Anfrage...", "info");
  try {
    const res = await fetch("/api/auth/challenge/request", { method: "POST" });
    const data = await res.json();
    if (res.ok && data.challenge_id) {
      challengeId.value = data.challenge_id;
      challengeCode.value = data.code || "";
      authStep.value = "waiting";
      timeLeft.value = 120;
      setStatus("Genehmigungsanfrage gesendet. Bitte in Telegram bestätigen.", "info");

      startPolling();
    } else {
      setStatus(data.detail || "Fehler beim Anfordern der Telegram-Challenge.", "error");
    }
  } catch (err: any) {
    setStatus("Netzwerkfehler: " + err.message, "error");
  }
}

function startPolling() {
  clearInterval(pollTimer);
  clearInterval(countdownTimer);

  countdownTimer = setInterval(() => {
    timeLeft.value--;
    if (timeLeft.value <= 0) {
      cancelChallenge();
      setStatus("Zeit abgelaufen. Bitte erneut versuchen.", "error");
    }
  }, 1000);

  pollTimer = setInterval(async () => {
    if (!challengeId.value) return;
    try {
      const res = await fetch(`/api/auth/challenge/poll?challenge_id=${encodeURIComponent(challengeId.value)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === "approved") {
          onSuccessRedirect();
        } else if (data.status === "rejected") {
          cancelChallenge();
          setStatus("Die Anfrage wurde in Telegram abgelehnt.", "error");
        }
      }
    } catch {}
  }, 2000);
}

function cancelChallenge() {
  clearInterval(pollTimer);
  clearInterval(countdownTimer);
  authStep.value = "idle";
  challengeId.value = "";
}

async function submitManualCode() {
  if (manualCode.value.length !== 6) return;
  isVerifying.value = true;
  setStatus("Verifiziere Code...", "info");

  try {
    const res = await fetch("/api/auth/challenge/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        challenge_id: challengeId.value || undefined,
        code: manualCode.value.trim(),
      }),
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      onSuccessRedirect();
    } else {
      setStatus(data.detail || "Ungültiger Bestätigungscode.", "error");
    }
  } catch (err: any) {
    setStatus("Netzwerkfehler: " + err.message, "error");
  } finally {
    isVerifying.value = false;
  }
}

async function submitApiKey() {
  if (!apiKeyInput.value.trim()) return;
  isVerifying.value = true;
  setStatus("Prüfe Admin-Passwort...", "info");

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password: apiKeyInput.value.trim(),
      }),
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      onSuccessRedirect();
    } else {
      setStatus(data.detail || "Falsches Admin-Passwort oder API-Key.", "error");
    }
  } catch (err: any) {
    setStatus("Netzwerkfehler: " + err.message, "error");
  } finally {
    isVerifying.value = false;
  }
}

function onSuccessRedirect() {
  clearInterval(pollTimer);
  clearInterval(countdownTimer);
  authStep.value = "success";
  setStatus("✅ Erfolgreich angemeldet!", "success");

  const urlParams = new URLSearchParams(window.location.search);
  const next = urlParams.get("next") || "/admin";
  setTimeout(() => {
    window.location.href = next;
  }, 400);
}

function toggleTheme() {
  const next = currentTheme.value === "light" ? "dark" : "light";
  currentTheme.value = next;
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("toktracker_theme", next);
  } catch {}
}

onMounted(() => {
  try {
    currentTheme.value = localStorage.getItem("toktracker_theme") || "dark";
    document.documentElement.setAttribute("data-theme", currentTheme.value);
  } catch {}

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("error")) {
    setStatus(decodeURIComponent(urlParams.get("error") || ""), "error");
  }
});

onUnmounted(() => {
  clearInterval(pollTimer);
  clearInterval(countdownTimer);
});
</script>

<style scoped>
.login-wrapper {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-body, #090d16);
  color: var(--text-main, #f1f5f9);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

.login-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.brand-link {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: #fff;
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-weight: 800;
  font-size: 18px;
}

.bar-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.top-bar-right {
  display: flex;
  gap: 12px;
}

.login-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 480px;
  background: rgba(15, 21, 35, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  padding: 32px;
  backdrop-filter: blur(20px);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 30px rgba(56, 189, 248, 0.1);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.avatar-ring {
  position: relative;
  display: inline-block;
  margin-bottom: 12px;
}

.login-avatar {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  object-fit: cover;
  border: 2px solid rgba(56, 189, 248, 0.4);
}

.avatar-pulse {
  position: absolute;
  inset: -4px;
  border-radius: 22px;
  border: 2px solid #38bdf8;
  opacity: 0.6;
  animation: ringPulse 2s infinite;
}

@keyframes ringPulse {
  0% { transform: scale(0.95); opacity: 0.8; }
  50% { transform: scale(1.08); opacity: 0.2; }
  100% { transform: scale(0.95); opacity: 0.8; }
}

.login-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 20px;
  font-weight: 800;
  color: #ffffff;
  margin: 0 0 6px;
}

.login-subtitle {
  font-size: 13px;
  color: #94a3b8;
  margin: 0;
}

/* Status Box */
.status-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 20px;
  font-size: 12.5px;
  line-height: 1.4;
}

.status-box.info {
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.3);
  color: #7dd3fc;
}

.status-box.error {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.status-box.success {
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #6ee7b7;
}

/* Method Card */
.method-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.15), rgba(56, 189, 248, 0.15));
  border: 1px solid rgba(56, 189, 248, 0.35);
  cursor: pointer;
  transition: all 0.2s ease;
}

.method-card:hover {
  transform: translateY(-2px);
  border-color: #38bdf8;
  box-shadow: 0 8px 24px rgba(56, 189, 248, 0.2);
}

.method-icon {
  font-size: 28px;
}

.method-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.method-info strong {
  font-size: 14px;
  color: #ffffff;
}

.method-info span {
  font-size: 11.5px;
  color: #94a3b8;
}

.method-arrow {
  font-size: 18px;
  color: #38bdf8;
  font-weight: 700;
}

/* Divider */
.divider {
  display: flex;
  align-items: center;
  text-align: center;
  margin: 20px 0;
}

.divider::before, .divider::after {
  content: '';
  flex: 1;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.divider span {
  padding: 0 10px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: #64748b;
}

/* Inputs */
.modern-input {
  width: 100%;
  padding: 11px 14px;
  background: rgba(10, 15, 28, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #ffffff;
  font-size: 13.5px;
  box-sizing: border-box;
  outline: none;
  transition: all 0.2s ease;
}

.modern-input:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

.center-text {
  text-align: center;
  font-size: 16px;
  letter-spacing: 2px;
  font-family: monospace;
}

.manual-code-form label {
  display: block;
  font-size: 11.5px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 6px;
}

.input-with-button {
  display: flex;
  gap: 8px;
}

.api-key-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.full-width {
  width: 100%;
  text-align: center;
}

.btn-primary {
  padding: 10px 18px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
  border: none;
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}

.btn-ghost:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

/* Waiting Step */
.waiting-box {
  text-align: center;
  padding: 16px 0;
}

.radar-ping {
  position: relative;
  width: 60px;
  height: 60px;
  margin: 0 auto 16px;
}

.ping-circle {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid #38bdf8;
  animation: pingExpand 1.8s infinite;
}

@keyframes pingExpand {
  0% { transform: scale(0.6); opacity: 1; }
  100% { transform: scale(1.6); opacity: 0; }
}

.ping-dot {
  position: absolute;
  inset: 22px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 12px #38bdf8;
}

.waiting-box h3 {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 800;
  color: #ffffff;
}

.waiting-text {
  font-size: 12.5px;
  color: #94a3b8;
  line-height: 1.5;
  margin-bottom: 20px;
}

.challenge-code-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin-bottom: 20px;
  background: rgba(255, 255, 255, 0.04);
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.code-sub {
  font-size: 11px;
  color: #94a3b8;
}

.code-digits {
  font-family: monospace;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 4px;
  color: #38bdf8;
}

.countdown-bar-wrap {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 6px;
}

.countdown-bar {
  height: 100%;
  background: linear-gradient(90deg, #38bdf8, #2563eb);
  transition: width 1s linear;
}

.countdown-text {
  font-size: 11px;
  color: #64748b;
  display: block;
  margin-bottom: 20px;
}

.waiting-actions {
  display: flex;
  justify-content: center;
}

/* Success Box */
.success-box {
  text-align: center;
  padding: 24px 0;
}

.success-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.success-box h3 {
  color: #34d399;
  font-size: 18px;
  margin: 0 0 6px;
}

.success-box p {
  color: #94a3b8;
  font-size: 13px;
  margin: 0;
}
</style>
