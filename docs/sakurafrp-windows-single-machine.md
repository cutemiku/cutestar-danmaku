# 星萌弹幕姬 · 基于 SakuraFrp 的 Windows 单机部署教程

> 适用对象：无云服务器、想用一台 Windows 电脑（或家用主机）对外提供弹幕互动的场景。
> 原理：服务端与前端跑在本机，通过 **SakuraFrp 内网穿透** 把公网流量映射回本机端口；
> 发送端（参与者页面 / mobile-sender）全部通过公网地址访问；大屏端按是否与服务端同网分两种情况连接。

---

## 1. 总体架构

```
                    公网
  参与者浏览器 ──────► SakuraFrp 隧道 ──────┐
  手机发送端 ────────►（frp 节点域名）        │
                                           ▼
                              ┌──────────────────────────┐
                              │    Windows 单机           │
                              │   ┌────────────────────┐  │
                              │   │ dev-proxy (8080)    │  │
                              │   │  静态前端 web/dist   │  │
                              │   │  /m/ mobile-sender  │  │
                              │   └────────┬───────────┘  │
                              │            │ /api /health │
                              │   ┌────────▼───────────┐  │
                              │   │ uvicorn (8000)      │  │
                              │   │ FastAPI + SQLite    │  │
                              │   └────────┬───────────┘  │
                              └────────────┼──────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────┐
         │ 情况 A：大屏与服务端同局域网/同机 │         │ 情况 B：大屏异地      │
         │ 大屏填 http://内网IP:8080        │         │ 大屏填 frp 公网域名    │
         │ （不经公网，延迟最低）             │         │ （走 frp 隧道，WSS）   │
         └─────────────────────────────────┘         └─────────────────────────┘
```

- **发送端（默认）**：浏览器 / 手机扫二维码打开 `https://<frp域名>`，全部流量走公网隧道。
- **大屏端**：两种情况分别配置，见第 6、7 节。

---

