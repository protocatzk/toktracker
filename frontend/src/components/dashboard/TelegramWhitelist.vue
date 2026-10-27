<template>
  <div class="telegram-whitelist-section">
    <!-- Steuerung & Zugriffsmodus Card -->
    <div class="modern-card control-card">
      <div class="card-header">
        <div class="header-left">
          <span class="header-icon">🛡️</span>
          <div>
            <h3 class="card-title">Telegram-Bot Steuerung &amp; Zugriffsmodus</h3>
            <p class="card-subtitle">
              Im Modus <strong>WHITELIST</strong> haben nur freigeschaltete Personen Zugriff auf Bot- und Radar-Funktionen.
            </p>
          </div>
        </div>
      </div>

      <div class="control-row">
        <div class="mode-select-wrap">
          <label for="selectAccessMode" class="mode-label">Zugriffsmodus:</label>
          <div class="select-wrapper">
            <select
              id="selectAccessMode"
              :value="store.settings?.telegram_access_mode || 'whitelist'"
              @change="handleModeChange"
              class="modern-select"
            >
              <option value="whitelist">WHITELIST – Nur freigeschaltete Personen (@username / ID)</option>
              <option value="public">PUBLIC – Alle Telegram-Nutzer dürfen Streams abfragen</option>
            </select>
          </div>
        </div>
        <button type="button" class="btn-primary" @click="handleSendReport">
          📤 24h-Bericht an Telegram senden
        </button>
      </div>
    </div>

    <!-- Nutzer hinzufügen Formular -->
    <div class="modern-card add-card">
      <div class="card-header">
        <div class="header-left">
          <span class="header-icon">👤</span>
          <div>
            <h3 class="card-title">Berechtigte Personen Freischalten</h3>
            <p class="card-subtitle">
              Personen mit der Rolle <strong>Admin</strong> können sich auch über den Telegram-Bot im Web-Admin-Panel anmelden.
            </p>
          </div>
        </div>
      </div>

      <form @submit.prevent="handleAddUser" class="form-row-modern">
        <div class="input-wrap">
          <input
            v-model="newIdentifier"
            type="text"
            placeholder="Telegram-ID oder @username"
            required
            class="modern-input"
          />
        </div>
        <div class="input-wrap">
          <input
            v-model="newNote"
            type="text"
            placeholder="Name oder Notiz (optional)"
            class="modern-input"
          />
        </div>
        <select v-model="newRole" class="modern-select">
          <option value="user">Rolle: Nutzer (Abfragen)</option>
          <option value="admin">Rolle: Admin (Voller Zugriff)</option>
        </select>
        <button type="submit" class="btn-primary" :disabled="isSubmitting">
          {{ isSubmitting ? 'Wird gespeichert...' : 'Freischalten' }}
        </button>
      </form>
    </div>

    <!-- Tabelle der Telegram-Nutzer -->
    <div class="modern-card">
      <div class="card-header-bar">
        <h3 class="card-title">Whitelist &amp; Rollenübersicht</h3>
        <span class="count-badge">{{ store.telegramUsers.length }} Mitglieder</span>
      </div>

      <div class="table-responsive">
        <table class="modern-table">
          <thead>
            <tr>
              <th class="hide-sm">TELEGRAM USER-ID</th>
              <th>@USERNAME / NAME</th>
              <th>ROLLE</th>
              <th>STATUS</th>
              <th class="hide-sm">NOTIZ</th>
              <th class="hide-md">ZULETZT AKTIV</th>
              <th style="text-align: right;">AKTIONEN</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="store.telegramUsers.length === 0">
              <td colspan="7" class="empty-cell">
                <div class="empty-state">
                  <span class="empty-icon">👥</span>
                  <p>Keine Einträge in der Whitelist vorhanden.</p>
                </div>
              </td>
            </tr>
            <tr v-for="u in store.telegramUsers" :key="u.id" class="user-row">
              <td class="id-col hide-sm">
                {{ u.telegram_id || 'wird verknüpft' }}
              </td>
              <td>
                <div class="user-profile">
                  <strong class="user-handle">{{ u.username ? `@${u.username}` : '-' }}</strong>
                  <span v-if="u.first_name" class="user-name">({{ u.first_name }})</span>
                </div>
              </td>
              <td>
                <span :class="['role-badge', u.role === 'admin' ? 'role-admin' : 'role-user']">
                  {{ u.role === 'admin' ? '👑 ADMIN' : 'NUTZER' }}
                </span>
              </td>
              <td>
                <span v-if="Number(u.is_allowed) === 1" class="status-badge badge-live">
                  <span class="status-pulse-dot"></span> FREIGESCHALTET
                </span>
                <span v-else-if="Number(u.is_allowed) === 0" class="status-badge badge-polling">
                  {{ store.settings?.telegram_access_mode === 'public' ? 'PUBLIC-GAST' : 'ANFRAGE OFFEN' }}
                </span>
                <span v-else class="status-badge badge-danger">GESPERRT</span>
              </td>
              <td class="muted hide-sm" style="font-size: 12px;">
                {{ u.note || '-' }}
              </td>
              <td class="muted hide-md" style="font-size: 12px;">
                {{ (u.last_seen_at || '').replace('T', ' ').substring(0, 19) || '-' }}
              </td>
              <td style="text-align: right;">
                <div class="action-buttons">
                  <button
                    v-if="Number(u.is_allowed) !== 1"
                    type="button"
                    class="btn-action btn-start"
                    @click="updateUserStatus(u, 1, u.role)"
                  >
                    Zulassen
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn-action btn-stop"
                    @click="updateUserStatus(u, -1, 'user')"
                  >
                    Sperren
                  </button>

                  <button
                    v-if="u.role !== 'admin'"
                    type="button"
                    class="btn-action btn-details"
                    @click="updateUserStatus(u, 1, 'admin')"
                  >
                    → Admin
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn-action"
                    @click="updateUserStatus(u, 1, 'user')"
                  >
                    → Nutzer
                  </button>

                  <button
                    type="button"
                    class="btn-action btn-delete"
                    @click="deleteUser(u.id)"
                    title="Eintrag entfernen"
                  >
                    ✕
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
import type { TelegramUser } from "../../types";

