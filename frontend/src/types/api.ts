import { Streamer } from "./streamer";
import { GiftEvent } from "./gift";

export interface OverviewTotals {
  streamer_count: number;
  live_count: number;
  total_coins: number;
  eur_net: number;
  usd_net: number;
  eur_gross: number;
  usd_gross: number;
  gift_events_count: number;
  total_gifts_sent: number;
}

export interface Settings {
  usd_per_diamond: number;
  gross_usd_per_coin: number;
  usd_to_eur_rate: number;
  currency_primary: string;
  poll_interval_seconds: number;
  api_key?: string;
  telegram_access_mode: "whitelist" | "public" | string;
  public_banner_enabled: boolean | number;
  public_banner_title: string;
  public_banner_text: string;
  public_banner_style: "highlight" | "warning" | "success" | "info" | string;
  public_banner_btn_text: string;
  public_banner_btn_url: string;
}

export interface TelegramUser {
  id: number;
  telegram_id?: string | number;
  username?: string;
  first_name?: string;
  role: "admin" | "user" | string;
  is_allowed: number;
  note?: string;
  last_seen_at?: string;
}

export interface SystemStatus {
  workers_total: number;
  workers_running: number;
  workers_connected: number;
  telegram_bot?: {
    sdk_available: boolean;
    state: string;
    bot_username?: string;
    has_token: boolean;
    access_mode: string;
    logs: Array<{ timestamp: string; level: string; message: string }>;
  };
  system_health?: {
    host?: {
      disk?: { used_gb: number; free_gb: number; total_gb: number; percent: number; status: string };
      memory?: { used_mb: number; free_mb: number; total_mb: number; percent: number; status: string };
      cpu?: { percent: number; status: string };
    };
    docker?: any;
    database?: any;
  };
}

export interface OverviewResponse {
  ok?: boolean;
  period: string;
  totals: OverviewTotals;
  streamers: Streamer[];
  recent_gifts: GiftEvent[];
  telegram_users: TelegramUser[];
  settings: Settings;
  system: SystemStatus;
}
