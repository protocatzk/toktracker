export interface GiftEvent {
  id: number;
  streamer_id: number;
  streamer_username?: string;
  session_id?: number | null;
  gift_name: string;
  diamond_count: number;
  repeat_count: number;
  total_diamonds: number;
  total_coins: number;
  sender_username: string;
  sender_nickname?: string;
  source: string;
  timestamp?: string;
  created_at?: string;
  usd_net: number;
  eur_net: number;
  is_super_fan?: boolean;
}

export interface DonorTier {
  coins: number;
  tier_name: string;
  badge_color?: string;
}
