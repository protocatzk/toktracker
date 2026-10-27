export interface WorkerLogEntry {
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | "DEBUG";
  message: string;
}

export interface WorkerDiagnostics {
  streamer_id: number;
  username: string;
  is_running: boolean;
  state: "connected" | "polling_offline" | "connecting" | "backoff" | "stopped" | "error" | string;
  auto_reconnect: boolean;
  authenticated_session: boolean;
  room_id?: string;
  session_id?: number | null;
  connected_since?: string | null;
  last_event_at?: string | null;
  last_message: string;
  last_error: string;
  current_viewers: number;
  peak_viewers: number;
  room_fan_tickets: number;
  reconnect_attempts: number;
  gifts_received_session: number;
  coins_received_session: number;
  active_battle?: any;
  pending_streaks_count: number;
  logs: WorkerLogEntry[];
}

export interface Streamer {
  id: number;
  username: string;
  display_name?: string;
  avatar_url?: string;
  room_id?: string;
  follower_count?: number;
  is_live: boolean | number;
  is_tracking: boolean | number;
  auto_monitor: boolean | number;
  current_viewers?: number;
  peak_viewers?: number;
  total_diamonds?: number;
  total_coins: number;
  gift_events_count?: number;
  total_gifts_sent?: number;
  unique_gifters?: number;
  usd_net: number;
  eur_net: number;
  usd_gross: number;
  eur_gross: number;
  top_gift?: {
    gift_name: string;
    coins: number;
  } | null;
  top_gifter?: {
    sender_username: string;
    coins: number;
  } | null;
  worker_diagnostics?: WorkerDiagnostics | null;
  is_tracking_active?: boolean;
  monitor_status?: string;
  last_seen_live?: string | null;
  created_at?: string;
}

export interface StreamerDetailResponse {
  streamer: Streamer;
  summary: {
    total_coins: number;
    usd_net: number;
    eur_net: number;
    usd_gross: number;
    eur_gross: number;
  };
  gift_breakdown: any[];
  top_gifters?: any[];
  sessions?: any[];
  recent_sessions?: any[];
  recent_events?: any[];
}
