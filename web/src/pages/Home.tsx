import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Home() {
  const [code, setCode] = useState("");
  const navigate = useNavigate();

  const enter = () => {
    const normalized = code.trim().toUpperCase();
    if (normalized) navigate(`/e/${encodeURIComponent(normalized)}`);
  };

  return (
    <section className="code-entry-page">
      <div className="code-entry-kicker">现场互动入口</div>
      <h1>输入活动码，<em>加入现场。</em></h1>
      <p>活动码通常印在现场二维码旁，也可以直接打开活动链接。</p>
      <div className="code-entry-form">
        <label htmlFor="activity-code">活动码</label>
        <input
          id="activity-code"
          value={code}
          maxLength={32}
          placeholder="例如 MEET2026"
          autoCapitalize="characters"
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && enter()}
        />
        <button className="send-button" onClick={enter} disabled={!code.trim()}>
          进入活动 <span>→</span>
        </button>
      </div>
      <div className="code-entry-note">无需注册 · 输入昵称即可参与</div>
    </section>
  );
}
