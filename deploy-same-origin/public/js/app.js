// Cutestar 移动端发送端 — 单页应用
// 页面状态: 'entry' | 'join' | 'sender'

const FINGERPRINT_KEY = 'cutestar_device_fingerprint';
const SESSION_KEY = 'cutestar_session';

function getFingerprint() {
  let fp = localStorage.getItem(FINGERPRINT_KEY);
  if (!fp) {
    fp = crypto.randomUUID?.() || `fp-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
    localStorage.setItem(FINGERPRINT_KEY, fp);
  }
  return fp;
}

function saveSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

const app = document.getElementById('app');

// ── 颜色预设 ──
const COLOR_PRESETS = [
  '#FFFFFF', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
  '#FFEAA7', '#DDA0DD', '#FF8C42', '#00CED1', '#FF69B4',
  '#7B68EE', '#32CD32', '#FFD700', '#FF4500', '#40E0D0',
];

// ── 状态 ──
let state = {
  page: 'entry',
  activity: null,
  session: loadSession(),
  code: '',
  nickname: '',
  content: '',
  customColor: '#FFFFFF',
  showColorPicker: false,
  allowMultiline: false,
  allowCustomColor: false,
  submissionPaused: false,
  onlineCount: 0,
  publishedCount: 0,
  bannedMsg: '',
  sent: false,
  sending: false,
  loading: false,
  errorMsg: '',
  danmakuHistory: [],
};

// ── 路由 ──
function setPage(page) {
  state.page = page;
  state.errorMsg = '';
  render();
}

// ── 渲染入口 ──
function render() {
  app.innerHTML = '';
  switch (state.page) {
    case 'entry':
      app.appendChild(renderEntry());
      break;
    case 'join':
      app.appendChild(renderJoin());
      break;
    case 'sender':
      app.appendChild(renderSender());
      break;
  }
}

// ═══════════════════════════════════════
// 页面 1: 活动码输入
// ═══════════════════════════════════════
function renderEntry() {
  const container = document.createElement('div');
  container.className = 'page entry-page';

  container.innerHTML = `
    <div class="entry-bg"></div>
    <div class="entry-content">
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <h1 class="brand-title">弹幕互动</h1>
        <p class="brand-sub">输入活动码，加入现场</p>
      </div>
      <div class="entry-form">
        <div class="input-wrap">
          <input
            id="code-input"
            type="text"
            class="code-input"
            placeholder="输入活动码"
            maxlength="32"
            autocomplete="off"
            autocapitalize="characters"
            value="${state.code}"
          />
          <div class="input-line"></div>
        </div>
        ${state.errorMsg ? `<div class="error-toast">${escapeHtml(state.errorMsg)}</div>` : ''}
        <button id="enter-btn" class="primary-btn" disabled>
          <span>进入活动</span>
          <svg class="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
      <div class="entry-footer">
        <span>由 cutestar 提供互动支持</span>
      </div>
    </div>
  `;

  const input = container.querySelector('#code-input');
  const btn = container.querySelector('#enter-btn');

  input.focus();

  input.addEventListener('input', (e) => {
    state.code = e.target.value.trim().toUpperCase();
    e.target.value = state.code;
    btn.disabled = !state.code;
    state.errorMsg = '';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && state.code) handleEnter();
  });

  btn.addEventListener('click', handleEnter);

  return container;
}

async function handleEnter() {
  const btn = document.getElementById('enter-btn');
  btn.disabled = true;
  btn.classList.add('loading');
  state.loading = true;

  try {
    const activity = await api.getActivity(state.code);
    state.activity = activity;
    state.customColor = activity.danmaku_default_color || '#FFFFFF';
    state.allowCustomColor = activity.allow_custom_color || false;
    state.allowMultiline = activity.allow_multiline || false;
    state.submissionPaused = activity.submission_paused || false;

    // 检查是否有缓存的会话且活动一致
    const session = loadSession();
    if (session && session.activity_id === activity.id) {
      state.session = session;
      state.nickname = session.nickname;
      setPage('sender');
      startPolling();
    } else {
      clearSession();
      state.session = null;
      setPage('join');
    }
  } catch (err) {
    state.errorMsg = err.message || '活动不存在或已结束';
    state.loading = false;
    render();
  }
}

// ═══════════════════════════════════════
// 页面 2: 昵称加入
// ═══════════════════════════════════════
function renderJoin() {
  const container = document.createElement('div');
  container.className = 'page join-page';

  container.innerHTML = `
    <div class="join-header">
      <button id="back-btn" class="icon-btn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
      </button>
      <span class="join-title">加入活动</span>
      <div class="placeholder"></div>
    </div>
    <div class="join-content">
      <div class="activity-card">
        <div class="activity-code">${state.activity.public_code}</div>
        <h2 class="activity-name">${escapeHtml(state.activity.name)}</h2>
        <div class="activity-status ${state.activity.status}">
          ${statusLabel(state.activity.status)}
        </div>
      </div>
      <div class="join-form">
        <label class="input-label">你的昵称</label>
        <div class="input-wrap">
          <input
            id="nickname-input"
            type="text"
            class="nickname-input"
            placeholder="输入昵称参与互动"
            maxlength="24"
            autocomplete="off"
            value="${state.nickname}"
          />
          <div class="input-line"></div>
        </div>
        <div class="char-count"><span id="nick-count">${state.nickname.length}</span> / 24</div>
        ${state.errorMsg ? `<div class="error-toast">${escapeHtml(state.errorMsg)}</div>` : ''}
        <button id="join-btn" class="primary-btn" ${!state.nickname.trim() ? 'disabled' : ''}>
          <span>加入活动</span>
        </button>
      </div>
    </div>
  `;

  const input = container.querySelector('#nickname-input');
  const btn = container.querySelector('#join-btn');
  const count = container.querySelector('#nick-count');

  input.focus();

  input.addEventListener('input', (e) => {
    state.nickname = e.target.value;
    count.textContent = state.nickname.length;
    btn.disabled = !state.nickname.trim();
    state.errorMsg = '';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && state.nickname.trim()) handleJoin();
  });

  btn.addEventListener('click', handleJoin);
  container.querySelector('#back-btn').addEventListener('click', () => setPage('entry'));

  return container;
}

async function handleJoin() {
  const btn = document.getElementById('join-btn');
  btn.disabled = true;
  btn.classList.add('loading');

  try {
    const res = await api.joinActivity(state.code, state.nickname.trim());
    state.session = {
      participant_id: res.participant_id,
      activity_id: res.activity_id,
      nickname: res.nickname,
      token: res.session_token,
    };
    saveSession(state.session);
    state.nickname = res.nickname;
    setPage('sender');
    startPolling();
  } catch (err) {
    state.errorMsg = err.message || '加入失败';
    render();
  }
}

// ═══════════════════════════════════════
// 页面 3: 弹幕发送主界面
// ═══════════════════════════════════════
function renderSender() {
  const container = document.createElement('div');
  container.className = 'page sender-page';

  const isPaused = state.submissionPaused;
  const isBanned = !!state.bannedMsg;

  container.innerHTML = `
    <div class="sender-header">
      <div class="sender-header-left">
        <button id="leave-btn" class="icon-btn small">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M9 19l-7-7 7-7M16 19l-7-7 7-7"/>
          </svg>
        </button>
        <div class="header-info">
          <span class="header-code">${state.activity?.public_code || ''}</span>
          <span class="header-online">
            <span class="online-dot"></span>
            ${state.onlineCount} 人在线
          </span>
        </div>
      </div>
      <div class="header-stats">
        <span>${state.publishedCount} 条弹幕</span>
      </div>
    </div>

    <div class="sender-body">
      <div class="danmaku-area" id="danmaku-area">
        ${state.danmakuHistory.length === 0
          ? `<div class="empty-danmaku">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              <p>还没有弹幕</p>
              <span>发送第一条弹幕吧</span>
            </div>`
          : state.danmakuHistory.map((d, i) => `
            <div class="danmaku-item" style="animation-delay: ${i * 0.05}s">
              <div class="danmaku-avatar" style="background: ${stringToColor(d.nickname)}">${d.nickname.slice(0, 1)}</div>
              <div class="danmaku-bubble" style="border-left-color: ${d.color}">
                <div class="danmaku-nick">${escapeHtml(d.nickname)}</div>
                <div class="danmaku-text" style="color: ${d.color}">${escapeHtml(d.content)}</div>
              </div>
            </div>
          `).join('')
        }
      </div>
    </div>

    <div class="sender-footer">
      ${state.sent ? `<div class="send-toast show">发送成功</div>` : ''}
      ${isBanned ? `<div class="banned-banner">${escapeHtml(state.bannedMsg)}</div>` : ''}

      <div class="input-toolbar">
        ${state.allowCustomColor ? `
          <button id="color-toggle" class="color-btn" style="background: ${state.customColor}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 2a10 10 0 0 1 0 20"/>
            </svg>
          </button>
        ` : ''}
        <div class="message-input-wrap">
          <textarea
            id="msg-input"
            class="message-input"
            placeholder="${isPaused ? '已暂停投稿' : isBanned ? '已被禁言' : '发弹幕...'}"
            maxlength="120"
            rows="1"
            ${isPaused || isBanned ? 'disabled' : ''}
          >${state.content}</textarea>
        </div>
        <button id="send-btn" class="send-btn ${state.content.trim() && !isPaused && !isBanned && !state.sending ? 'active' : ''}" ${!state.content.trim() || isPaused || isBanned || state.sending ? 'disabled' : ''}>
          ${state.sending
            ? `<svg class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4m0 12v4m10-10h-4M6 12H2m15.07 4.93l-2.83-2.83M8.76 8.76L5.93 5.93m12.14 0l-2.83 2.83M8.76 15.24l-2.83 2.83"/></svg>`
            : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>`
          }
        </button>
      </div>

      ${state.showColorPicker ? `
        <div class="color-panel">
          <div class="color-grid">
            ${COLOR_PRESETS.map(c => `
              <button class="color-swatch ${state.customColor === c ? 'active' : ''}" style="background: ${c}" data-color="${c}">
                ${state.customColor === c ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>' : ''}
              </button>
            `).join('')}
          </div>
          <div class="color-custom">
            <input type="color" id="custom-color" value="${state.customColor}">
            <span>${state.customColor}</span>
          </div>
        </div>
      ` : ''}

      <div class="input-meta">
        <span class="char-count">${state.content.length}/120</span>
        ${state.allowMultiline ? '<span class="hint">支持多行</span>' : '<span class="hint">Enter 发送</span>'}
      </div>
    </div>
  `;

  // 事件绑定
  const msgInput = container.querySelector('#msg-input');
  const sendBtn = container.querySelector('#send-btn');

  if (msgInput) {
    msgInput.focus();

    // 自动增高
    msgInput.addEventListener('input', (e) => {
      state.content = e.target.value;
      e.target.style.height = 'auto';
      e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
      renderSenderUpdate();
    });

    msgInput.addEventListener('keydown', (e) => {
      if (!state.allowMultiline && e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (state.content.trim()) handleSend();
      }
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', handleSend);
  }

  container.querySelector('#leave-btn')?.addEventListener('click', () => {
    if (confirm('确定要退出当前活动吗？')) {
      clearSession();
      state.session = null;
      state.activity = null;
      state.code = '';
      state.nickname = '';
      state.danmakuHistory = [];
      stopPolling();
      setPage('entry');
    }
  });

  // 颜色选择器
  container.querySelector('#color-toggle')?.addEventListener('click', () => {
    state.showColorPicker = !state.showColorPicker;
    render();
  });

  container.querySelectorAll('.color-swatch').forEach(btn => {
    btn.addEventListener('click', () => {
      state.customColor = btn.dataset.color;
      render();
    });
  });

  const customColorInput = container.querySelector('#custom-color');
  if (customColorInput) {
    customColorInput.addEventListener('input', (e) => {
      state.customColor = e.target.value;
      render();
    });
  }

  // 点击面板外关闭颜色选择器
  if (state.showColorPicker) {
    container.addEventListener('click', (e) => {
      if (!e.target.closest('.color-panel') && !e.target.closest('#color-toggle')) {
        state.showColorPicker = false;
        render();
      }
    });
  }

  // 滚动到底部
  const area = container.querySelector('#danmaku-area');
  if (area) {
    area.scrollTop = area.scrollHeight;
  }

  return container;
}

// 局部更新发送按钮状态（避免全量重渲染）
function renderSenderUpdate() {
  const btn = document.getElementById('send-btn');
  const count = document.querySelector('.input-meta .char-count');
  if (!btn) return;

  const hasContent = state.content.trim().length > 0;
  const isPaused = state.submissionPaused;
  const isBanned = !!state.bannedMsg;

  btn.disabled = !hasContent || isPaused || isBanned || state.sending;
  btn.classList.toggle('active', hasContent && !isPaused && !isBanned && !state.sending);

  if (count) count.textContent = `${state.content.length}/120`;
}

async function handleSend() {
  if (!state.content.trim() || state.sending || state.submissionPaused || state.bannedMsg) return;

  state.sending = true;
  renderSenderUpdate();

  try {
    await api.submitDanmaku(
      state.session.token,
      state.session.activity_id,
      state.content.trim(),
      state.customColor,
      getFingerprint(),
    );

    // 添加到本地历史（仅本机展示，不拉取他人弹幕）
    state.danmakuHistory.push({
      nickname: state.nickname,
      content: state.content.trim(),
      color: state.customColor,
      time: new Date(),
    });
    if (state.danmakuHistory.length > 50) state.danmakuHistory.shift();

    state.content = '';
    state.sent = true;
    state.sending = false;
    state.bannedMsg = '';
    state.errorMsg = '';

    setTimeout(() => { state.sent = false; render(); }, 2000);
    render();
  } catch (err) {
    const msg = err.message || '发送失败';
    if (msg.includes('禁言')) {
      state.bannedMsg = msg;
    } else {
      state.errorMsg = msg;
    }
    state.sending = false;
    render();
  }
}

// ═══════════════════════════════════════
// 轮询
// ═══════════════════════════════════════
let pollTimer = null;

function startPolling() {
  stopPolling();
  refreshStats();
  pollTimer = setInterval(refreshStats, 8000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function refreshStats() {
  if (!state.activity) return;
  try {
    const stats = await api.getStats(state.activity.id, state.session?.token);
    state.onlineCount = stats.online_count || 0;
    state.publishedCount = stats.published_count || 0;
    // 静默更新，不重渲染整个页面
    const onlineEl = document.querySelector('.header-online');
    const statsEl = document.querySelector('.header-stats span');
    if (onlineEl) {
      onlineEl.innerHTML = `<span class="online-dot"></span>${state.onlineCount} 人在线`;
    }
    if (statsEl) {
      statsEl.textContent = `${state.publishedCount} 条弹幕`;
    }
  } catch {
    // 静默失败
  }
}

// ═══════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function statusLabel(status) {
  const map = { draft: '未开始', live: '进行中', paused: '已暂停', closed: '已结束' };
  return map[status] || status;
}

function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['#E06B3C', '#4ECDC4', '#45B7D1', '#96CEB4', '#DDA0DD', '#FF8C42', '#7B68EE', '#32CD32'];
  return colors[Math.abs(hash) % colors.length];
}

// ═══════════════════════════════════════
// 初始化
// ═══════════════════════════════════════
// 支持 URL 预填活动码：?code=MEET2026 或 #MEET2026
function getPresetCode() {
  const params = new URLSearchParams(location.search);
  const fromQuery = params.get('code');
  if (fromQuery) return fromQuery.toUpperCase();
  const hash = location.hash.replace(/^#/, '').trim();
  if (hash) return hash.toUpperCase();
  return '';
}

const presetCode = getPresetCode();

// 如果有缓存会话，尝试恢复
const cachedSession = loadSession();
if (cachedSession) {
  // 预加载活动信息
  state.code = '';
  state.session = cachedSession;
  state.nickname = cachedSession.nickname;
  api.getActivity(cachedSession.activity_id).then(activity => {
    state.activity = activity;
    state.code = activity.public_code;
    state.customColor = activity.danmaku_default_color || '#FFFFFF';
    state.allowCustomColor = activity.allow_custom_color || false;
    state.allowMultiline = activity.allow_multiline || false;
    state.submissionPaused = activity.submission_paused || false;
    setPage('sender');
    startPolling();
  }).catch(() => {
    clearSession();
    render();
  });
} else if (presetCode) {
  // URL 预填活动码：自动查询活动信息
  state.code = presetCode;
  render();
  api.getActivity(presetCode).then(activity => {
    state.activity = activity;
    state.customColor = activity.danmaku_default_color || '#FFFFFF';
    state.allowCustomColor = activity.allow_custom_color || false;
    state.allowMultiline = activity.allow_multiline || false;
    state.submissionPaused = activity.submission_paused || false;
    setPage('join');
  }).catch(() => {
    state.errorMsg = '活动不存在或已结束';
    render();
  });
} else {
  render();
}
