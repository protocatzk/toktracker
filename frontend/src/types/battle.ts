export interface Battle {
  id: number;
  streamer_id: number;
  streamer_username: string;
  opponent_user_id?: string;
  opponent_username?: string;
  host_score: number;
  opponent_score: number;
  result: "WIN" | "LOSS" | "DRAW" | "CANCELLED" | string;
  mode: "1v1" | "2v2" | string;
  duration_seconds: number;
  timestamp?: string;
  created_at?: string;
  top_contributor?: string;
}

export interface RivalStats {
  opponent_username: string;
  matches_count: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate: number;
}
