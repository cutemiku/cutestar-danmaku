# 星萌弹幕姬（Cutestar-Danmaku）

面向会议、发布会、年会与婚礼的**扫码弹幕互动平台**。参与者扫码进入活动，发送弹幕经过人工（或阿里云内容安全）审核后上墙；运营人员在大屏前实时控场；Windows 大屏客户端通过 WSS 主动订阅活动事件，无需暴露公网入站端口。

## 功能

- 活动码 / 二维码匿名参与，昵称自由设置
- 弹幕投稿、三级违禁词处理、人工审核 / 自动审核、撤回、暂停 / 慢速 / 清屏
- 参与者级限流与禁言（按参与者 / IP / 设备指纹）
- 基础抽奖、CSV 导出、操作审计
- 大屏配对（密钥授权、一次性下发）、断线重连与事件序号补偿
- 运营控制台实时事件流，活动 / 弹幕 / 大屏配置在线修改

## 架构

```
                          ┌─────────────────────────────────────────────┐
                          │                 云端                         │
 参与者（浏览器/小程序）──►│  ┌──────────┐   ┌────────────────────────┐  │
 运营控制台（浏览器）──────►│  │  nginx   │──►│   FastAPI 服务          │  │
 移动发送端（mobile-sender）│  │ 反代+静态 │   │  活动/审核/弹幕/密钥 API │  │
                          │  └──────────┘   │  WebSocket 事件流         │  │
                          │                 │  (sequence 序号回放)      │  │
                          │                 └──────┬──────────┬────────┘  │
                          │                        │          │          │
                          │              ┌─────────▼──┐  ┌───▼──────┐    │
                          │              │ PostgreSQL │  │  Redis   │    │
                          │              │ (或 SQLite)│  │ (可选)   │    │
                          │              └────────────┘  └──────────┘    │
                          └─────────────────────────────────────────────┘
                                          ▲  WSS（主动出网，无需入站端口）
                                          │
                               ┌──────────┴──────────┐
                               │  Windows WPF 大屏端  │
                               │  软件/GPU 渲染双实现  │
                               └─────────────────────┘
```

核心约束：所有状态变更**先落库再广播**；写操作支持幂等键；实时事件携带 `sequence`，大屏断线重连后按序号补偿，超出窗口回退拉取快照。

## 目录

- `web/`：参与者页面与运营控制台的 React + TypeScript 前端
- `server/`：Python FastAPI 模块化单体服务（活动、审核、弹幕、大屏密钥、审计）
- `screen-client/`：.NET 8 WPF Windows 大屏客户端（软件渲染 + GPU 渲染双实现）
- `mobile-sender/`：无构建的移动端发送页（单页应用，可直接部署）
- `deploy-same-origin/`：all-in-one 容器（React 前端 + mobile-sender + nginx 反代 + FastAPI 后端单容器运行）
- `infra/`：容器化本地开发与云端部署模板（PostgreSQL + Redis + 迁移）
- `docs/`：产品、API/事件与部署文档

## 本地启动

后端需要 Python 3.11+，数据库默认 PostgreSQL，可用 SQLite 免装：

```powershell
cd server
pip install -r requirements.txt
$env:CUTESTAR_DATABASE_URL = "sqlite+aiosqlite:///./dev.db"   # 可选，默认 PostgreSQL
python -m app.seed                                            # 迁移 + 播种管理员与演示活动 MEET2026
uvicorn app.main:app --reload
```

首次启动会按 `CUTESTAR_ADMIN_USERNAME` / `CUTESTAR_ADMIN_PASSWORD` 播种管理员；演示活动由 `python -m app.seed` 创建。生产环境配置项见 `server/.env.example`（JWT 密钥与管理员密码为必填）。

测试（使用 SQLite，无需数据库服务）：

```powershell
cd server
pip install -r requirements-dev.txt
pytest
```

前端需要 Node.js 18+：

```powershell
cd web
npm install
npm run dev
```

WPF 大屏客户端：

```powershell
dotnet restore screen-client\Cutestar.Screen.csproj
dotnet run --project screen-client\Cutestar.Screen.csproj
```

Windows 上一键启动（含环境检查）：

```powershell
powershell -ExecutionPolicy Bypass -File start-dev.ps1
```

## 部署

- 推荐拓扑：云端反向代理（Caddy / nginx）终止 HTTPS/WSS，服务端连接 PostgreSQL、Redis，大屏客户端仅主动出网
- 轻量场景：`deploy-same-origin/` 提供 all-in-one 单容器（React 前端 `/` + 轻量发送端 `/m/` + `/api` 与 WebSocket 反代 + FastAPI 后端），详见 `docs/deployment-runbook.md`
- 生产安全基线（TLS、CSP、响应头、密钥必填）见 `docs/deployment-runbook.md`

## 许可证

[MIT](LICENSE) © 2026 Cutestar contributors
