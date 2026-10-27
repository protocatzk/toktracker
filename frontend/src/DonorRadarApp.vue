<template>
  <div class="toktracker-radar-app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <div class="brand-block">
          <div class="brand-logo-wrap">
            <img :src="'/pictures/bot_avatar.jpg'" alt="toktracker" class="brand-logo" onerror="this.src='/static/avatar_default.png'" />
            <span class="brand-radar-indicator"></span>
          </div>
          <div class="brand-text">
            <div class="brand-title-row">
              <h1 class="brand-title">toktracker</h1>
              <span class="brand-badge-radar">SPENDER-RADAR</span>
            </div>
            <span class="brand-subtitle">Whale Intelligence, Cross-Streamer &amp; Frontenwechsler</span>
          </div>
        </div>

        <nav class="nav-links">
          <a href="/admin" class="nav-pill">
            <span class="icon">📊</span> Admin-Panel
          </a>
          <a href="/chat-intelligence" class="nav-pill">
            <span class="icon">💬</span> Chat-Intelligence
          </a>
          <a href="/public" target="_blank" class="nav-pill">
            <span class="icon">🌐</span> Public Radar ↗
          </a>
          <a href="/miniapp" target="_blank" class="nav-pill">
            <span class="icon">📱</span> Mini-App
          </a>
          <button type="button" class="btn-theme-toggle" @click="toggleTheme">
            {{ currentTheme === 'dark' ? '🌙 Dark' : '☀️ Light' }}
          </button>
        </nav>
      </div>
    </header>

    <!-- Whale Alert Ticker Bar -->
    <div class="whale-ticker-bar" v-if="whaleAlerts.length > 0">
      <div class="ticker-badge">
        <span class="whale-icon">🐋</span>
        <span>WHALE-ALERT:</span>
      </div>
      <div class="ticker-content">
        <div class="ticker-items">
          <span
            v-for="alert in whaleAlerts"
            :key="alert.id"
            class="ticker-item"
            @click="openDossier(alert.sender_username)"
          >
            <strong>@{{ alert.sender_username }}</strong>
            <span class="gift-text">schenkte {{ alert.gift_name }}</span>
            <span class="coins-badge">+{{ formatNumber(alert.total_coins) }} 💎</span>
            <span class="streamer-sub">an @{{ alert.streamer_username }}</span>
          </span>
        </div>
      </div>
      <div class="ticker-controls">
        <button
          type="button"
          class="btn-audio"
          :class="{ active: audioEnabled }"
          @click="toggleAudio"
          :title="audioEnabled ? 'Sound aktiviert' : 'Sound stummschalten'"
        >
          {{ audioEnabled ? '🔊 Sound An' : '🔇 Stumm' }}
        </button>
      </div>
    </div>

    <!-- Main Container -->
    <main class="app-body">
      <!-- KPI Cards Grid -->
      <section class="radar-kpi-grid">
        <div class="kpi-card card-whales" @click="setTierFilter('whale')">
          <div class="kpi-top">
            <span class="kpi-icon">🐋</span>
            <span class="kpi-label">Whales (&ge; 10k)</span>
          </div>
          <div class="kpi-value text-purple">{{ formatNumber(kpis.whales_count) }}</div>
          <div class="kpi-sub">Top Spender &ge; 10.000 Coins</div>
        </div>

        <div class="kpi-card card-sharks" @click="setTierFilter('shark')">
          <div class="kpi-top">
            <span class="kpi-icon">🦈</span>
            <span class="kpi-label">Sharks (&ge; 2.5k)</span>
          </div>
          <div class="kpi-value text-cyan">{{ formatNumber(kpis.sharks_count) }}</div>
          <div class="kpi-sub">Starke Supporter &ge; 2.500 Coins</div>
        </div>

        <div class="kpi-card card-dolphins" @click="setTierFilter('dolphin')">
          <div class="kpi-top">
            <span class="kpi-icon">🐬</span>
            <span class="kpi-label">Dolphins (&ge; 500)</span>
          </div>
          <div class="kpi-value text-emerald">{{ formatNumber(kpis.dolphins_count) }}</div>
          <div class="kpi-sub">Regelmäßige Spender &ge; 500 Coins</div>
        </div>

        <div class="kpi-card card-cross" @click="crossOnly = !crossOnly; loadDonors()">
          <div class="kpi-top">
            <span class="kpi-icon">🔀</span>
            <span class="kpi-label">Cross-Streamer</span>
          </div>
          <div class="kpi-value text-amber">{{ formatNumber(kpis.cross_streamers_count) }}</div>
          <div class="kpi-sub">Spenden an &ge; 2 Streamer</div>
        </div>

        <div class="kpi-card card-vip" @click="vipOnly = !vipOnly; loadDonors()">
          <div class="kpi-top">
            <span class="kpi-icon">⭐</span>
            <span class="kpi-label">VIP-Watchlist</span>
          </div>
          <div class="kpi-value text-gold">{{ formatNumber(kpis.vip_donors_count) }}</div>
          <div class="kpi-sub">Gemarkte VIP-Profile</div>
        </div>

        <div class="kpi-card card-chat">
          <div class="kpi-top">
            <span class="kpi-icon">💬</span>
            <span class="kpi-label">Chat-Logs</span>
          </div>
          <div class="kpi-value text-blue">{{ formatNumber(chatLogsCount) }}</div>
          <div class="kpi-sub">Erfasste Live-Nachrichten</div>
        </div>
      </section>

      <!-- View Selector Tabs -->
      <div class="hub-tabs-row">
        <div class="hub-pills">
          <button
            type="button"
            :class="['hub-pill', { active: currentView === 'radar' }]"
            @click="currentView = 'radar'"
          >
            🎯 Spender-Radar &amp; Live-Stream
          </button>
          <button
            type="button"
            :class="['hub-pill', { active: currentView === 'loyalty' }]"
            @click="currentView = 'loyalty'; loadLoyaltyData()"
          >
            🔄 Loyalty &amp; Frontenwechsler
            <span class="badge-mini" v-if="loyaltySwitchers.length > 0">{{ loyaltySwitchers.length }}</span>
          </button>
        </div>

        <div class="toolbar-right">
          <div class="period-pills">
            <button
              v-for="p in ['today', '24h', '7d', '30d', 'all']"
              :key="p"
              type="button"
              :class="['period-btn', { active: period === p }]"
              @click="setPeriod(p)"
            >
              {{ p.toUpperCase() }}
            </button>
          </div>

          <button
            type="button"
            class="btn-refresh"
            @click="refreshAll"
            :disabled="isLoading"
            title="Daten neu laden"
          >
            <span :class="['refresh-icon', { spinning: isLoading }]">🔄</span>
            <span>Aktualisieren</span>
          </button>
        </div>
      </div>

      <!-- VIEW 1: Spender-Radar & Chatlog Split Layout -->
      <div v-show="currentView === 'radar'" class="radar-split-grid">
        <!-- Donors Table Area -->
        <div class="donors-panel">
          <!-- Filter Controls -->
          <div class="filter-bar">
            <div class="search-input-wrap">
              <span class="search-icon">🔍</span>
              <input
                v-model="searchQuery"
                type="search"
                placeholder="Spender nach Username / Nickname filtern..."
                class="modern-input-search"
                @input="debouncedSearch"
              />
            </div>

            <div class="filter-group">
              <select v-model="selectedStreamerId" @change="loadDonors" class="modern-select">
                <option value="">Alle Streamer</option>
                <option v-for="s in streamerOptions" :key="s.id" :value="s.id">
                  @{{ s.username }} ({{ s.display_name || s.username }})
                </option>
              </select>

              <select v-model="selectedTier" @change="loadDonors" class="modern-select">
                <option value="">Alle Tiers</option>
                <option value="whale">🐋 Whale (&ge; 10k)</option>
                <option value="shark">🦈 Shark (&ge; 2.5k)</option>
                <option value="dolphin">🐬 Dolphin (&ge; 500)</option>
                <option value="minnow">🐟 Minnow (&lt; 500)</option>
              </select>

              <label class="checkbox-pill" :class="{ checked: crossOnly }">
                <input type="checkbox" v-model="crossOnly" @change="loadDonors" />
                <span>🔀 Cross-Streamer</span>
              </label>

              <label class="checkbox-pill" :class="{ checked: vipOnly }">
                <input type="checkbox" v-model="vipOnly" @change="loadDonors" />
                <span>⭐ Nur VIPs</span>
              </label>
            </div>
          </div>

          <!-- Donors Table -->
          <div class="modern-card table-card">
            <div class="table-header-info">
              <div class="title-with-count">
                <h3>Top Spender-Radar</h3>
                <span class="count-pill">{{ formatNumber(donorsList.length) }} Spender</span>
              </div>
              <div class="auto-refresh-toggle">
                <label>
                  <input type="checkbox" v-model="autoRefresh" />
                  <span>Auto-Refresh (10s)</span>
                </label>
              </div>
            </div>

            <div class="table-responsive">
              <table class="modern-table">
                <thead>
                  <tr>
                    <th class="rank-col">RANG</th>
                    <th>SPENDER</th>
                    <th>TIER</th>
                    <th class="num-col">DIAMONDS</th>
                    <th class="num-col">NETTO (€)</th>
                    <th>HAUPT-STREAMER</th>
                    <th>LETZTES GESCHENK</th>
                    <th class="actions-col">AKTIONEN</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="donorsList.length === 0 && !isLoading">
                    <td colspan="8" class="empty-cell">
                      Keine Spender für die gewählten Filterkriterien gefunden.
                    </td>
                  </tr>

                  <tr
                    v-for="(donor, idx) in donorsList"
                    :key="donor.sender_username"
                    class="donor-row"
                    @click="openDossier(donor.sender_username)"
                  >
                    <td class="rank-col">
                      <span :class="['rank-pill', getRankClass(idx + 1)]">
                        #{{ idx + 1 }}
                      </span>
                    </td>

                    <td>
                      <div class="donor-profile">
                        <div class="donor-avatar-wrap">
                          <img
                            :src="'/static/avatar_default.png'"
                            class="donor-avatar"
                            alt="Avatar"
                          />
                          <button
                            type="button"
                            class="star-btn"
                            :class="{ active: donor.is_vip }"
                            @click.stop="toggleVip(donor.sender_username)"
                            :title="donor.is_vip ? 'VIP entfernen' : 'Als VIP markieren'"
                          >
                            {{ donor.is_vip ? '★' : '☆' }}
                          </button>
                        </div>
                        <div class="donor-names">
                          <strong class="donor-username">@{{ donor.sender_username }}</strong>
                          <span class="donor-nickname" v-if="donor.sender_nickname">
                            {{ donor.sender_nickname }}
                          </span>
                        </div>
                      </div>
                    </td>

                    <td>
                      <div class="tier-badges-wrap">
                        <span :class="['tier-pill', 'tier-' + (donor.tier || 'minnow')]">
                          {{ getTierLabel(donor.tier) }}
                        </span>
                        <span v-if="donor.streamer_count && donor.streamer_count >= 2" class="cross-badge" title="Spendet an mehrere Streamer">
                          🔀 Cross ({{ donor.streamer_count }})
                        </span>
                      </div>
                    </td>

                    <td class="num-col font-bold text-cyan">
                      {{ formatNumber(donor.total_coins || donor.total_diamonds) }} 💎
                    </td>

                    <td class="num-col">
                      <div class="revenue-stack">
                        <span class="revenue-eur">{{ formatEUR(donor.eur_net) }}</span>
                        <span class="revenue-usd">{{ formatUSD(donor.usd_net) }}</span>
                      </div>
                    </td>

                    <td>
                      <span class="streamer-pill" v-if="donor.primary_streamer">
                        @{{ donor.primary_streamer }}
                      </span>
                      <span class="muted" v-else>-</span>
                    </td>

                    <td>
                      <span class="time-sub">{{ formatTime(donor.last_gift_time || donor.last_seen_at) }}</span>
                    </td>

                    <td class="actions-col" @click.stop>
                      <button
                        type="button"
                        class="btn-dossier"
                        @click="openDossier(donor.sender_username)"
                      >
                        Dossier ↗
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Live Chat & Whale Stream Side Panel -->
        <div class="chat-stream-panel">
          <div class="modern-card chat-card">
            <div class="chat-header">
              <div class="chat-title-wrap">
                <span class="live-dot-pulse"></span>
                <h4>Live Stream Feed</h4>
              </div>

              <div class="chat-actions">
                <label class="toggle-whale-chat">
                  <input type="checkbox" v-model="whaleOnlyChat" />
                  <span>Nur Whales</span>
                </label>
                <button
                  type="button"
                  class="btn-pause"
                  @click="chatPaused = !chatPaused"
                >
                  {{ chatPaused ? '▶️ Weiter' : '⏸ Pause' }}
                </button>
              </div>
            </div>

            <div class="chat-messages" ref="chatMessagesContainer">
              <div v-if="filteredChatLogs.length === 0" class="chat-empty">
                Warte auf eingehende Chat-Nachrichten und Geschenke...
              </div>

              <div
                v-for="msg in filteredChatLogs"
                :key="msg.id"
                class="chat-msg"
                :class="{ 'is-whale': msg.is_whale, 'is-gift': msg.is_gift }"
                @click="openDossier(msg.sender_username)"
              >
                <div class="msg-header">
                  <span class="msg-time">{{ formatTimeOnly(msg.created_at) }}</span>
                  <strong class="msg-sender">@{{ msg.sender_username }}</strong>
                  <span class="msg-target">an @{{ msg.streamer_username }}</span>
                </div>
                <div class="msg-body">
                  <span v-if="msg.is_gift" class="gift-badge">
                    🎁 {{ msg.gift_name }} (+{{ formatNumber(msg.total_coins) }} 💎)
                  </span>
                  <span v-else class="msg-text">{{ msg.message }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- VIEW 2: Loyalty & Frontenwechsler Hub -->
      <div v-show="currentView === 'loyalty'" class="loyalty-hub-container">
        <!-- Control Bar -->
        <div class="loyalty-controls modern-card">
          <div class="controls-left">
            <span class="icon">🔄</span>
            <div>
              <strong>Frontenwechsler &amp; Loyalty Shift Radar</strong>
              <p class="muted">
                Identifiziert Supporter, die kürzlich ihren primär unterstützten Streamer gewechselt haben.
              </p>
            </div>
          </div>
          <div class="controls-right">
            <label for="loyaltyDaysSelect">Zeitfenster:</label>
            <select id="loyaltyDaysSelect" v-model="loyaltyDays" @change="loadLoyaltyData" class="modern-select">
              <option :value="7">Letzte 7 Tage</option>
              <option :value="14">Letzte 14 Tage (Standard)</option>
              <option :value="30">Letzte 30 Tage</option>
            </select>
            <button type="button" class="btn-primary sm" @click="loadLoyaltyData">
              Neu berechnen
            </button>
          </div>
        </div>

        <div class="loyalty-grid">
          <!-- Switchers List -->
          <div class="modern-card switchers-card">
            <div class="card-header-bar">
              <h4>Gefundene Frontenwechsler</h4>
              <span class="count-pill">{{ loyaltySwitchers.length }} gewechselt</span>
            </div>

            <div class="table-responsive">
              <table class="modern-table">
                <thead>
                  <tr>
                    <th>SPENDER</th>
                    <th>VON STREAMER</th>
                    <th>NEUER HAUPT-STREAMER</th>
                    <th class="num-col">TRANSFERIERTE COINS</th>
                    <th class="num-col">SHIFT-QUOTE</th>
                    <th>AKTION</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="loyaltySwitchers.length === 0 && !isLoyaltyLoading">
                    <td colspan="6" class="empty-cell">
                      Keine signifikanten Frontenwechsel im gewählten Zeitraum festgestellt.
                    </td>
                  </tr>
                  <tr
                    v-for="sw in loyaltySwitchers"
                    :key="sw.username"
                    class="donor-row"
                    @click="openDossier(sw.username)"
                  >
                    <td>
                      <strong class="donor-username">@{{ sw.username }}</strong>
                    </td>
                    <td>
                      <span class="streamer-pill old">@{{ sw.previous_streamer }}</span>
                    </td>
                    <td>
                      <span class="streamer-pill new">@{{ sw.new_streamer }}</span>
                    </td>
                    <td class="num-col font-bold text-cyan">
                      {{ formatNumber(sw.recent_coins) }} 💎
                    </td>
                    <td class="num-col font-bold text-amber">
                      {{ sw.shift_percentage }}%
                    </td>
                    <td>
                      <button type="button" class="btn-dossier" @click.stop="openDossier(sw.username)">
                        Dossier
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Overlap Matrix -->
          <div class="modern-card matrix-card">
            <div class="card-header-bar">
              <h4>Streamer-Überschneidungsmatrix</h4>
              <span class="count-pill">{{ overlapPairs.length }} Paare</span>
            </div>

            <div class="table-responsive">
              <table class="modern-table">
                <thead>
                  <tr>
                    <th>STREAMER A</th>
                    <th>STREAMER B</th>
                    <th class="num-col">GEMEINSAME SPENDER</th>
                    <th class="num-col">GEMEINSAME COINS</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="overlapPairs.length === 0 && !isLoyaltyLoading">
                    <td colspan="4" class="empty-cell">
                      Keine Überschneidungspaare gefunden.
                    </td>
                  </tr>
                  <tr v-for="(pair, idx) in overlapPairs" :key="idx">
                    <td><strong>@{{ pair.streamer_a }}</strong></td>
                    <td><strong>@{{ pair.streamer_b }}</strong></td>
                    <td class="num-col font-bold text-purple">
                      {{ formatNumber(pair.shared_donors_count) }} Spender
                    </td>
                    <td class="num-col font-bold text-cyan">
                      {{ formatNumber(pair.shared_coins) }} 💎
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Dossier Modal -->
    <div v-if="selectedDossierUser" class="modal-backdrop" @click.self="selectedDossierUser = null">
      <div class="modal-dialog dossier-modal">
        <div class="modal-header">
          <div class="dossier-title-wrap">
            <img :src="'/static/avatar_default.png'" class="modal-avatar" alt="Avatar" />
            <div>
              <div class="modal-title-row">
                <h3 class="modal-title">@{{ selectedDossierUser }}</h3>
                <span :class="['tier-pill', 'tier-' + (dossierData?.donor?.tier || 'minnow')]">
                  {{ getTierLabel(dossierData?.donor?.tier) }}
                </span>
                <button
                  type="button"
                  class="star-btn-modal"
                  :class="{ active: dossierData?.donor?.is_vip }"
                  @click="toggleVip(selectedDossierUser)"
                >
                  {{ dossierData?.donor?.is_vip ? '★ VIP' : '☆ Als VIP markieren' }}
                </button>
              </div>
              <span class="modal-subtitle" v-if="dossierData?.donor?.sender_nickname">
                Nickname: {{ dossierData.donor.sender_nickname }}
              </span>
            </div>
          </div>
          <button type="button" class="close-btn" @click="selectedDossierUser = null">✕</button>
        </div>

        <div class="modal-body" v-if="dossierLoading">
          <div class="loading-state">
            <span class="spinning">🔄</span>
            <p>Lade Spender-Dossier...</p>
          </div>
        </div>

        <div class="modal-body" v-else-if="dossierData">
          <!-- Summary Cards -->
          <div class="dossier-summary-grid">
            <div class="compact-card">
              <span class="compact-label">GESAMT GESPENDET</span>
              <strong class="compact-val text-cyan">
                {{ formatNumber(dossierData.donor?.total_diamonds || dossierData.donor?.total_coins) }} 💎
              </strong>
            </div>
            <div class="compact-card">
              <span class="compact-label">NETTO WERT (EUR)</span>
              <strong class="compact-val text-emerald">
                {{ formatEUR(dossierData.donor?.eur_net) }}
              </strong>
            </div>
            <div class="compact-card">
              <span class="compact-label">UNTERSTÜTZTE STREAMER</span>
              <strong class="compact-val text-purple">
                {{ dossierData.streamers_supported?.length || 1 }} Streamer
              </strong>
            </div>
            <div class="compact-card">
              <span class="compact-label">ERSTMALS GESEHEN</span>
              <strong class="compact-val">
                {{ formatTime(dossierData.donor?.first_seen_at) }}
              </strong>
            </div>
          </div>

          <!-- CRM Notes & Tags -->
          <div class="crm-section modern-card">
            <h4>CRM-Notizen &amp; Kennzeichnung</h4>
            <div class="tags-input-row">
              <span v-for="tag in currentTags" :key="tag" class="tag-pill">
                {{ tag }}
                <button type="button" class="tag-remove" @click="removeTag(tag)">×</button>
              </span>
              <input
                v-model="newTagInput"
                type="text"
                placeholder="+ Tag hinzufügen (Enter)..."
                class="tag-input"
                @keydown.enter.prevent="addTag"
              />
            </div>

            <textarea
              v-model="crmNotes"
              rows="3"
              class="notes-textarea"
              placeholder="Notizen zu diesem Spender hinterlegen (z.B. Vorlieben, Streamer-Treue, Event-Zusagen)..."
            ></textarea>

            <div class="crm-actions">
              <button
                type="button"
                class="btn-primary sm"
                :disabled="crmSaving"
                @click="saveCrm"
              >
                {{ crmSaving ? 'Speichere...' : 'CRM-Daten speichern' }}
              </button>
            </div>
          </div>

          <!-- Streamers Supported Distribution -->
          <div class="section-block" style="margin-top: 20px;">
            <h4>Streamer-Verteilung</h4>
            <div class="table-responsive modal-table-wrap">
              <table class="modal-table">
                <thead>
                  <tr>
                    <th>STREAMER</th>
                    <th class="num-col">COINS GESPENDET</th>
                    <th class="num-col">ANTEIL</th>
                    <th>LETZTES GESCHENK</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="st in dossierData.streamers_supported" :key="st.streamer_username">
                    <td><strong>@{{ st.streamer_username }}</strong></td>
                    <td class="num-col font-bold text-cyan">{{ formatNumber(st.coins) }} 💎</td>
                    <td class="num-col">{{ st.percentage }}%</td>
                    <td><span class="time-sub">{{ formatTime(st.last_gift_at) }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Top Gifts -->
          <div class="section-block" style="margin-top: 20px;">
            <h4>Häufigste Geschenke</h4>
            <div class="table-responsive modal-table-wrap">
              <table class="modal-table">
                <thead>
                  <tr>
                    <th>GESCHENK</th>
                    <th class="num-col">ANZAHL</th>
                    <th class="num-col">COINS GESAMT</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="g in dossierData.top_gifts" :key="g.gift_name">
                    <td><strong>🎁 {{ g.gift_name }}</strong></td>
                    <td class="num-col">{{ formatNumber(g.count) }}x</td>
                    <td class="num-col font-bold text-cyan">{{ formatNumber(g.total_coins) }} 💎</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn-close" @click="selectedDossierUser = null">Schließen</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { formatEUR, formatUSD, formatNumber } from "./utils/formatters";

// State
const period = ref("all");
const currentView = ref<"radar" | "loyalty">("radar");
const isLoading = ref(false);
const autoRefresh = ref(false);
const currentTheme = ref("dark");

// Filter State
const searchQuery = ref("");
const selectedStreamerId = ref<string | number>("");
const selectedTier = ref("");
const crossOnly = ref(false);
const vipOnly = ref(false);

// KPI State
const kpis = ref({
  whales_count: 0,
  sharks_count: 0,
  dolphins_count: 0,
  cross_streamers_count: 0,
  vip_donors_count: 0,
  total_donors: 0,
  total_coins: 0,
  total_eur_net: 0,
  total_usd_net: 0,
});

const donorsList = ref<any[]>([]);
const streamerOptions = ref<any[]>([]);
const chatLogsCount = ref(0);

// Whale Alerts & Sound
const whaleAlerts = ref<any[]>([]);
const audioEnabled = ref(false);
let audioContext: AudioContext | null = null;
const seenAlertIds = new Set<number>();

// Live Chat Stream
const chatLogs = ref<any[]>([]);
const whaleOnlyChat = ref(false);
const chatPaused = ref(false);
const chatMessagesContainer = ref<HTMLElement | null>(null);

// Loyalty State
const loyaltyDays = ref(14);
const isLoyaltyLoading = ref(false);
const loyaltySwitchers = ref<any[]>([]);
const overlapPairs = ref<any[]>([]);

// Dossier Modal State
const selectedDossierUser = ref<string | null>(null);
const dossierLoading = ref(false);
const dossierData = ref<any>(null);
const currentTags = ref<string[]>([]);
const newTagInput = ref("");
const crmNotes = ref("");
const crmSaving = ref(false);

let refreshTimer: any = null;
let whaleTimer: any = null;
let chatTimer: any = null;

const filteredChatLogs = computed(() => {
  if (whaleOnlyChat.value) {
    return chatLogs.value.filter((m) => m.is_whale || (m.total_coins && m.total_coins >= 2500));
  }
  return chatLogs.value;
});

// Methods
function setPeriod(p: string) {
  period.value = p;
  loadDonors();
}

function setTierFilter(tier: string) {
  selectedTier.value = selectedTier.value === tier ? "" : tier;
  loadDonors();
}

function getTierLabel(tier?: string) {
  switch ((tier || "").toLowerCase()) {
    case "whale": return "🐋 Whale";
    case "shark": return "🦈 Shark";
    case "dolphin": return "🐬 Dolphin";
    default: return "🐟 Minnow";
  }
}

function getRankClass(rank: number) {
  if (rank === 1) return "rank-top-1";
  if (rank === 2) return "rank-top-2";
  if (rank === 3) return "rank-top-3";
  return "";
}

function formatTime(str?: string) {
  if (!str) return "-";
  try {
    const d = new Date(str);
    return d.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return str;
  }
}

function formatTimeOnly(str?: string) {
  if (!str) return "";
  try {
    const d = new Date(str);
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

async function loadDonors() {
  isLoading.value = true;
  try {
    const params = new URLSearchParams({
      period: period.value,
      limit: "150",
    });
    if (selectedTier.value) params.append("min_tier", selectedTier.value);
    if (selectedStreamerId.value) params.append("streamer_id", String(selectedStreamerId.value));
    if (crossOnly.value) params.append("cross_streamer_only", "true");
    if (vipOnly.value) params.append("vip_only", "true");
    if (searchQuery.value.trim()) params.append("search", searchQuery.value.trim());

    const res = await fetch(`/api/donor-radar?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const data = json.data || {};

    if (data.kpis) {
      kpis.value = { ...kpis.value, ...data.kpis };
    }
    donorsList.value = data.donors || [];
    if (data.streamers && data.streamers.length > 0) {
      streamerOptions.value = data.streamers;
    }
  } catch (err) {
    console.error("Fehler beim Laden des Spender-Radars:", err);
  } finally {
    isLoading.value = false;
  }
}

let debounceTimer: any = null;
function debouncedSearch() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    loadDonors();
  }, 350);
}

async function toggleVip(username: string) {
  try {
    const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(username)}/toggle-vip`, {
      method: "POST",
    });
    if (res.ok) {
      const target = donorsList.value.find((d) => d.sender_username === username);
      if (target) target.is_vip = !target.is_vip;
      if (dossierData.value?.donor?.sender_username === username) {
        dossierData.value.donor.is_vip = !dossierData.value.donor.is_vip;
      }
    }
  } catch (err) {
    console.error("Fehler beim Umschalten des VIP-Status:", err);
  }
}

async function loadWhaleAlerts() {
  try {
    const res = await fetch("/api/donor-radar/whale-alerts?min_coins=2500&limit=15");
    if (res.ok) {
      const json = await res.json();
      const alerts = json.alerts || [];
      // Play chime if new whale alert arrives
      alerts.forEach((a: any) => {
        if (!seenAlertIds.has(a.id)) {
          seenAlertIds.add(a.id);
          if (audioEnabled.value) {
            playWhaleSound();
          }
        }
      });
      whaleAlerts.value = alerts;
    }
  } catch (err) {
    console.error("Fehler whale alerts:", err);
  }
}

async function loadChatLogs() {
  if (chatPaused.value) return;
  try {
    const res = await fetch("/api/chat-logs?limit=40");
    if (res.ok) {
      const json = await res.json();
      chatLogs.value = json.logs || [];
      chatLogsCount.value = json.total || chatLogs.value.length;
    }
  } catch (err) {
    console.error("Fehler chat logs:", err);
  }
}

async function loadLoyaltyData() {
  isLoyaltyLoading.value = true;
  try {
    const res = await fetch(
      `/api/donor-radar/loyalty-and-overlap?days_recent=${loyaltyDays.value}&min_coins=50`
    );
    if (res.ok) {
      const json = await res.json();
      const d = json.data || {};
      loyaltySwitchers.value = d.switchers || [];
      overlapPairs.value = d.overlap_matrix || [];
    }
  } catch (err) {
    console.error("Fehler loyalty data:", err);
  } finally {
    isLoyaltyLoading.value = false;
  }
}

async function openDossier(username: string) {
  selectedDossierUser.value = username;
  dossierLoading.value = true;
  dossierData.value = null;
  currentTags.value = [];
  crmNotes.value = "";

  try {
    const res = await fetch(`/api/donor-radar/donors/${encodeURIComponent(username)}`);
    if (res.ok) {
      const json = await res.json();
      dossierData.value = json.data;
      if (dossierData.value?.crm) {
        currentTags.value = dossierData.value.crm.tags || [];
        crmNotes.value = dossierData.value.crm.notes || "";
      }
    }
  } catch (err) {
    console.error("Fehler beim Laden des Dossiers:", err);
  } finally {
    dossierLoading.value = false;
  }
}

function addTag() {
  const val = newTagInput.value.trim();
  if (val && !currentTags.value.includes(val)) {
    currentTags.value.push(val);
    newTagInput.value = "";
  }
}

function removeTag(tag: string) {
  currentTags.value = currentTags.value.filter((t) => t !== tag);
}

async function saveCrm() {
  if (!selectedDossierUser.value) return;
  crmSaving.value = true;
  try {
    await fetch(`/api/donor-radar/donors/${encodeURIComponent(selectedDossierUser.value)}/crm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        is_vip: Boolean(dossierData.value?.donor?.is_vip),
        tags: currentTags.value,
        notes: crmNotes.value.trim(),
      }),
    });
    alert("CRM-Notizen erfolgreich gespeichert!");
  } catch (err) {
    alert("Fehler beim Speichern: " + err);
  } finally {
    crmSaving.value = false;
  }
}

function toggleAudio() {
  audioEnabled.value = !audioEnabled.value;
  if (audioEnabled.value && !audioContext) {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      audioContext = new AudioCtx();
    } catch {}
  }
}

function playWhaleSound() {
  try {
    if (!audioContext) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      audioContext = new AudioCtx();
    }
    if (audioContext && audioContext.state === "suspended") {
      audioContext.resume();
    }
    if (!audioContext) return;

    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, audioContext.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, audioContext.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.2, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4);
    osc.connect(gain);
    gain.connect(audioContext.destination);
    osc.start();
    osc.stop(audioContext.currentTime + 0.4);
  } catch {}
}

function toggleTheme() {
  const next = currentTheme.value === "light" ? "dark" : "light";
  currentTheme.value = next;
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("toktracker_theme", next);
  } catch {}
}

function refreshAll() {
  loadDonors();
  loadWhaleAlerts();
  loadChatLogs();
  if (currentView.value === "loyalty") {
    loadLoyaltyData();
  }
}

onMounted(() => {
  try {
    currentTheme.value = localStorage.getItem("toktracker_theme") || "dark";
    document.documentElement.setAttribute("data-theme", currentTheme.value);
  } catch {}

  loadDonors();
  loadWhaleAlerts();
  loadChatLogs();

  whaleTimer = setInterval(loadWhaleAlerts, 6000);
  chatTimer = setInterval(loadChatLogs, 3500);
  refreshTimer = setInterval(() => {
    if (autoRefresh.value) {
      loadDonors();
    }
  }, 10000);
});

onUnmounted(() => {
  clearInterval(whaleTimer);
  clearInterval(chatTimer);
  clearInterval(refreshTimer);
});
</script>

<style scoped>
.toktracker-radar-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-body, #090d16);
  color: var(--text-main, #f1f5f9);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Header */
.app-header {
  background: rgba(15, 21, 35, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 12px 24px;
}

.header-inner {
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-logo-wrap {
  position: relative;
}

.brand-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  object-fit: cover;
}

.brand-radar-indicator {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #a855f7;
  box-shadow: 0 0 8px #a855f7;
}

.brand-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-title {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: #ffffff;
  margin: 0;
}

.brand-badge-radar {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.8px;
  padding: 2px 7px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.3), rgba(126, 34, 206, 0.4));
  border: 1px solid rgba(168, 85, 247, 0.5);
  color: #d8b4fe;
}

.brand-subtitle {
  font-size: 11.5px;
  color: #94a3b8;
  display: block;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s ease;
}

.nav-pill:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.2);
}

.btn-theme-toggle {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-theme-toggle:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

/* Whale Ticker Bar */
.whale-ticker-bar {
  background: linear-gradient(90deg, rgba(147, 51, 234, 0.2), rgba(15, 21, 35, 0.95));
  border-bottom: 1px solid rgba(168, 85, 247, 0.35);
  padding: 8px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
}

.ticker-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 800;
  color: #d8b4fe;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.ticker-content {
  flex: 1;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}

.ticker-content::-webkit-scrollbar {
  display: none;
}

.ticker-items {
  display: inline-flex;
  gap: 20px;
}

.ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ticker-item:hover {
  background: rgba(168, 85, 247, 0.2);
  border-color: rgba(168, 85, 247, 0.5);
}

.gift-text {
  color: #cbd5e1;
}

.coins-badge {
  font-weight: 800;
  color: #38bdf8;
}

.streamer-sub {
  color: #94a3b8;
  font-size: 11px;
}

.btn-audio {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #94a3b8;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.btn-audio.active {
  background: rgba(168, 85, 247, 0.25);
  border-color: #a855f7;
  color: #d8b4fe;
}

/* App Body */
.app-body {
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 24px 60px;
  flex: 1;
}

/* Radar KPI Grid */
.radar-kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

@media (max-width: 1200px) {
  .radar-kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .radar-kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.kpi-card {
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(12px);
}

.kpi-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.kpi-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.kpi-icon {
  font-size: 16px;
}

.kpi-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #94a3b8;
}

.kpi-value {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 4px;
}

.kpi-sub {
  font-size: 11px;
  color: #64748b;
}

.text-purple { color: #c084fc; }
.text-cyan { color: #38bdf8; }
.text-emerald { color: #34d399; }
.text-amber { color: #fbbf24; }
.text-gold { color: #f59e0b; }
.text-blue { color: #60a5fa; }

/* Hub Tabs Row */
.hub-tabs-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}

.hub-pills {
  display: flex;
  gap: 8px;
}

.hub-pill {
  padding: 9px 18px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.hub-pill.active {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.25), rgba(56, 189, 248, 0.15));
  border-color: rgba(168, 85, 247, 0.5);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(168, 85, 247, 0.2);
}

.badge-mini {
  background: #a855f7;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 10px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.period-pills {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 2px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.period-btn {
  padding: 5px 12px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}

.period-btn.active {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Radar Split Grid */
.radar-split-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 20px;
}

@media (max-width: 1080px) {
  .radar-split-grid {
    grid-template-columns: 1fr;
  }
}

/* Filter Bar */
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 14px;
  font-size: 14px;
  opacity: 0.6;
}

.modern-input-search {
  width: 100%;
  padding: 10px 14px 10px 38px;
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #ffffff;
  font-size: 13px;
  outline: none;
  transition: all 0.2s ease;
}

.modern-input-search:focus {
  border-color: #a855f7;
  box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.2);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.modern-select {
  padding: 8px 14px;
  background: rgba(15, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  outline: none;
  cursor: pointer;
}

.checkbox-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
}

.checkbox-pill.checked {
  background: rgba(168, 85, 247, 0.15);
  border-color: rgba(168, 85, 247, 0.4);
  color: #d8b4fe;
}

.checkbox-pill input {
  accent-color: #a855f7;
}

/* Modern Card */
.modern-card {
  background: rgba(15, 21, 35, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  backdrop-filter: blur(14px);
  overflow: hidden;
}

.table-header-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.title-with-count {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-with-count h3 {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  font-size: 15px;
  font-weight: 800;
  color: #ffffff;
  margin: 0;
}

.count-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
}

.auto-refresh-toggle {
  font-size: 12px;
  color: #94a3b8;
}

.auto-refresh-toggle input {
  margin-right: 6px;
  accent-color: #a855f7;
}

/* Modern Table */
.table-responsive {
  overflow-x: auto;
}

.modern-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.modern-table th {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}

.modern-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.donor-row {
  cursor: pointer;
  transition: background 0.15s ease;
}

.donor-row:hover {
  background: rgba(168, 85, 247, 0.05);
}

.rank-col {
  text-align: center;
  width: 50px;
}

.rank-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 24px;
  padding: 0 6px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 700;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.06);
}

.rank-top-1 {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.35), rgba(217, 119, 6, 0.5));
  border: 1px solid rgba(245, 158, 11, 0.6);
  color: #fbbf24;
}

.rank-top-2 {
  background: linear-gradient(135deg, rgba(148, 163, 184, 0.3), rgba(100, 116, 139, 0.45));
  border: 1px solid rgba(148, 163, 184, 0.5);
  color: #f1f5f9;
}

.rank-top-3 {
  background: linear-gradient(135deg, rgba(180, 83, 9, 0.3), rgba(120, 53, 15, 0.45));
  border: 1px solid rgba(180, 83, 9, 0.5);
  color: #f97316;
}

.donor-profile {
  display: flex;
  align-items: center;
  gap: 10px;
}

.donor-avatar-wrap {
  position: relative;
}

.donor-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.star-btn {
  position: absolute;
  bottom: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: #1e293b;
  color: #94a3b8;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.star-btn.active {
  background: #f59e0b;
  color: #0f172a;
  border-color: #f59e0b;
}

.donor-names {
  display: flex;
  flex-direction: column;
}

.donor-username {
  font-size: 13.5px;
  color: #ffffff;
}

.donor-nickname {
  font-size: 11.5px;
  color: #94a3b8;
}

.tier-badges-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tier-pill {
  font-size: 11px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.4px;
}

.tier-whale {
  background: rgba(168, 85, 247, 0.2);
  border: 1px solid rgba(168, 85, 247, 0.5);
  color: #d8b4fe;
}

.tier-shark {
  background: rgba(56, 189, 248, 0.2);
  border: 1px solid rgba(56, 189, 248, 0.5);
  color: #7dd3fc;
}

.tier-dolphin {
  background: rgba(52, 211, 153, 0.2);
  border: 1px solid rgba(52, 211, 153, 0.5);
  color: #6ee7b7;
}

.tier-minnow {
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.25);
  color: #94a3b8;
}

.cross-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: #fbbf24;
}

.revenue-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.revenue-eur {
  font-weight: 800;
  color: #34d399;
}

.revenue-usd {
  font-size: 11px;
  color: #94a3b8;
}

.streamer-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
}

.streamer-pill.old {
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #f87171;
}

.streamer-pill.new {
  border: 1px solid rgba(52, 211, 153, 0.4);
  color: #34d399;
}

.time-sub {
  font-size: 11.5px;
  color: #94a3b8;
}

.actions-col {
  text-align: right;
}

.btn-dossier {
  padding: 5px 12px;
  border-radius: 6px;
  background: rgba(168, 85, 247, 0.15);
  border: 1px solid rgba(168, 85, 247, 0.35);
  color: #d8b4fe;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-dossier:hover {
  background: #a855f7;
  color: #ffffff;
}

.empty-cell {
  text-align: center;
  padding: 36px 16px;
  color: #94a3b8;
}

/* Chat Stream Side Panel */
.chat-card {
  display: flex;
  flex-direction: column;
  height: 680px;
}

.chat-header {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-title-wrap h4 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 800;
  color: #fff;
}

.live-dot-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 8px #ef4444;
  animation: pulseDot 1.6s infinite;
}

@keyframes pulseDot {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.chat-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-whale-chat {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.btn-pause {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  scrollbar-width: thin;
}

.chat-empty {
  text-align: center;
  color: #64748b;
  padding: 40px 10px;
  font-size: 12px;
}

.chat-msg {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.chat-msg:hover {
  background: rgba(255, 255, 255, 0.07);
}

.chat-msg.is-whale {
  background: rgba(168, 85, 247, 0.15);
  border-color: rgba(168, 85, 247, 0.35);
}

.chat-msg.is-gift {
  border-left: 3px solid #38bdf8;
}

.msg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.msg-time {
  font-size: 10px;
  color: #64748b;
}

.msg-sender {
  color: #ffffff;
  font-size: 11.5px;
}

.msg-target {
  font-size: 10.5px;
  color: #94a3b8;
}

.gift-badge {
  font-weight: 700;
  color: #38bdf8;
}

.msg-text {
  color: #cbd5e1;
}

/* Loyalty Hub Layout */
.loyalty-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}

.controls-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.controls-left .icon {
  font-size: 24px;
  padding: 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
}

.controls-left strong {
  display: block;
  font-size: 15px;
  color: #fff;
}

.controls-left p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #94a3b8;
}

.controls-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.loyalty-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 900px) {
  .loyalty-grid {
    grid-template-columns: 1fr;
  }
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.card-header-bar h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: #ffffff;
}

/* Dossier Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1050;
  padding: 16px;
}

.dossier-modal {
  background: #0f1523;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  width: 100%;
  max-width: 860px;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 24px rgba(168, 85, 247, 0.15);
}

.modal-header {
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dossier-title-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
}

.modal-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  border: 1px solid rgba(168, 85, 247, 0.4);
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  color: #fff;
}

.star-btn-modal {
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #94a3b8;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.star-btn-modal.active {
  background: #f59e0b;
  border-color: #f59e0b;
  color: #0f172a;
}

.modal-subtitle {
  font-size: 12px;
  color: #94a3b8;
  display: block;
}

.close-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  font-size: 18px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
  scrollbar-width: thin;
}

.dossier-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

@media (max-width: 640px) {
  .dossier-summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.compact-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.compact-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #94a3b8;
}

.compact-val {
  font-size: 18px;
  font-weight: 800;
  color: #ffffff;
}

.crm-section {
  padding: 16px;
  margin-bottom: 20px;
}

.crm-section h4 {
  margin: 0 0 10px;
  font-size: 13.5px;
  font-weight: 800;
  color: #ffffff;
}

.tags-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(168, 85, 247, 0.2);
  border: 1px solid rgba(168, 85, 247, 0.4);
  color: #d8b4fe;
  font-size: 11.5px;
  font-weight: 600;
}

.tag-remove {
  background: none;
  border: none;
  color: #d8b4fe;
  cursor: pointer;
  padding: 0;
  font-size: 14px;
}

.tag-input {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 4px 10px;
  color: #fff;
  font-size: 12px;
  outline: none;
}

.notes-textarea {
  width: 100%;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 10px;
  color: #ffffff;
  font-size: 12.5px;
  resize: vertical;
  box-sizing: border-box;
  font-family: inherit;
  outline: none;
}

.notes-textarea:focus {
  border-color: #a855f7;
}

.crm-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.btn-primary.sm {
  background: linear-gradient(135deg, #a855f7, #6366f1);
  border: none;
  border-radius: 8px;
  color: #ffffff;
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.section-block h4 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 800;
  color: #cbd5e1;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.modal-table-wrap {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  max-height: 220px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.modal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.modal-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #141c2e;
  padding: 8px 12px;
  color: #94a3b8;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  text-align: left;
}

.modal-table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.modal-footer {
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: flex-end;
}

.btn-close {
  padding: 7px 18px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #f1f5f9;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
</style>