## 2. 前置准备

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11 x64 |
| Python | 3.11+（[python.org](https://www.python.org/downloads/) 安装时勾选 **Add to PATH**） |
| Node.js | 18+（[nodejs.org](https://nodejs.org/)） |
| .NET SDK | 8.0（仅大屏端编译需要，[dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/8.0)） |
| SakuraFrp 账号 | 在 [SakuraFrp 官网](https://www.natfrp.com/) 注册并**完成实名认证**（创建隧道必需） |
| 代码 | 本项目克隆/解压到本机任意目录，下文以 `D:\cutestar-danmaku` 为例 |

> 防火墙提示：本机需要允许 `8000`（后端）与 `8080`（前端代理）端口入站，仅对局域网开放即可；
> 公网访问由 SakuraFrp 客户端**主动出网**完成，不需要在路由器上做端口映射。

---

## 3. 构建前端

在 `D:\cutestar-danmaku\web` 下执行：

```powershell
npm install
npm run build
```

构建产物输出到 `web\dist\`（含 `index.html` 与 `assets\`）。dev-proxy 会直接服务这个目录。

> 管理后台入口由 URL 路径决定：访问 `https://<frp域名>/<CUTESTAR_ADMIN_ENTRY_PATH>` 即进入登录页（前端 `/:adminEntry` 路由会向后端校验该入口），**无需**前端构建时配置。

---

## 4. 启动后端（FastAPI）

### 4.1 配置环境变量

在 `D:\cutestar-danmaku\server` 下创建 `.env`（参考 `.env.example`），单机 SQLite 部署建议：

```ini
CUTESTAR_ENV=production
CUTESTAR_DATABASE_URL=sqlite+aiosqlite:///./data/cutestar.db
CUTESTAR_REDIS_URL=            # 留空：单 worker 进程内事件总线
CUTESTAR_CORS_ORIGINS=         # 同源部署（发送端与后端同域名），留空即可
CUTESTAR_JWT_SECRET=<至少32位随机字符串，勿用示例值>
CUTESTAR_ADMIN_USERNAME=admin
CUTESTAR_ADMIN_PASSWORD=<强密码>
CUTESTAR_ADMIN_ENTRY_PATH=<随机8-64位URL安全段，如 ops-2026-x7k2>
```

> `CUTESTAR_JWT_SECRET` 生成示例（PowerShell）：
> `[Convert]::ToBase64String((1..48 | %{Get-Random -Max 256}) -as [byte[]])`

### 4.2 安装依赖并初始化数据库

```powershell
cd D:\cutestar-danmaku\server
pip install -r requirements.txt
python -m app.seed        # 自动迁移建表 + 播种管理员 + 演示活动 MEET2026
```

> 数据目录：SQLite 文件默认落在 `server\data\cutestar.db`（如用上面的 URL 需先 `mkdir data`）。

### 4.3 启动后端

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证：浏览器打开 `http://127.0.0.1:8000/health` 应返回 `{"status":"ok",...}`。

> ⚠️ 单机部署**不要**加 `--workers` 多进程：事件总线在进程内，多 worker 会收不到实时事件；
> 若必须多 worker，需配置 `CUTESTAR_REDIS_URL` 并安装 Redis。

---

## 5. 启动前端同源代理（dev-proxy）

dev-proxy 是轻量同源代理：服务 `web\dist` 静态前端 + `/m/` 发送端，并把 `/api`、`/health` 转发到本机 8000 后端。

```powershell
cd D:\cutestar-danmaku
python deploy-same-origin\dev-proxy.py 8080 0.0.0.0
```

- 第一个参数：端口（默认 8080）
- 第二个参数：监听地址（`0.0.0.0` 允许局域网内大屏/其他设备访问；仅本机用可填 `127.0.0.1`）

验证：

```powershell
Invoke-WebRequest http://127.0.0.1:8080/health          # 后端可达性（经代理）
Invoke-WebRequest http://127.0.0.1:8080/                # React 首页
Invoke-WebRequest http://127.0.0.1:8080/m/               # mobile-sender 发送端
```

> 想用 nginx 替代 dev-proxy 也可以，配置见 `deploy-same-origin/nginx.windows.conf`（需改 `root` 为 `web\dist` 绝对路径）。

---

## 6. SakuraFrp 内网穿透配置

### 6.1 安装并登录客户端

1. 下载 **SakuraFrp Launcher**（官网 → 下载中心 → Windows 版），解压运行。
2. 登录账号（需已完成实名认证）。

### 6.2 创建 HTTP 隧道（供发送端与情况 B 大屏使用）

在 Launcher / 管理面板中创建隧道：

| 字段 | 填写 |
|---|---|
| 隧道类型 | **HTTP**（HTTPS 需要付费隧道；免费 HTTP 隧道即可满足 ws 场景） |
| 本地地址 | `127.0.0.1` |
| 本地端口 | `8080` |
| 远程端口 | 随机（或面板指定） |
| 隧道名称 | 随意，如 `cutestar-web` |

> HTTP 隧道会得到一个公网域名（形如 `xxxxxx.frp-xxxx.xxx` 的节点域名，以面板显示为准）。
> WebSocket：dev-proxy/uvicorn 侧无需额外配置；SakuraFrp HTTP 隧道默认透传 Upgrade 头（大屏 WSS 场景建议开通 HTTPS 隧道，免费版不强制）。

### 6.3 启动隧道

在 Launcher 中启动该隧道，记录分配的公网地址（下文以 `https://cutestar-xxxxxx.frp-xxxx.xxx` 为例）。

### 6.4 验证公网访问

- 手机（关闭 Wi-Fi 用 4G）打开 `https://cutestar-xxxxxx.frp-xxxx.xxx/e/MEET2026`，应能看到参与者页面。
- 提交一条测试弹幕，应出现在审核队列（管理后台）。

---

## 7. 大屏端配置

> 无论哪种情况，都需先在管理后台为活动**申请大屏授权密钥**：
> 打开 `https://<你的访问地址>/<CUTESTAR_ADMIN_ENTRY_PATH>` 登录 → 活动 → 大屏授权密钥 → 申请密钥 → 复制一次性明文 sk。

### 7.1 情况 A：大屏与服务端同局域网 / 同一台机器

大屏客户端（SetupWindow / SettingsWindow）填写：

| 字段 | 值 |
|---|---|
| 服务地址 | `http://<本机局域网IP>:8080`（同一台机器可用 `http://127.0.0.1:8080`） |
| 活动码 | `MEET2026`（或实际活动码） |
| 大屏密钥 | 第 7 节开头申请到的 sk |

- 连接协议：客户端自动把 `http://` 转为 `ws://`，**不经公网**，延迟最低、不消耗隧道流量。
- 查询本机局域网 IP：`ipconfig` 中“IPv4 地址”（如 `192.168.1.100`）。

### 7.2 情况 B：大屏与服务端不在同一局域网（异地 / 远程现场）

| 字段 | 值 |
|---|---|
| 服务地址 | `https://cutestar-xxxxxx.frp-xxxx.xxx`（frp 公网域名） |
| 活动码 | `MEET2026` |
| 大屏密钥 | 同上 |

- 客户端自动转为 `wss://`，经 frp 隧道连接服务端。
- 免费 HTTP 隧道下客户端会以 ws 明文连接；涉及敏感现场可开通 SakuraFrp HTTPS 隧道获得 wss。

### 7.3 验证大屏连通

1. 大屏状态栏应显示「已连接」（而非“断线重连中”）。
2. 用手机发送一条弹幕 → 管理后台通过 → 大屏数秒内出现弹幕。
3. 断开大屏网络再恢复，观察自动重连与断线补偿（历史弹幕带 replay 标记错峰展示）。

---

## 8. 常见问题

| 现象 | 原因与解决 |
|---|---|
| 手机打不开 frp 域名 | 隧道未启动 / 未实名；检查 Launcher 隧道状态；免费隧道有流量限额，耗尽会暂停 |
| 发送端正常，但大屏连不上 | 大屏密钥未申请或填错；活动码大小写不一致；服务地址漏写端口 |
| 大屏显示「连接被拒绝 (1008)」 | sk 无效/被吊销，或该活动下设备未授权，重新申请密钥 |
| 公网弹幕通了但大屏不同步 | 检查 dev-proxy 是否监听 `0.0.0.0`（`127.0.0.1` 时局域网大屏无法访问） |
| 管理后台打不开 | 检查访问路径是否含正确的 `CUTESTAR_ADMIN_ENTRY_PATH`（大小写敏感）；入口错误会返回 404 并跳回首页 |
| 重启后数据还在吗 | 在：SQLite 文件持久化在 `server\data\`；建议定期备份该文件 |
| 电脑关机/睡眠后隧道失效 | 这是必然：单机部署依赖本机在线；可设置电源计划为“从不睡眠” |

---

## 9. 开机自启（可选）

- **后端/前端**：用 `start-dev.ps1` 或把两条启动命令做成计划任务（任务计划程序 → 创建基本任务 → 登录时启动）。
- **SakuraFrp**：Launcher 设置里勾选“开机自启动”，或同样加入计划任务。

---

## 10. 安全提醒

- 生产环境务必使用强 `CUTESTAR_JWT_SECRET` 与强管理员密码，不要使用示例值。
- frp 域名等于暴露了公网入口：管理后台入口依赖随机 `CUTESTAR_ADMIN_ENTRY_PATH`，不要外传。
- 免费隧道有带宽/流量限制，现场活动前建议先做一次压测（并发发弹幕观察延迟）。
- 大屏密钥明文仅显示一次，妥善保存；吊销后需重新申请。
