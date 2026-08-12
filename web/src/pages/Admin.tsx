import { useCallback, useEffect, useRef, useState } from "react";
import {
  adminLogin,
  approveDanmaku,
  approveScreenRequest,
  controlActivity,
  createActivity,
  createBan,
  createScreenKey,
  deleteActivity,
  deleteBan,
  deleteScreenKey,
  getDanmakuLogs,
  listActivities,
  listBans,
  listPendingScreenRequests,
  listScreenKeys,
  getModerationQueue,
  getStats,
  rejectDanmaku,
  updateActivity,
  updateDanmakuSettings,
  updateOverlaySettings,
} from "../api";
import type {
  Activity,
  ActivityStats,
  Ban,
  BanTargetType,
  Danmaku,
  DanmakuLogItem,
  DanmakuSettings,
  EventEnvelope,
  OverlaySettings,
  ScreenKey,
} from "../types";

const ADMIN_TOKEN_KEY = "cutestar_admin_token";

const STATUS_LABEL: Record<string, string> = {
  draft: "未开始",
  live: "进行中",
  paused: "已暂停",
  closed: "已结束",
};

type ConsoleTab = "overview" | "moderation" | "logs" | "display" | "activity";

// ── 工具 ──

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return `${Math.floor(diff / 86_400_000)} 天前`;
}

// ── 登录表单 ──