const store = useDashboardStore();

const newIdentifier = ref("");
const newNote = ref("");
const newRole = ref("user");
const isSubmitting = ref(false);

async function handleAddUser() {
  if (!newIdentifier.value.trim()) return;
  isSubmitting.value = true;
  try {
    await store.updateTelegramUser(
      newIdentifier.value.trim(),
      1,
      newRole.value
    );
    newIdentifier.value = "";
    newNote.value = "";
  } finally {
    isSubmitting.value = false;
  }
}

async function handleModeChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  await store.updateSettings({
    telegram_access_mode: target.value,
  });
}

async function handleSendReport() {
  try {
    const res = await fetch("/api/v1/telegram/report", { method: "POST" });
    const json = await res.json();
    alert(json.message || "24h-Report erfolgreich an Telegram gesendet!");
  } catch (err: any) {
    alert("Fehler beim Senden: " + err.message);
  }
}

async function updateUserStatus(u: TelegramUser, isAllowed: number, role: string) {
  const ident = u.telegram_id ? String(u.telegram_id) : `@${u.username}`;
  await store.updateTelegramUser(ident, isAllowed, role);
}

async function deleteUser(recordId: number) {
  if (confirm("Diesen Telegram-Eintrag wirklich löschen?")) {
    await store.deleteTelegramUser(recordId);
  }
}
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

.control-card, .add-card {
  padding: 22px 24px;
}

.card-header {
  margin-bottom: 16px;
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

.control-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.mode-select-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mode-label {
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
}

.form-row-modern {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}

.input-wrap {
  flex: 1;
  min-width: 200px;
}

.modern-input {
  width: 100%;
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

.modern-select {
  appearance: none;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 9px 32px 9px 14px;
  color: #f1f5f9;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 14px;
}

.modern-select:focus {
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  padding: 9px 18px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%);
  color: #090d16;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  box-shadow: 0 4px 14px rgba(14, 165, 233, 0.3);
  transition: all 0.2s ease;
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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

.user-row:hover {
  background: rgba(56, 189, 248, 0.04);
}

.id-col {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-handle {
  color: #ffffff;
  font-size: 13.5px;
}

.user-name {
  color: #94a3b8;
  font-size: 12px;
}

.role-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.5px;
}

.role-admin {
  background: rgba(56, 189, 248, 0.15);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #38bdf8;
}

.role-user {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.badge-live {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #34d399;
}

.status-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
}

.badge-polling {
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #38bdf8;
}

.badge-danger {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #f87171;
}

.muted {
  color: #94a3b8;
}

.action-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.btn-action {
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #f1f5f9;
  transition: all 0.15s ease;
}

.btn-action:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}

.btn-start {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.35);
  color: #34d399;
}

.btn-stop {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}

.btn-details {
  background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.3);
  color: #38bdf8;
}

.btn-delete {
  color: #f87171;
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.5);
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

@media (max-width: 992px) {
  .hide-md {
    display: none !important;
  }
}
</style>
