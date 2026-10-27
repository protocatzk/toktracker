<template>
  <div class="telegram-whitelist-section">
    <!-- Steuerung & Zugriffsmodus Card -->
    <div class="card" style="margin-bottom: 20px;">
      <div class="card-header">
        <h3>TELEGRAM-BOT STEUERUNG &amp; ZUGRIFFSMODUS</h3>
        <p class="muted">
          Im Modus <strong>WHITELIST</strong> können nur freigeschaltete Nutzer Befehle ausführen.
          Im Modus <strong>PUBLIC</strong> sind Abfrage-Befehle für alle offen.
        </p>
      </div>

      <div class="form-row-compact" style="align-items: center; justify-content: space-between;">
        <div style="display: flex; gap: 8px; align-items: center;">
          <label for="selectAccessMode"><strong>Zugriffsmodus:</strong></label>
          <select
            id="selectAccessMode"
            :value="store.settings?.telegram_access_mode || 'whitelist'"
            @change="handleModeChange"
            class="sm-input"
          >
            <option value="whitelist">WHITELIST – Nur freigeschaltete Personen (@username / ID)</option>
            <option value="public">PUBLIC – Alle Telegram-Nutzer dürfen Streams abfragen</option>
          </select>
        </div>
        <button type="button" class="sm" @click="handleSendReport">
          24h-Bericht an Telegram senden
        </button>
      </div>
    </div>

    <!-- Nutzer hinzufügen Formular -->
    <div class="card" style="margin-bottom: 20px;">
      <div class="card-header">
        <h3>BERECHTIGTE PERSONEN &amp; OFFENE ZUGRIFFSANFRAGEN</h3>
        <p class="muted">
          Personen mit der Rolle <strong>Admin</strong> können sich auch über den Telegram-Bot im Web-Admin-Panel anmelden.
        </p>
      </div>

      <form @submit.prevent="handleAddUser" class="form-row-compact">
        <input
          v-model="newIdentifier"
          type="text"
          placeholder="Telegram-ID oder @username"
          required
          style="max-width: 220px;"
        />
        <input
          v-model="newNote"
          type="text"
          placeholder="Name oder Notiz"
          style="max-width: 220px;"
        />
        <select v-model="newRole" class="sm-input">
          <option value="user">Rolle: Nutzer (Abfragen)</option>
          <option value="admin">Rolle: Admin (Voller Zugriff)</option>
        </select>
        <button type="submit" class="primary sm" :disabled="isSubmitting">
          Freischalten
        </button>
      </form>
    </div>

    <!-- Tabelle der Telegram-Nutzer -->
    <div class="card">
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th class="hide-sm">TELEGRAM USER-ID</th>
              <th>@USERNAME / NAME</th>
              <th>ROLLE</th>
              <th>STATUS</th>
              <th class="hide-sm">NOTIZ / HERKUNFT</th>
              <th class="hide-md">ZULETZT AKTIV</th>
              <th>AKTIONEN</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="store.telegramUsers.length === 0">
              <td colspan="7" class="muted text-center" style="padding: 24px;">
                Keine Einträge vorhanden.
              </td>
            </tr>
            <tr v-for="u in store.telegramUsers" :key="u.id">
              <td class="mono hide-sm">
                {{ u.telegram_id || 'wird bei Nachricht verknüpft' }}
              </td>
              <td>
                <strong>{{ u.username ? `@${u.username}` : '-' }}</strong>
                <span v-if="u.first_name" class="muted"> ({{ u.first_name }})</span>
              </td>
              <td class="mono">
                <strong v-if="u.role === 'admin'" style="color: #38bdf8;">ADMIN</strong>
                <span v-else>Nutzer</span>
              </td>
              <td>
                <span v-if="Number(u.is_allowed) === 1" class="status-tag live">FREIGESCHALTET</span>
                <span v-else-if="Number(u.is_allowed) === 0" class="status-tag polling">
                  {{ store.settings?.telegram_access_mode === 'public' ? 'PUBLIC-GAST' : 'ANFRAGE OFFEN' }}
                </span>
                <span v-else class="status-tag danger">GESPERRT</span>
              </td>
              <td class="mono muted hide-sm" style="font-size:11px;">
                {{ u.note || '-' }}
              </td>
              <td class="mono muted hide-md" style="font-size:11px;">
                {{ (u.last_seen_at || '').replace('T', ' ') || '-' }}
              </td>
              <td>
                <div class="action-group">
                  <button
                    v-if="Number(u.is_allowed) !== 1"
                    type="button"
                    class="sm primary"
                    @click="updateUserStatus(u, 1, u.role)"
                  >
                    Freischalten
                  </button>
                  <button
                    v-else
                    type="button"
                    class="sm"
                    @click="updateUserStatus(u, -1, 'user')"
                  >
                    Sperren
                  </button>

                  <button
                    v-if="u.role !== 'admin'"
                    type="button"
                    class="sm"
                    @click="updateUserStatus(u, 1, 'admin')"
                  >
                    → Admin
                  </button>
                  <button
                    v-else
                    type="button"
                    class="sm"
                    @click="updateUserStatus(u, 1, 'user')"
                  >
                    → Nutzer
                  </button>

                  <button
                    type="button"
                    class="sm danger"
                    @click="deleteUser(u.id)"
                  >
                    X
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
    alert(json.message || "Report gesendet!");
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
