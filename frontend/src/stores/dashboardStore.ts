import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api } from "../services/api";
import type {
  OverviewTotals,
  Streamer,
  GiftEvent,
  Settings,
  TelegramUser,
  SystemStatus,
} from "../types";

export const useDashboardStore = defineStore("dashboard", () => {
  // State
  const period = ref<string>("all");
  const isLoading = ref<boolean>(false);
  const lastUpdated = ref<Date | null>(null);
  const error = ref<string | null>(null);

  const totals = ref<OverviewTotals>({
    streamer_count: 0,
    live_count: 0,
    total_coins: 0,
    eur_net: 0,
    usd_net: 0,
    eur_gross: 0,
    usd_gross: 0,
    gift_events_count: 0,
    total_gifts_sent: 0,
  });

  const streamers = ref<Streamer[]>([]);
  const recentGifts = ref<GiftEvent[]>([]);
  const telegramUsers = ref<TelegramUser[]>([]);
  const settings = ref<Settings | null>(null);
  const system = ref<SystemStatus | null>(null);

  const streamerFilter = ref<string>("");
  const giftFilter = ref<string>("");

  let pollTimer: ReturnType<typeof setTimeout> | null = null;

  // Getters
  const filteredStreamers = computed(() => {
    const q = streamerFilter.value.trim().toLowerCase();
    if (!q) return streamers.value;
    return streamers.value.filter((s) => {
      const u = (s.username || "").toLowerCase();
      const d = (s.display_name || "").toLowerCase();
      return u.includes(q) || d.includes(q);
    });
  });

  const filteredGifts = computed(() => {
    const q = giftFilter.value.trim().toLowerCase();
    if (!q) return recentGifts.value;
    return recentGifts.value.filter((g) => {
      return (
        (g.streamer_username || "").toLowerCase().includes(q) ||
        (g.sender_username || "").toLowerCase().includes(q) ||
        (g.sender_nickname || "").toLowerCase().includes(q) ||
        (g.gift_name || "").toLowerCase().includes(q)
      );
    });
  });

  const liveStreamersCount = computed(() => {
    return streamers.value.filter((s) => Boolean(s.is_live)).length;
  });

  const activeWorkersCount = computed(() => {
    return streamers.value.filter(
      (s) => s.worker_diagnostics?.is_running || s.is_tracking_active
    ).length;
  });

  // Actions
  async function loadOverview(silent = false) {
    if (!silent) isLoading.value = true;
    error.value = null;

    try {
      const data = await api.getOverview(period.value);
      totals.value = data.totals || totals.value;
      streamers.value = data.streamers || [];
      recentGifts.value = data.recent_gifts || [];
      telegramUsers.value = data.telegram_users || [];
      settings.value = data.settings || settings.value;
      system.value = data.system || system.value;
      lastUpdated.value = new Date();
    } catch (err: any) {
      error.value = err.message || "Fehler beim Laden der Übersichtsdaten";
      console.error("Dashboard error:", err);
    } finally {
      if (!silent) isLoading.value = false;
    }
  }

  function setPeriod(newPeriod: string) {
    if (period.value !== newPeriod) {
      period.value = newPeriod;
      loadOverview();
    }
  }

  async function toggleWorker(streamerId: number) {
    await api.toggleWorker(streamerId);
    await loadOverview(true);
  }

  async function refreshStreamer(streamerId: number) {
    await api.refreshStreamer(streamerId);
    await loadOverview(true);
  }

  async function deleteStreamer(streamerId: number) {
    await api.deleteStreamer(streamerId);
    await loadOverview(true);
  }

  async function addStreamer(
    username: string,
    displayName?: string,
    startWorker = true,
    autoMonitor = true
  ) {
    await api.addStreamer(username, displayName, startWorker, autoMonitor);
    await loadOverview(true);
  }

  async function updateSettings(newSettings: Partial<Settings>) {
    await api.updateSettings(newSettings);
    await loadOverview(true);
  }

  async function updateTelegramUser(identifier: string, isAllowed: number, role = "user") {
    await api.updateTelegramUser(identifier, isAllowed, role);
    await loadOverview(true);
  }

  async function deleteTelegramUser(recordId: number) {
    await api.deleteTelegramUser(recordId);
    await loadOverview(true);
  }

  // Auto Polling
  function startPolling() {
    stopPolling();
    const scheduleNext = () => {
      const delay = typeof document !== "undefined" && document.hidden ? 30000 : 5000;
      pollTimer = setTimeout(async () => {
        if (typeof document === "undefined" || !document.hidden) {
          await loadOverview(true);
        }
        scheduleNext();
      }, delay);
    };

    scheduleNext();

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }
  }

  function handleVisibilityChange() {
    if (!document.hidden) {
      loadOverview(true);
    }
  }

  function stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    }
  }

  return {
    period,
    isLoading,
    lastUpdated,
    error,
    totals,
    streamers,
    recentGifts,
    telegramUsers,
    settings,
    system,
    streamerFilter,
    giftFilter,
    filteredStreamers,
    filteredGifts,
    liveStreamersCount,
    activeWorkersCount,
    loadOverview,
    setPeriod,
    toggleWorker,
    refreshStreamer,
    deleteStreamer,
    addStreamer,
    updateSettings,
    updateTelegramUser,
    deleteTelegramUser,
    startPolling,
    stopPolling,
  };
});
