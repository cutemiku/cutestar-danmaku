import type {
  Activity,
  ActivityStats,
  Ban,
  BanTargetType,
  Danmaku,
  DanmakuLogItem,
  DanmakuLogsResponse,
  DanmakuSettings,
  EventEnvelope,
  JoinResponse,
  OverlaySettings,
  ScreenKey,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = `请求失败 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

// ── 公共 ──

export function getActivity(code: string): Promise<Activity> {
  return request<Activity>(`/api/v1/public/activities/${encodeURIComponent(code)}`);
}

export function joinActivity(code: string, nickname: string): Promise<JoinResponse> {
  return request<JoinResponse>(`/api/v1/public/activities/${encodeURIComponent(code)}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nickname }),
  });
}

// ── 参与者 ──

export function submitDanmaku(
  token: string,
  activityId: string,
  content: string,
  color?: string,
  idempotencyKey?: string,
  deviceFingerprint?: string,
): Promise<Danmaku> {
  const headers: Record<string, string> = { ...authHeader(token) };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  return request<Danmaku>("/api/v1/public/danmaku", {
    method: "POST",
    headers,
    body: JSON.stringify({ activity_id: activityId, content, color, device_fingerprint: deviceFingerprint }),
  });
}

// ── 统计 ──

export function getStats(activityId: string): Promise<ActivityStats> {
  return request<ActivityStats>(`/api/v1/activities/${activityId}/stats`);
}

// ── 管理员 ──

export function checkAdminEntry(entry: string): Promise<void> {
  return request<void>(`/api/v1/auth/admin/entry/${encodeURIComponent(entry)}`);
}

export function adminLogin(entry: string, username: string, password: string): Promise<{ token: string }> {
  return request<{ token: string }>(`/api/v1/auth/admin/login/${encodeURIComponent(entry)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function listActivities(adminToken: string): Promise<Activity[]> {
  return request<Activity[]>("/api/v1/activities", { headers: authHeader(adminToken) });
}

export function createActivity(adminToken: string, name: string, publicCode: string): Promise<Activity> {
  return request<Activity>("/api/v1/activities", {
    method: "POST",
    headers: authHeader(adminToken),
    body: JSON.stringify({ name, public_code: publicCode }),
  });
}

export function updateActivity(
  adminToken: string,
  activityId: string,
  patch: Partial<Pick<Activity, "name" | "status" | "auto_moderation_enabled" | "allow_multiline">>,
): Promise<Activity> {
  return request<Activity>(`/api/v1/activities/${activityId}`, {
    method: "PUT",
    headers: authHeader(adminToken),
    body: JSON.stringify(patch),
  });
}

export function deleteActivity(adminToken: string, activityId: string): Promise<void> {
  return request<void>(`/api/v1/activities/${activityId}`, {
    method: "DELETE",
    headers: authHeader(adminToken),
  });
}

export function getModerationQueue(adminToken: string, activityId: string): Promise<Danmaku[]> {
  return request<Danmaku[]>(`/api/v1/activities/${activityId}/moderation-queue`, {
    headers: authHeader(adminToken),
  });
}

export function getDanmakuLogs(
  adminToken: string,
  activityId: string,
  limit = 50,
  offset = 0,
): Promise<DanmakuLogsResponse> {
  return request<DanmakuLogsResponse>(
    `/api/v1/activities/${activityId}/danmaku-logs?limit=${limit}&offset=${offset}`,
    { headers: authHeader(adminToken) },
  );
}

export function createBan(
  adminToken: string,
  activityId: string,
  target: {
    target_type: BanTargetType;
    target_value: string;
    reason?: string;
    duration_minutes?: number | null;
  },
): Promise<Ban> {
  return request<Ban>(`/api/v1/activities/${activityId}/bans`, {
    method: "POST",
    headers: authHeader(adminToken),
    body: JSON.stringify(target),
  });
}

export function listBans(adminToken: string, activityId: string): Promise<Ban[]> {
  return request<Ban[]>(`/api/v1/activities/${activityId}/bans`, { headers: authHeader(adminToken) });
}

export function deleteBan(adminToken: string, activityId: string, banId: string): Promise<void> {
  return request<void>(`/api/v1/activities/${activityId}/bans/${banId}`, {
    method: "DELETE",
    headers: authHeader(adminToken),
  });
}

export function createScreenKey(adminToken: string, activityId: string, label: string): Promise<ScreenKey> {
  return request<ScreenKey>(`/api/v1/activities/${activityId}/screen-keys`, {
    method: "POST",
    headers: authHeader(adminToken),
    body: JSON.stringify({ label }),
  });
}

export function listScreenKeys(adminToken: string, activityId: string): Promise<ScreenKey[]> {
  return request<ScreenKey[]>(`/api/v1/activities/${activityId}/screen-keys`, {
    headers: authHeader(adminToken),
  });
}

export function deleteScreenKey(adminToken: string, activityId: string, keyId: string): Promise<void> {
  return request<void>(`/api/v1/activities/${activityId}/screen-keys/${keyId}`, {
    method: "DELETE",
    headers: authHeader(adminToken),
  });
}

export function listPendingScreenRequests(adminToken: string, activityId: string): Promise<ScreenKey[]> {
  return request<ScreenKey[]>(`/api/v1/activities/${activityId}/screen-keys/pending`, {
    headers: authHeader(adminToken),
  });
}

export function approveScreenRequest(adminToken: string, activityId: string, deviceId: string): Promise<ScreenKey> {
  return request<ScreenKey>(`/api/v1/activities/${activityId}/screen-keys/approve/${encodeURIComponent(deviceId)}`, {
    method: "POST",
    headers: authHeader(adminToken),
  });
}

export function approveDanmaku(adminToken: string, danmakuId: string): Promise<Danmaku> {
  return request<Danmaku>(`/api/v1/danmaku/${danmakuId}/approve`, {
    method: "POST",
    headers: authHeader(adminToken),
  });
}

export function rejectDanmaku(adminToken: string, danmakuId: string): Promise<Danmaku> {
  return request<Danmaku>(`/api/v1/danmaku/${danmakuId}/reject`, {
    method: "POST",
    headers: authHeader(adminToken),
  });
}

export function controlActivity(
  adminToken: string,
  activityId: string,
  action: string,
  seconds?: number,
): Promise<EventEnvelope> {
  return request<EventEnvelope>(`/api/v1/activities/${activityId}/controls`, {
    method: "POST",
    headers: authHeader(adminToken),
    body: JSON.stringify({ action, seconds: seconds ?? 0 }),
  });
}

export function updateDanmakuSettings(
  adminToken: string,
  activityId: string,
  settings: DanmakuSettings,
): Promise<DanmakuSettings> {
  return request<DanmakuSettings>(`/api/v1/activities/${activityId}/danmaku-settings`, {
    method: "PUT",
    headers: authHeader(adminToken),
    body: JSON.stringify(settings),
  });
}

export function updateOverlaySettings(
  adminToken: string,
  activityId: string,
  settings: OverlaySettings,
): Promise<OverlaySettings> {
  return request<OverlaySettings>(`/api/v1/activities/${activityId}/overlay-settings`, {
    method: "PUT",
    headers: authHeader(adminToken),
    body: JSON.stringify(settings),
  });
}
