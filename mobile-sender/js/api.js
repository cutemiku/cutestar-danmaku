// API 封装 — 与星萌弹幕姬后端兼容
// API 地址解析优先级：
//   1. URL 查询参数 ?api=https://api.example.com （现场部署时推荐，避免硬编码本地地址）
//   2. 全局变量 window.CUTESTAR_API_BASE（静态部署时在 index.html 里配置）
//   3. 留空 = 同源（后端与前端部署在同一域名/反代下，自动使用 https 协议）
const API_BASE = (() => {
  const fromQuery = new URLSearchParams(location.search).get('api');
  if (fromQuery) return fromQuery.replace(/\/+$/, '');
  if (window.CUTESTAR_API_BASE) return String(window.CUTESTAR_API_BASE).replace(/\/+$/, '');
  return ''; // 同源
})();

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
