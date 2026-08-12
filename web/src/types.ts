export interface Activity {
  id: string;
  public_code: string;
  name: string;
  status: string;
  submission_paused: boolean;
  slow_mode_seconds: number;
  danmaku_color_mode: "fixed" | "random";
  danmaku_default_color: string;
  allow_custom_color: boolean;
  auto_moderation_enabled: boolean;
  auto_moderation_configured: boolean;
  allow_multiline: boolean;
  overlay_font_size: number;
  overlay_speed: number;
  overlay_opacity: number;
  overlay_font: string;
}

export interface JoinResponse {
  participant_id: string;
  activity_id: string;
  nickname: string;
  session_token: string;
}

export interface Danmaku {
  id: string;
  activity_id: string;
  participant_id: string;
  content: string;
  color: string;
  status: DanmakuStatus;
  submitted_at: string;
}

export type DanmakuStatus = "pending" | "published" | "rejected" | "revoked" | "blocked";

export interface DanmakuSettings {
  color_mode: "fixed" | "random";
  default_color: string;
  allow_custom_color: boolean;
  allow_multiline?: boolean;
  auto_moderation_enabled?: boolean;
}

export interface OverlaySettings {
  font_size: number;
  speed: number;
  opacity: number;
  font: string;
}

export interface EventEnvelope {
  event_id: string;
  sequence: number;
  activity_id: string;
  type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface ActivityStats {
  online_count: number;
  published_count: number;
}

export type BanTargetType = "participant" | "ip" | "fingerprint";

export interface DanmakuLogItem {
  id: string;
  activity_id: string;
  participant_id: string;
  nickname: string | null;
  content: string;
  color: string;
  status: DanmakuStatus;
  ip_address: string | null;
  device_fingerprint: string | null;
  submitted_at: string;
}

export interface DanmakuLogsResponse {
  items: DanmakuLogItem[];
  total: number;
}

export interface Ban {
  id: string;
  activity_id: string;
  target_type: BanTargetType;
  target_value: string;
  reason: string | null;
  banned_by: string;
  expires_at: string | null;
  created_at: string;
}

export interface ScreenKey {
  id: string;
  activity_id: string;
  label: string;
  device_id?: string | null;
  enabled: boolean;
  created_at: string;
  key?: string | null;
}