function LoginForm({ adminEntry, onLogin }: { adminEntry: string; onLogin: (token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async () => {
    if (!username.trim() || !password) return;
    setLoading(true);
    setError("");
    try {
      const res = await adminLogin(adminEntry, username.trim(), password);
      sessionStorage.setItem(ADMIN_TOKEN_KEY, res.token);
      onLogin(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }, [adminEntry, username, password, onLogin]);

  return (
    <section className="participant-page">
      <div className="login-form">
        <h2>运营控制台</h2>
        <p className="login-subtitle">请使用管理员账号登录</p>
        <label htmlFor="admin-user">用户名</label>
        <input
          id="admin-user"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          autoFocus
        />
        <label htmlFor="admin-pass">密码</label>
        <input
          id="admin-pass"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
        {error && <p className="login-error">{error}</p>}
        <button
          className="send-button"
          onClick={handleSubmit}
          disabled={!username.trim() || !password || loading}
        >
          {loading ? "登录中……" : "登录"}
        </button>
      </div>
    </section>
  );
}

// ── 审核控制台 ──

function Console({ adminToken, onLogout }: { adminToken: string; onLogout: () => void }) {
  const [activeTab, setActiveTab] = useState<ConsoleTab>("overview");
  const [activities, setActivities] = useState<Activity[]>([]);
  const [activityId, setActivityId] = useState<string | null>(null);
  const [queue, setQueue] = useState<Danmaku[]>([]);
  const [stats, setStats] = useState<ActivityStats>({ online_count: 0, published_count: 0 });
  const [wsConnected, setWsConnected] = useState(false);
  const [settings, setSettings] = useState<DanmakuSettings>({
    color_mode: "fixed",
    default_color: "#FFFFFF",
    allow_custom_color: false,
    allow_multiline: false,
    auto_moderation_enabled: false,
  });
  const [overlay, setOverlay] = useState<OverlaySettings>({
    font_size: 28,
    speed: 80,
    opacity: 1.0,
    font: "Segoe UI",
  });
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [overlaySaved, setOverlaySaved] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [logs, setLogs] = useState<DanmakuLogItem[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logsOffset, setLogsOffset] = useState(0);
  const [bans, setBans] = useState<Ban[]>([]);
  const [banTarget, setBanTarget] = useState<DanmakuLogItem | null>(null);
  const [banType, setBanType] = useState<BanTargetType>("participant");
  const [banDuration, setBanDuration] = useState<number | "permanent">(60);
  const [banReason, setBanReason] = useState("");
  const [banSaving, setBanSaving] = useState(false);
  const [banError, setBanError] = useState("");
  const [screenKeys, setScreenKeys] = useState<ScreenKey[]>([]);
  const [pendingKeys, setPendingKeys] = useState<ScreenKey[]>([]);
  const [newKeyLabel, setNewKeyLabel] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [keyCreating, setKeyCreating] = useState(false);
  const [keyError, setKeyError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);

  const activity = activities.find((a) => a.id === activityId) ?? null;

  // 拉取活动列表（默认选中 MEET2026，否则选第一个）
  useEffect(() => {
    listActivities(adminToken)
      .then((list) => {
        setActivities(list);
        setActivityId((prev) => {
          if (prev && list.some((a) => a.id === prev)) return prev;
          return list.find((a) => a.public_code === "MEET2026")?.id ?? list[0]?.id ?? null;
        });
      })
      .catch(() => {});
  }, [adminToken]);

  // 切换活动时重置各面板状态
  useEffect(() => {
    if (!activity) return;
    setSettings({
      color_mode: activity.danmaku_color_mode,
      default_color: activity.danmaku_default_color,
      allow_custom_color: activity.allow_custom_color,
      allow_multiline: activity.allow_multiline,
      auto_moderation_enabled: activity.auto_moderation_enabled,
    });
    setOverlay({
      font_size: activity.overlay_font_size,
      speed: activity.overlay_speed,
      opacity: activity.overlay_opacity,
      font: activity.overlay_font,
    });
    setQueue([]);
    setStats({ online_count: 0, published_count: 0 });
    setRenaming(false);
    setConfirmDelete(false);
    setConfirmEnd(false);
    setShowCreate(false);
    setLogs([]);
    setLogsTotal(0);
    setLogsOffset(0);
    setBanTarget(null);
    setScreenKeys([]);
    setPendingKeys([]);
    setNewKeyValue("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activityId]);

  // 局部更新活动列表中的字段（用于暂停状态、设置保存后的回写）
  const patchActivity = useCallback((id: string, patch: Partial<Activity>) => {
    setActivities((prev) => prev.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  }, []);

  // 拉取统计数据（挂载 + 每 10 秒刷新）
  useEffect(() => {
    if (!activity) return;
    const refresh = () => getStats(activity.id).then(setStats).catch(() => {});
    refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, [activity]);

  // 拉取审核队列
  const refreshQueue = useCallback(() => {
    if (!activity) return;
    getModerationQueue(adminToken, activity.id)
      .then(setQueue)
      .catch(() => {});
  }, [adminToken, activity]);

  useEffect(() => {
    refreshQueue();
  }, [refreshQueue]);

  // 拉取弹幕日志（每 8 秒刷新第一页）+ 禁言列表
  const refreshLogs = useCallback(() => {
    if (!activity) return;
    getDanmakuLogs(adminToken, activity.id, 50, 0)
      .then((data) => {
        setLogs(data.items);
        setLogsTotal(data.total);
        setLogsOffset(0);
      })
      .catch(() => {});
  }, [adminToken, activity]);

  const refreshBans = useCallback(() => {
    if (!activity) return;
    listBans(adminToken, activity.id).then(setBans).catch(() => {});
  }, [adminToken, activity]);

  const refreshScreenKeys = useCallback(() => {
    if (!activity) return;
    listScreenKeys(adminToken, activity.id).then(setScreenKeys).catch(() => {});
  }, [adminToken, activity]);

  const refreshPendingKeys = useCallback(() => {
    if (!activity) return;
    listPendingScreenRequests(adminToken, activity.id).then(setPendingKeys).catch(() => {});
  }, [adminToken, activity]);

  useEffect(() => {
    refreshScreenKeys();
    refreshPendingKeys();
    const timer = window.setInterval(refreshPendingKeys, 5000); // 待审批请求可能随时出现
    return () => window.clearInterval(timer);
  }, [refreshScreenKeys, refreshPendingKeys]);

  // 批准大屏接入请求（大屏轮询到 approved 后自动拿到 sk 连接）
  const handleApprovePending = useCallback(
    async (deviceId: string) => {
      if (!activity) return;
      setKeyError("");
      try {
        const approved = await approveScreenRequest(adminToken, activity.id, deviceId);
        setNewKeyValue(approved.key ?? "");
        setPendingKeys((prev) => prev.filter((k) => k.device_id !== deviceId));
        refreshScreenKeys();
      } catch (err) {
        setKeyError(err instanceof Error ? err.message : "批准失败");
      }
    },
    [activity, adminToken, refreshScreenKeys],
  );

  // 申请大屏授权密钥（明文仅此一次展示）
  const handleCreateKey = useCallback(async () => {
    if (!activity || !newKeyLabel.trim()) return;
    setKeyCreating(true);
    setKeyError("");
    try {
      const created = await createScreenKey(adminToken, activity.id, newKeyLabel.trim());
      setNewKeyValue(created.key ?? "");
      setNewKeyLabel("");
      refreshScreenKeys();
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : "申请失败");
    } finally {
      setKeyCreating(false);
    }
  }, [activity, adminToken, newKeyLabel, refreshScreenKeys]);

  // 删除密钥
  const handleDeleteKey = useCallback(
    async (keyId: string) => {
      if (!activity) return;
      try {
        await deleteScreenKey(adminToken, activity.id, keyId);
        setScreenKeys((prev) => prev.filter((k) => k.id !== keyId));
      } catch {
        refreshScreenKeys();
      }
    },
    [activity, adminToken, refreshScreenKeys],
  );

  useEffect(() => {
    refreshLogs();
    refreshBans();
    const timer = window.setInterval(refreshLogs, 8_000);
    return () => window.clearInterval(timer);
  }, [refreshLogs, refreshBans]);

  const loadMoreLogs = useCallback(() => {
    if (!activity || logs.length >= logsTotal) return;
    getDanmakuLogs(adminToken, activity.id, 50, logsOffset + 50)
      .then((data) => {
        setLogs((prev) => [...prev, ...data.items]);
        setLogsOffset((prev) => prev + 50);
      })
      .catch(() => {});
  }, [activity, adminToken, logs.length, logsTotal, logsOffset]);

  // 打开禁言对话框：按来源预选禁言维度
  const openBanDialog = useCallback((item: DanmakuLogItem) => {
    setBanTarget(item);
    setBanType("participant");
    setBanReason("");
    setBanError("");
  }, []);

  // 提交禁言
  const handleBan = useCallback(async () => {
    if (!banTarget || !activity) return;
    setBanSaving(true);
    setBanError("");
    try {
      let targetValue = banTarget.participant_id;
      if (banType === "ip") targetValue = banTarget.ip_address ?? "";
      if (banType === "fingerprint") targetValue = banTarget.device_fingerprint ?? "";
      if (!targetValue) {
        setBanError("该条目没有可用的禁言目标，请换一种维度");
        return;
      }
      await createBan(adminToken, activity.id, {
        target_type: banType,
        target_value: targetValue,
        reason: banReason.trim() || undefined,
        duration_minutes: banDuration === "permanent" ? null : banDuration,
      });
      setBanTarget(null);
      refreshBans();
    } catch (err) {
      setBanError(err instanceof Error ? err.message : "禁言失败");
    } finally {
      setBanSaving(false);
    }
  }, [banTarget, activity, adminToken, banType, banDuration, banReason, refreshBans]);

  // 解除禁言
  const handleUnban = useCallback(
    async (banId: string) => {
      if (!activity) return;
      try {
        await deleteBan(adminToken, activity.id, banId);
        setBans((prev) => prev.filter((b) => b.id !== banId));
      } catch {
        refreshBans();
      }
    },
    [activity, adminToken, refreshBans],
  );

  const banExpiresLabel = (ban: Ban): string => {
    if (!ban.expires_at) return "永久";
    const diff = new Date(ban.expires_at).getTime() - Date.now();
    if (diff <= 0) return "已过期";
    const minutes = Math.ceil(diff / 60_000);
    if (minutes < 60) return `剩余 ${minutes} 分钟`;
    if (minutes < 1440) return `剩余 ${Math.ceil(minutes / 60)} 小时`;
    return `剩余 ${Math.ceil(minutes / 1440)} 天`;
  };

  const banTargetLabel = (ban: Ban): string => {
    if (ban.target_type === "participant") return `参与者 ${ban.target_value.slice(0, 8)}`;
    if (ban.target_type === "ip") return `IP ${ban.target_value}`;
    return `设备 ${ban.target_value.slice(0, 12)}`;
  };

  // WebSocket 实时事件：仅在 activityId 变化时重建，避免内部字段更新触发重连循环
  useEffect(() => {
    if (!activityId) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const base = import.meta.env.VITE_API_URL ?? "";
    const wsBase = base ? base.replace(/^http/, "ws") : `${protocol}//${location.host}`;
    const ws = new WebSocket(`${wsBase}/api/v1/activities/${activityId}/events?admin_token=${encodeURIComponent(adminToken)}`);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (msg) => {
      try {
        const event: EventEnvelope = JSON.parse(msg.data);
        sequenceRef.current = Math.max(sequenceRef.current, event.sequence);
        ws.send(JSON.stringify({ last_sequence: sequenceRef.current }));

        // 处理事件
        if (event.type === "danmaku.pending_created") {
          const d = event.payload as unknown as Danmaku;
          setQueue((prev) => {
            if (prev.some((item) => item.id === d.id)) return prev;
            return [...prev, d];
          });
        } else if (event.type === "danmaku.published" || event.type === "danmaku.rejected") {
          const d = event.payload as unknown as Danmaku;
          setQueue((prev) => prev.filter((item) => item.id !== d.id));
        } else if (event.type === "activity.control_changed") {
          const payload = event.payload as { action?: string };
          if (payload.action === "pause_submissions") {
            patchActivity(activityId, { submission_paused: true });
          } else if (payload.action === "resume_submissions") {
            patchActivity(activityId, { submission_paused: false });
          }
        } else if (event.type === "activity.status_changed") {
          const payload = event.payload as { status?: string };
          if (payload.status) patchActivity(activityId, { status: payload.status });
        }
      } catch {
        /* ignore malformed events */
      }
    };

    return () => {
      ws.close();
    };
  }, [activityId, patchActivity]);

  // 创建活动
  const handleCreate = useCallback(async () => {
    const code = newCode.trim().toUpperCase();
    if (!newName.trim() || !/^[A-Z0-9]{3,32}$/.test(code)) {
      setCreateError("请填写活动名称与 3-32 位字母数字活动码");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const created = await createActivity(adminToken, newName.trim(), code);
      setActivities((prev) => [...prev, created]);
      setActivityId(created.id);
      setNewName("");
      setNewCode("");
      setShowCreate(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }, [adminToken, newName, newCode]);

  // 重命名活动（活动码不变）
  const handleRename = useCallback(async () => {
    if (!activity || !renameValue.trim()) return;
    try {
      const updated = await updateActivity(adminToken, activity.id, { name: renameValue.trim() });
      patchActivity(activity.id, { name: updated.name });
      setRenaming(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "重命名失败");
    }
  }, [activity, renameValue, adminToken, patchActivity]);

  // 删除活动（两步确认：危险操作需明确确认）
  const handleDeleteClick = useCallback(async () => {
    if (!activity) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    try {
      await deleteActivity(adminToken, activity.id);
      const rest = activities.filter((a) => a.id !== activity.id);
      setActivities(rest);
      setActivityId(rest.find((a) => a.public_code === "MEET2026")?.id ?? rest[0]?.id ?? null);
      setConfirmDelete(false);
    } catch {
      setConfirmDelete(false);
    }
  }, [confirmDelete, activity, adminToken, activities]);

  // 修改活动状态（draft/live/paused/closed）
  const handleSetStatus = useCallback(
    async (status: string) => {
      if (!activity) return;
      try {
        const updated = await updateActivity(adminToken, activity.id, { status });
        patchActivity(activity.id, { status: updated.status });
      } catch {
        /* ignore */
      }
    },
    [activity, adminToken, patchActivity],
  );

  // 结束活动（两步确认）
  const handleEndClick = useCallback(() => {
    if (!confirmEnd) {
      setConfirmEnd(true);
      return;
    }
    setConfirmEnd(false);
    handleSetStatus("closed");
  }, [confirmEnd, handleSetStatus]);

  // 审核操作
  const handleApprove = useCallback(
    async (id: string) => {
      try {
        await approveDanmaku(adminToken, id);
        setQueue((prev) => prev.filter((d) => d.id !== id));
      } catch {
        refreshQueue();
      }
    },
    [adminToken, refreshQueue],
  );

  const handleReject = useCallback(
    async (id: string) => {
      try {
        await rejectDanmaku(adminToken, id);
        setQueue((prev) => prev.filter((d) => d.id !== id));
      } catch {
        refreshQueue();
      }
    },
    [adminToken, refreshQueue],
  );

  // 暂停/恢复
  const handleTogglePause = useCallback(async () => {
    if (!activity) return;
    const action = activity.submission_paused ? "resume_submissions" : "pause_submissions";
    try {
      await controlActivity(adminToken, activity.id, action);
      patchActivity(activity.id, { submission_paused: !activity.submission_paused });
    } catch {
      /* ignore */
    }
  }, [adminToken, activity, patchActivity]);

  // 保存颜色设置（含活动级多行/自动审核开关）
  const handleSaveSettings = useCallback(async () => {
    if (!activity) return;
    try {
      // 多行/自动审核是活动级字段，先走 updateActivity 提交；颜色设置走 updateDanmakuSettings
      const updated = await updateActivity(adminToken, activity.id, {
        allow_multiline: settings.allow_multiline,
        auto_moderation_enabled: settings.auto_moderation_enabled,
      });
      patchActivity(activity.id, {
        allow_multiline: updated.allow_multiline,
        auto_moderation_enabled: updated.auto_moderation_enabled,
      });
      const saved = await updateDanmakuSettings(adminToken, activity.id, {
        color_mode: settings.color_mode,
        default_color: settings.default_color,
        allow_custom_color: settings.allow_custom_color,
      });
      setSettings({
        ...saved,
        allow_multiline: settings.allow_multiline,
        auto_moderation_enabled: settings.auto_moderation_enabled,
      });
      patchActivity(activity.id, {
        danmaku_color_mode: saved.color_mode,
        danmaku_default_color: saved.default_color,
        allow_custom_color: saved.allow_custom_color,
      });
      setSettingsSaved(true);
      window.setTimeout(() => setSettingsSaved(false), 2000);
    } catch {
      /* ignore */
    }
  }, [adminToken, activity, settings, patchActivity]);

  // 保存大屏显示设置
  const handleSaveOverlay = useCallback(async () => {
    if (!activity) return;
    try {
      const saved = await updateOverlaySettings(adminToken, activity.id, overlay);
      setOverlay(saved);
      patchActivity(activity.id, {
        overlay_font_size: saved.font_size,
        overlay_speed: saved.speed,
        overlay_opacity: saved.opacity,
        overlay_font: saved.font,
      });
      setOverlaySaved(true);
      window.setTimeout(() => setOverlaySaved(false), 2000);
    } catch {
      /* ignore */
    }
  }, [adminToken, activity, overlay, patchActivity]);

  const pendingCount = queue.length;
  const paused = activity?.submission_paused ?? false;
  const status = activity?.status ?? "";
  const primaryStatusAction =
    status === "draft" ? { label: "开始活动", target: "live" }
    : status === "live" ? { label: "暂停活动", target: "paused" }
    : status === "paused" ? { label: "恢复活动", target: "live" }
    : status === "closed" ? { label: "重新开放", target: "live" }
    : null;

  return (
    <section className="console-page">
      <div className="console-heading">
        <div>
          <div className="event-kicker">
            运营控制台 / {activity?.name ?? "加载中……"}
            {activity && (
              <span className={`status-chip status-${status}`}>
                {STATUS_LABEL[status] ?? status}
              </span>
            )}
          </div>
          <h1>现场内容</h1>
        </div>
        <div className="console-actions">
          <button className="outline-button" onClick={handleTogglePause} disabled={!activity}>
            {paused ? "恢复投稿" : "暂停投稿"}
          </button>
          <button className="outline-button logout-button" onClick={onLogout}>
            退出登录
          </button>
        </div>
      </div>

      <div className="activity-bar">
        <label className="settings-label" htmlFor="activity-select">当前活动</label>
        <select
          id="activity-select"
          className="activity-select"
          value={activityId ?? ""}
          onChange={(e) => setActivityId(e.target.value)}
        >
          {activities.length === 0 && <option value="">暂无活动</option>}
          {activities.map((a) => (
            <option key={a.id} value={a.id}>
              {a.public_code} · {a.name}
            </option>
          ))}
        </select>
        {activeTab === "activity" && <button
          className="outline-button"
          disabled={!activity}
          onClick={() => {
            setRenameValue(activity?.name ?? "");
            setRenaming((v) => !v);
          }}
        >
          {renaming ? "收起" : "重命名"}
        </button>}
        {activeTab === "activity" && primaryStatusAction && (
          <button
            className="outline-button"
            disabled={!activity}
            onClick={() => handleSetStatus(primaryStatusAction.target)}
          >
            {primaryStatusAction.label}
          </button>
        )}
        {activeTab === "activity" && <button className="outline-button" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "收起" : "创建活动"}
        </button>}
        {activeTab === "activity" && <button className="reject-button" disabled={!activity} onClick={handleEndClick}>
          {confirmEnd ? "确认结束？" : "结束活动"}
        </button>}
        {activeTab === "activity" && <button className="reject-button" disabled={!activity} onClick={handleDeleteClick}>
          {confirmDelete ? "确认删除？" : "删除"}
        </button>}
        {confirmEnd && (
          <span className="settings-hint">结束后参与者将无法加入或投稿，大屏端会提示重新配置</span>
        )}
        {confirmDelete && (
          <span className="settings-hint">删除后该活动的弹幕与数据将一并清除</span>
        )}
      </div>

      <nav className="console-tabs" aria-label="控制台功能">
        {([
          ["overview", "现场"],
          ["moderation", "审核"],
          ["logs", "日志与禁言"],
          ["display", "显示设置"],
          ["activity", "活动管理"],
        ] as [ConsoleTab, string][]).map(([tab, label]) => (
          <button
            key={tab}
            className={activeTab === tab ? "console-tab is-active" : "console-tab"}
            onClick={() => setActiveTab(tab)}
            aria-current={activeTab === tab ? "page" : undefined}
          >
            {label}
            {tab === "moderation" && pendingCount > 0 && <span>{pendingCount}</span>}
          </button>
        ))}
      </nav>

      {activeTab === "activity" && renaming && activity && (
        <div className="create-panel">
          <input
            className="text-input"
            placeholder="活动名称"
            value={renameValue}
            maxLength={120}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRename()}
          />
          <button className="send-button" onClick={handleRename} disabled={!renameValue.trim()}>
            保存
          </button>
          <span className="settings-hint">仅修改名称，活动码不变</span>
        </div>
      )}

      {activeTab === "activity" && showCreate && (
        <div className="create-panel">
          <input
            className="text-input"
            placeholder="活动名称"
            value={newName}
            maxLength={120}
            onChange={(e) => setNewName(e.target.value)}
          />
          <input
            className="text-input code-input"
            placeholder="活动码（3-32 位字母数字，如 MYEVENT）"
            value={newCode}
            maxLength={32}
            onChange={(e) => setNewCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <button className="send-button" onClick={handleCreate} disabled={creating}>
            {creating ? "创建中……" : "创建"}
          </button>
          {createError && <span className="field-error">{createError}</span>}
        </div>
      )}

      {activeTab === "activity" && (
        <div className="settings-panel">
          <div className="settings-title">
            <h2>
              大屏授权密钥 <span>{screenKeys.length}</span>
            </h2>
            <span className="settings-hint">
              部署大屏前在此申请密钥，大屏配置密钥后才能读取弹幕；删除后立即失效
            </span>
          </div>
          <div className="settings-rows">
            <div className="settings-row">
              <span className="settings-label">密钥用途</span>
              <input
                className="text-input key-label-input"
                placeholder="例如：现场一号大屏"
                value={newKeyLabel}
                maxLength={64}
                onChange={(e) => setNewKeyLabel(e.target.value)}
              />
              <button className="approve-button" onClick={handleCreateKey} disabled={keyCreating || !newKeyLabel.trim()}>
                {keyCreating ? "申请中……" : "申请密钥"}
              </button>
            </div>
            {newKeyValue && (
              <div className="settings-row">
                <span className="settings-label">新密钥</span>
                <code className="key-value">{newKeyValue}</code>
                <span className="settings-hint">仅显示一次，请立即配置到大屏</span>
              </div>
            )}
            {keyError && <p className="field-error">{keyError}</p>}
          </div>
          {pendingKeys.length > 0 && (
            <div className="pending-requests">
              <div className="settings-title">
                <h3>待审批大屏 <span>{pendingKeys.length}</span></h3>
                <span className="settings-hint">大屏首次连接时自动发起，批准后大屏自动获取密钥连接</span>
              </div>
              {pendingKeys.map((k) => (
                <article className="log-row" key={k.id}>
                  <div className="log-content">
                    <p>{k.label || "未命名大屏"}</p>
                    <div className="log-meta">
                      <span>{k.device_id?.slice(0, 16)}…</span>
                      <time>{new Date(k.created_at).toLocaleString()}</time>
                    </div>
                  </div>
                  <div className="moderation-actions">
                    <button
                      className="approve-button"
                      onClick={() => handleApprovePending(k.device_id!)}
                    >
                      批准
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {screenKeys.map((k) => (
            <article className="log-row" key={k.id}>
              <div className="log-content">
                <p>{k.label || "未命名大屏"}</p>
                <div className="log-meta">
                  <span>{k.enabled ? "已授权" : "已删除"}</span>
                  <time>{new Date(k.created_at).toLocaleString()}</time>
                </div>
              </div>
              <div className="moderation-actions">
                {k.enabled && (
                  <button className="reject-button" onClick={() => handleDeleteKey(k.id)}>
                    删除
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {activeTab === "overview" && <>
      <div className="metrics">
        <div>
          <span>当前在线</span>
          <strong>{stats.online_count}</strong>
          <small>WS 连接数</small>
        </div>
        <div>
          <span>已上墙</span>
          <strong>{stats.published_count}</strong>
          <small>已审核通过</small>
        </div>
        <div className="attention">
          <span>待处理</span>
          <strong>{pendingCount}</strong>
          <small>需要你的确认</small>
        </div>
      </div>
      </>}

      {activeTab === "display" && <div className="settings-panel">
        <div className="settings-title">
          <h2>弹幕颜色设置</h2>
          <span className={`save-note ${settingsSaved ? "is-visible" : ""}`}>已保存</span>
        </div>
        <div className="settings-rows">
          <div className="settings-row">
            <span className="settings-label">颜色模式</span>
            <div className="segment-control">
              <button
                className={settings.color_mode === "fixed" ? "segment-active" : ""}
                onClick={() => setSettings({ ...settings, color_mode: "fixed" })}
              >
                固定颜色
              </button>
              <button
                className={settings.color_mode === "random" ? "segment-active" : ""}
                onClick={() => setSettings({ ...settings, color_mode: "random" })}
              >
                随机颜色
              </button>
            </div>
          </div>
          {settings.color_mode === "fixed" && (
            <div className="settings-row">
              <span className="settings-label">默认颜色</span>
              <input
                type="color"
                value={settings.default_color}
                onChange={(e) => setSettings({ ...settings, default_color: e.target.value })}
              />
              <span className="color-hex">{settings.default_color}</span>
            </div>
          )}
          <div className="settings-row">
            <span className="settings-label">允许自定义颜色</span>
            <label className="switch">
              <input
                type="checkbox"
                checked={settings.allow_custom_color}
                onChange={(e) => setSettings({ ...settings, allow_custom_color: e.target.checked })}
              />
              <span className="switch-track" />
            </label>
            <span className="settings-hint">开启后参与者可在页面选择弹幕颜色</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">允许多行弹幕</span>
            <label className="switch">
              <input
                type="checkbox"
                checked={settings.allow_multiline}
                onChange={(e) => setSettings({ ...settings, allow_multiline: e.target.checked })}
              />
              <span className="switch-track" />
            </label>
            <span className="settings-hint">
              关闭后参与者无法输入换行，服务端也会拒绝多行内容（防刷屏）
            </span>
          </div>
        </div>
        <button className="outline-button" onClick={handleSaveSettings}>
          保存设置
        </button>
      </div>}

      {activeTab === "moderation" && <div className="settings-panel">
        <div className="settings-title">
          <h2>内容审核</h2>
        </div>
        <div className="settings-rows">
          <div className="settings-row">
            <span className="settings-label">自动审核</span>
            <label className={`switch ${activity?.auto_moderation_configured ? "" : "is-disabled"}`}>
              <input
                type="checkbox"
                checked={settings.auto_moderation_enabled}
                disabled={!activity?.auto_moderation_configured}
                onChange={async (e) => {
                  const next = e.target.checked;
                  setSettings({ ...settings, auto_moderation_enabled: next }); // 立即反馈
                  if (!activity) return;
                  try {
                    const updated = await updateActivity(adminToken, activity.id, {
                      auto_moderation_enabled: next,
                    });
                    patchActivity(activity.id, { auto_moderation_enabled: updated.auto_moderation_enabled });
                  } catch {
                    setSettings({ ...settings, auto_moderation_enabled: !next }); // 失败回滚
                  }
                }}
              />
              <span className="switch-track" />
            </label>
            {activity?.auto_moderation_configured ? (
              <span className="settings-hint">
                开启后弹幕将通过阿里云内容安全 API 自动审核，通过直接上屏，高风险自动拒绝，中/低风险保留人工复核
              </span>
            ) : (
              <span className="settings-hint settings-warn">
                阿里云内容安全未配置密钥，自动审核不可用。请在 server/.env 配置 CUTESTAR_ALIBABA_ACCESS_KEY_ID / _SECRET 后重启
              </span>
            )}
          </div>
        </div>
      </div>}

      {activeTab === "display" && <div className="settings-panel">
        <div className="settings-title">
          <h2>大屏显示设置（服务端统一下发）</h2>
          <span className={`save-note ${overlaySaved ? "is-visible" : ""}`}>已保存</span>
        </div>
        <div className="settings-rows">
          <div className="settings-row">
            <span className="settings-label">弹幕字号</span>
            <input
              className="number-input"
              type="number"
              min={12}
              max={160}
              value={overlay.font_size}
              onChange={(e) => setOverlay({ ...overlay, font_size: Number(e.target.value) })}
            />
            <span className="settings-hint">px（12–160）</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">弹幕速度</span>
            <input
              className="number-input"
              type="number"
              min={10}
              max={1000}
              value={overlay.speed}
              onChange={(e) => setOverlay({ ...overlay, speed: Number(e.target.value) })}
            />
            <span className="settings-hint">px/s（10–1000）</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">不透明度</span>
            <input
              className="range-input"
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={overlay.opacity}
              onChange={(e) => setOverlay({ ...overlay, opacity: Number(e.target.value) })}
            />
            <span className="color-hex">{Math.round(overlay.opacity * 100)}%</span>
          </div>
          <div className="settings-row">
            <span className="settings-label">字体</span>
            <input
              className="text-input"
              value={overlay.font}
              maxLength={64}
              onChange={(e) => setOverlay({ ...overlay, font: e.target.value })}
            />
            <span className="settings-hint">字体族名称</span>
          </div>
        </div>
        <button className="outline-button" onClick={handleSaveOverlay}>
          保存设置
        </button>
      </div>
      }

      {activeTab === "moderation" && <>
      <div className="queue-header">
        <h2>
          审核队列 <span>{pendingCount}</span>
        </h2>
        <span className={`ws-status ${wsConnected ? "ws-connected" : "ws-disconnected"}`}>
          {wsConnected ? "实时连接" : "连接中……"}
        </span>
      </div>
      </>}

      {activeTab === "moderation" && <div className="moderation-list">
        {activities.length === 0 && <p className="empty-queue">还没有活动，请先在上方创建活动</p>}
        {activities.length > 0 && queue.length === 0 && <p className="empty-queue">暂无待审核弹幕</p>}
        {queue.map((item) => (
          <article className="moderation-row" key={item.id}>
            <div className="avatar">{(item.content ?? "").slice(0, 1)}</div>
            <div className="message">
              <div>
                <b>{item.participant_id.slice(0, 8)}</b>
                <time>{relativeTime(item.submitted_at)}</time>
              </div>
              <p>{item.content}</p>
            </div>
            <div className="moderation-actions">
              <button className="approve-button" onClick={() => handleApprove(item.id)}>
                通过
              </button>
              <button className="reject-button" onClick={() => handleReject(item.id)}>
                拒绝
              </button>
            </div>
          </article>
        ))}
      </div>
      }

      {activeTab === "logs" && <div className="settings-panel">
        <div className="settings-title">
          <h2>
            弹幕日志 <span>{logsTotal}</span>
          </h2>
          <span className="settings-hint">记录发送人 IP / ID / 设备指纹，支持按维度禁言</span>
        </div>
        {logs.length === 0 && <p className="empty-queue">暂无弹幕记录</p>}
        {logs.map((item) => (
          <article className="log-row" key={item.id}>
            <div className="log-content">
              <p>{item.content}</p>
              <div className="log-meta">
                <span>{item.nickname ?? "匿名"}</span>
                <span>{item.participant_id.slice(0, 8)}</span>
                <span>{item.ip_address ?? "-"}</span>
                <span>{item.device_fingerprint ? item.device_fingerprint.slice(0, 16) : "-"}</span>
                <time>{relativeTime(item.submitted_at)}</time>
              </div>
            </div>
            <div className="moderation-actions">
              <button className="reject-button" onClick={() => openBanDialog(item)}>
                禁言
              </button>
            </div>
          </article>
        ))}
        {logs.length > 0 && logs.length < logsTotal && (
          <button className="outline-button" onClick={loadMoreLogs}>
            加载更多（{logs.length} / {logsTotal}）
          </button>
        )}
      </div>
      }

      {activeTab === "logs" && <div className="settings-panel">
        <div className="settings-title">
          <h2>
            禁言列表 <span>{bans.length}</span>
          </h2>
          <span className="settings-hint">被禁言者无法向该活动发送弹幕</span>
        </div>
        {bans.length === 0 && <p className="empty-queue">暂无禁言记录</p>}
        {bans.map((ban) => (
          <article className="log-row" key={ban.id}>
            <div className="log-content">
              <p>{banTargetLabel(ban)}</p>
              <div className="log-meta">
                <span>{ban.reason ?? "无原因"}</span>
                <span>by {ban.banned_by}</span>
                <span>{banExpiresLabel(ban)}</span>
              </div>
            </div>
            <div className="moderation-actions">
              <button className="approve-button" onClick={() => handleUnban(ban.id)}>
                解除
              </button>
            </div>
          </article>
        ))}
      </div>
      }

      {activeTab === "logs" && banTarget && (
        <div className="ban-dialog-backdrop" onClick={() => setBanTarget(null)}>
          <div className="ban-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>禁言设置</h3>
            <p className="ban-dialog-quote">“{banTarget.content}”</p>
            <div className="settings-row">
              <span className="settings-label">禁言维度</span>
              <div className="segment-control">
                <button
                  className={banType === "participant" ? "segment-active" : ""}
                  onClick={() => setBanType("participant")}
                >
                  发送人
                </button>
                <button
                  className={banType === "ip" ? "segment-active" : ""}
                  onClick={() => setBanType("ip")}
                  disabled={!banTarget.ip_address}
                  title={banTarget.ip_address ? undefined : "该条无 IP 记录"}
                >
                  IP
                </button>
                <button
                  className={banType === "fingerprint" ? "segment-active" : ""}
                  onClick={() => setBanType("fingerprint")}
                  disabled={!banTarget.device_fingerprint}
                  title={banTarget.device_fingerprint ? undefined : "该条无设备指纹"}
                >
                  设备
                </button>
              </div>
            </div>
            <div className="settings-row">
              <span className="settings-label">禁言时长</span>
              <select
                className="activity-select"
                value={banDuration}
                onChange={(e) =>
                  setBanDuration(e.target.value === "permanent" ? "permanent" : Number(e.target.value))
                }
              >
                <option value={10}>10 分钟</option>
                <option value={60}>1 小时</option>
                <option value={1440}>24 小时</option>
                <option value="permanent">永久</option>
              </select>
            </div>
            <div className="settings-row">
              <span className="settings-label">原因</span>
              <input
                className="text-input"
                value={banReason}
                maxLength={256}
                placeholder="选填，例如：刷屏 / 违规内容"
                onChange={(e) => setBanReason(e.target.value)}
              />
            </div>
            {banError && <p className="field-error">{banError}</p>}
            <div className="ban-dialog-actions">
              <button className="outline-button" onClick={() => setBanTarget(null)}>
                取消
              </button>
              <button className="reject-button" onClick={handleBan} disabled={banSaving}>
                {banSaving ? "禁言中……" : "确认禁言"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="console-bottom">
        <div>
          <span className={`status-dot ${wsConnected ? "" : "offline"}`} />
          {wsConnected ? "大屏已连接 · 运行正常" : "等待连接……"}
        </div>
      </div>
    </section>
  );
}

// ── 主组件 ──

export default function Admin({ adminEntry }: { adminEntry: string }) {
  const [adminToken, setAdminToken] = useState<string | null>(
    () => sessionStorage.getItem(ADMIN_TOKEN_KEY),
  );

  const handleLogin = useCallback((token: string) => {
    setAdminToken(token);
  }, []);

  const handleLogout = useCallback(() => {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    setAdminToken(null);
  }, []);

  if (!adminToken) {
    return <LoginForm adminEntry={adminEntry} onLogin={handleLogin} />;
  }

  return <Console adminToken={adminToken} onLogout={handleLogout} />;
}
