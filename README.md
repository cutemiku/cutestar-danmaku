# Cutestar Danmaku

面向会议与线下活动的扫码弹幕互动平台。核心服务运行在云端，Windows 大屏客户端通过 WSS 主动订阅活动；大屏不承担公网后端。

## 目录

- `web/`：参与者页面与运营控制台的 React + TypeScript 前端。
- `server/`：Python FastAPI 模块化单体服务。
- `screen-client/`：.NET 8 WPF Windows 大屏客户端。
- `docs/`：产品、API/事件和部署文档。
- `infra/`：容器化本地开发与云端部署模板。

## 当前状态

这是第一版可审查骨架，已包含可运行的服务端健康检查、活动与弹幕 API、实时事件协议、Web 前端原型和 WPF 客户端工程边界。数据库、鉴权、Redis 扇出和生产部署仍需按文档继续实现。

## 本地启动

后端需要 Python 3.11+ 和一个数据库。默认连接 PostgreSQL，也可用 SQLite 免装数据库：

```powershell
cd server
pip install -r requirements.txt
$env:CUTESTAR_DATABASE_URL = "sqlite+aiosqlite:///./dev.db"   # 可选，默认 PostgreSQL
python -m app.seed                                            # 初始化表结构并创建演示活动 MEET2026
uvicorn app.main:app --reload
```

首次启动会自动建表并按 `CUTESTAR_ADMIN_USERNAME` / `CUTESTAR_ADMIN_PASSWORD` 播种管理员；演示活动由 `python -m app.seed` 创建。生产环境配置项见 `server/.env.example`。

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

WPF 客户端：

```powershell
dotnet restore screen-client\Cutestar.Screen.csproj
dotnet run --project screen-client\Cutestar.Screen.csproj
```
