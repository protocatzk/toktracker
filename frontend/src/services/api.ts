import type {
  OverviewResponse,
  Streamer,
  Settings,
  Battle,
} from "../types";

class ApiService {
  private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    if (res.status === 401) {
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      throw new Error("Nicht authentifiziert (401)");
    }

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errJson = await res.json();
        detail = errJson.detail || errJson.message || detail;
      } catch {}
      throw new Error(detail);
    }

    return res.json() as Promise<T>;
  }

  // Dashboard Overview
  async getOverview(period = "today"): Promise<OverviewResponse> {
    return this.request<OverviewResponse>(`/api/overview?period=${encodeURIComponent(period)}`);
  }

  async getPublicOverview(period = "24h"): Promise<OverviewResponse> {
    return this.request<OverviewResponse>(`/api/public/overview?period=${encodeURIComponent(period)}`);
  }

  // Streamers
  async addStreamer(
    username: string,
    displayName?: string,
    startWorker = true,
    autoMonitor = true
  ): Promise<{ ok: boolean; streamer: Streamer }> {
    return this.request<{ ok: boolean; streamer: Streamer }>("/api/streamers", {
      method: "POST",
      body: JSON.stringify({
        username,
        display_name: displayName,
        start_worker: startWorker,
        auto_monitor: autoMonitor,
      }),
    });
  }

  async toggleWorker(streamerId: number): Promise<{ ok: boolean; message: string }> {
    return this.request<{ ok: boolean; message: string }>(`/api/streamers/${streamerId}/toggle`, {
      method: "POST",
    });
  }

  async refreshStreamer(streamerId: number): Promise<{ ok: boolean; message: string }> {
    return this.request<{ ok: boolean; message: string }>(`/api/streamers/${streamerId}/refresh`, {
      method: "POST",
    });
  }

  async deleteStreamer(streamerId: number): Promise<{ ok: boolean; message: string }> {
    return this.request<{ ok: boolean; message: string }>(`/api/streamers/${streamerId}`, {
      method: "DELETE",
    });
  }

  async getStreamerDetail(
    streamerId: number,
    period = "all"
  ): Promise<{
    streamer: Streamer;
    summary: any;
    gift_breakdown: any[];
    sessions: any[];
  }> {
    return this.request(`/api/streamers/${streamerId}?period=${encodeURIComponent(period)}`);
  }

  // Battles
  async getBattles(params: {
    streamerId?: string | number;
    period?: string;
    result?: string;
    mode?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ battles: Battle[]; total: number; rivals: any[] }> {
    const query = new URLSearchParams();
    if (params.streamerId) query.append("streamer_id", String(params.streamerId));
    if (params.period) query.append("period", params.period);
    if (params.result && params.result !== "ALL") query.append("result", params.result);
    if (params.mode && params.mode !== "ALL") query.append("mode", params.mode);
    if (params.search) query.append("search", params.search);
    if (params.limit) query.append("limit", String(params.limit));
    if (params.offset !== undefined) query.append("offset", String(params.offset));

    return this.request(`/api/battles?${query.toString()}`);
  }

  // Settings
  async updateSettings(settings: Partial<Settings>): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>("/api/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
  }

  // Telegram Users Whitelist
  async updateTelegramUser(
    identifier: string,
    isAllowed: number,
    role = "user"
  ): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>("/api/v1/telegram/users", {
      method: "POST",
      body: JSON.stringify({
        identifier: String(identifier),
        is_allowed: isAllowed,
        role,
      }),
    });
  }

  async deleteTelegramUser(recordId: number): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>(`/api/v1/telegram/users/${recordId}`, {
      method: "DELETE",
    });
  }

  // Manual Test Transaction
  async triggerTestGift(payload: {
    streamer_id: number;
    gift_name: string;
    diamond_count: number;
    repeat_count: number;
    sender_username: string;
  }): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>("/api/gifts/manual", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export const api = new ApiService();
