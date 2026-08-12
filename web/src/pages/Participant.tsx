import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getActivity, joinActivity, submitDanmaku } from "../api";
import type { Activity } from "../types";

type Phase = "loading" | "idle" | "joined" | "error";

const FINGERPRINT_KEY = "cutestar_device_fingerprint";

// 设备指纹：首次生成后持久化，用于后台按设备维度禁言
function getDeviceFingerprint(): string {
  let fp = localStorage.getItem(FINGERPRINT_KEY);
  if (!fp) {
    fp = crypto.randomUUID?.() ?? `fp-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
    localStorage.setItem(FINGERPRINT_KEY, fp);
  }
  return fp;
}

export default function Participant() {
  const { code } = useParams<{ code: string }>();

  const [phase, setPhase] = useState<Phase>("loading");
  const [activity, setActivity] = useState<Activity | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const [nickname, setNickname] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [activityId, setActivityId] = useState("");

  const [content, setContent] = useState("");
  const [customColor, setCustomColor] = useState("#FFFFFF");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [bannedMsg, setBannedMsg] = useState("");
  const sentTimer = useRef(0);

  // 拉取活动信息
  useEffect(() => {
    if (!code) return;
    setPhase("loading");
    getActivity(code)
      .then((act) => {
        setActivity(act);
        setActivityId(act.id);
        setCustomColor(act.danmaku_default_color ?? "#FFFFFF");
        setPhase("idle");
      })
      .catch((err: Error) => {
        setErrorMsg(err.message);
        setPhase("error");
      });
  }, [code]);

  // 加入活动
  const handleJoin = useCallback(async () => {
    if (!code || !nickname.trim()) return;
    try {
      const res = await joinActivity(code, nickname.trim());
      setSessionToken(res.session_token);
      setActivityId(res.activity_id);
      setNickname(res.nickname);
      setPhase("joined");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "加入失败");
    }
  }, [code, nickname]);

  // 发送弹幕
  const handleSend = useCallback(async () => {
    if (!content.trim() || !sessionToken || sending) return;
    setSending(true);
    setBannedMsg("");
    try {
      await submitDanmaku(
        sessionToken,
        activityId,
        content.trim(),
        customColor,
        undefined,
        getDeviceFingerprint(),
      );
      setContent("");
      setSent(true);
      window.clearTimeout(sentTimer.current);
      sentTimer.current = window.setTimeout(() => setSent(false), 2400);
    } catch (err) {
      const message = err instanceof Error ? err.message : "发送失败";
      if (message.includes("禁言")) {
        setBannedMsg(message);
        setErrorMsg("");
      } else {
        setErrorMsg(message);
      }
    } finally {
      setSending(false);
    }
  }, [content, sessionToken, activityId, customColor, sending]);

  const paused = activity?.submission_paused ?? false;
  const allowCustomColor = activity?.allow_custom_color ?? false;
  const allowMultiline = activity?.allow_multiline ?? false;

  // ── 加载中 ──
  if (phase === "loading") {
    return (
      <section className="participant-page">
        <p className="loading">正在加载活动信息……</p>
      </section>
    );
  }

  // ── 活动不存在 ──
  if (phase === "error") {
    return (
      <section className="participant-page">
        <div className="error-page">
          <h2>无法打开活动</h2>
          <p>{errorMsg}</p>
          <Link className="outline-button text-link" to="/">重新输入活动码</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="participant-page">
      <div className="event-kicker">{(code ?? "").toUpperCase()}</div>
      <h1>
        {activity?.name ?? "活动现场"}
        <br />
        <em>把你的想法送到现场。</em>
      </h1>
      <p className="intro">
        弹幕会经过现场审核，通过后出现在大屏上。
      </p>

      {phase === "idle" ? (
        /* ── 加入表单 ── */
        <div className="participant-form">
          <label htmlFor="nickname">你的昵称</label>
          <input
            id="nickname"
            value={nickname}
            maxLength={24}
            placeholder="输入昵称后加入活动"
            onChange={(e) => setNickname(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleJoin()}
          />
          <div className="form-footer">
            <span>{nickname.length} / 24</span>
            <button
              className="send-button"
              onClick={handleJoin}
              disabled={!nickname.trim()}
            >
              加入活动<span>→</span>
            </button>
          </div>
          {errorMsg && <p className="field-error">{errorMsg}</p>}
        </div>
      ) : (
        /* ── 投稿表单 ── */
        <div className="participant-form">
          <div className="joined-info">
            <span className="avatar">{nickname.slice(0, 1)}</span>
            <span>{nickname}</span>
          </div>
          <label htmlFor="content">写下一句话</label>
          <textarea
            id="content"
            value={content}
            maxLength={120}
            placeholder="说点此刻最想说的……"
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (!allowMultiline && e.key === "Enter") {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          {allowCustomColor && (
            <div className="color-row">
              <label htmlFor="danmaku-color">弹幕颜色</label>
              <input
                id="danmaku-color"
                type="color"
                value={customColor}
                onChange={(e) => setCustomColor(e.target.value)}
              />
              <span className="color-hex">{customColor}</span>
            </div>
          )}
          <div className="form-footer">
            <span>{content.length} / 120</span>
            <button
              className="send-button"
              onClick={handleSend}
              disabled={!content.trim() || paused || sending || !!bannedMsg}
            >
              {bannedMsg ? "已被禁言" : paused ? "暂时停止投稿" : sending ? "发送中……" : "发送弹幕"}
              <span>↗</span>
            </button>
          </div>
          {bannedMsg && (
            <p className="banned-note" role="alert">
              {bannedMsg}，如对处理有异议请联系现场工作人员。
            </p>
          )}
          {errorMsg && <p className="field-error">{errorMsg}</p>}
        </div>
      )}

      <div className={`delivery-note ${sent ? "is-visible" : ""}`}>
        <span>✓</span> 已送达审核队列，稍后见
      </div>
      <div className="participant-foot">
        <span>活动码 {(code ?? "").toUpperCase()}</span>
        <span>由 星萌弹幕姬 提供互动</span>
      </div>
    </section>
  );
}
