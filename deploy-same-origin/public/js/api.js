// API 封装 — 同源部署：前端与后端同域名，走相对路径，由 nginx 反代 /api
const API_BASE = '';

async function request(path, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `请求失败 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined;
  return res.json();
}

function authHeader(token) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

const api = {
  getActivity(code) {
    return request(`/api/v1/public/activities/${encodeURIComponent(code)}`);
  },
  joinActivity(code, nickname) {
    return request(`/api/v1/public/activities/${encodeURIComponent(code)}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname }),
    });
  },
  submitDanmaku(token, activityId, content, color, deviceFingerprint) {
    const headers = authHeader(token);
    return request('/api/v1/public/danmaku', {
      method: 'POST',
      headers,
      body: JSON.stringify({ activity_id: activityId, content, color, device_fingerprint: deviceFingerprint }),
    });
  },
  getStats(activityId, token) {
    // 携带参与者令牌：服务端视其为心跳，刷新"在线"状态
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    return request(`/api/v1/activities/${activityId}/stats`, { headers });
  },
};
