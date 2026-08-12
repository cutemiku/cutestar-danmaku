# Windows 大屏客户端

透明弹幕叠加层，覆盖在指定显示器的任意内容之上，鼠标事件完全穿透。

## 功能

- **首次启动配置**：首次运行弹出配置窗口，填写服务地址与活动码后才能启动
- **活动有效性校验**：启动时请求 `GET /api/v1/public/activities/{code}` 校验活动；服务器不可达、活动不存在或已结束（closed）时要求重新配置
- **透明叠加 + 鼠标穿透**：`AllowsTransparency` + `WS_EX_TRANSPARENT`，弹幕不拦截任何鼠标操作
- **多显示器支持**：在设置界面选择目标显示器，通过 Win32 API 精确定位（支持负坐标屏幕）
- **弹幕滚动**：右→左飘过，速度可配置（40-400 px/s）
- **弹幕颜色**：按服务端下发的颜色渲染（`danmaku.published` 事件携带 `color`），无效颜色回落白色；软件/GPU 渲染器视觉一致
- **自动分道**：Canvas 随机分道，避免弹幕重叠
- **显示参数服务端下发**：字号、速度、不透明度、字体四项参数可本地配置，也可开启"使用服务端统一下发的显示设置"（默认开启）由服务端下发并实时更新
- **WS 实时订阅**：连接云端 `/api/v1/activities/{id}/events`，接收 `danmaku.published` 事件
- **断线重连**：指数退避（2^n 秒，上限 30s），自动恢复连接
- **系统托盘**：右键菜单 → 设置 / 清屏 / 退出；双击打开设置
- **启动 Toast**：右上角浮窗提示启动状态，3.5 秒自动消失
- **测试弹幕**：设置窗口内可直接发送测试弹幕，无需连接服务器

## 操作方式

| 操作 | 入口 |
|---|---|
| 首次配置 | 首次启动自动弹出配置窗口 |
| 重新配置 | 启动校验失败（服务器不可达 / 活动不存在 / 活动已结束）自动弹出 |
| 打开设置 | 托盘图标双击，或托盘右键 → 设置 |
| 清屏 | 托盘右键 → 清屏 |
| 退出 | 托盘右键 → 退出 |
| 测试弹幕 | 设置窗口底部 → 输入内容 → 发送 |

## 配置

启动后通过托盘图标打开设置窗口，或直接编辑 `config.json`：

```json
{
  "ServerUrl": "http://localhost:8000",
  "ActivityCode": "MEET2026",
  "ActivityName": "春日分享会",
  "UseServerSettings": true,
  "MonitorIndex": 0,
  "DanmakuSpeed": 120,
  "FontSize": 28,
  "MaxOpacity": 0.92,
  "MaxConcurrent": 40,
  "FontFamily": "Microsoft YaHei",
  "LaneHeight": 48
}
```

| 字段 | 说明 | 默认值 |
|---|---|---|
| `ServerUrl` | 云端服务地址 | `http://localhost:8000` |
| `ActivityCode` | 要订阅的活动码（一般无需修改） | `MEET2026` |
| `ActivityName` | 活动名称（可单独修改，与活动码解耦） | 空 |
| `UseServerSettings` | 是否使用服务端统一下发的显示设置 | `true` |
| `MonitorIndex` | 目标显示器索引（0 起） | `0` |
| `DanmakuSpeed` | 弹幕速度，像素/秒（开启服务端下发时被覆盖） | `120` |
| `FontSize` | 弹幕字号（开启服务端下发时被覆盖） | `28` |
| `MaxOpacity` | 弹幕最大不透明度（开启服务端下发时被覆盖） | `0.92` |
| `MaxConcurrent` | 同屏最大弹幕数 | `40` |
| `FontFamily` | 字体（开启服务端下发时被覆盖） | `Microsoft YaHei` |
| `LaneHeight` | 单行弹道高度（像素） | `48` |

## 启动

```powershell
dotnet restore screen-client\Cutestar.Screen.csproj
dotnet run --project screen-client\Cutestar.Screen.csproj
```

## 架构

```
App (OnStartup: 首次启动 → SetupWindow 配置门)
    └── MainWindow (透明 Canvas + 鼠标穿透覆盖层)
         ├── IDanmakuRenderer  → 渲染器接口（渲染语义抽象）
         │    └── SoftwareDanmakuRenderer
         │         └── DrawingVisual + CompositionTarget.Rendering
         │              （软件渲染基础版，任何机器可运行）
         ├── RendererFactory   → 按 RendererMode 选择渲染器
         ├── WsClient          → ClientWebSocket 异步连接
         ├── Reconnector       → 指数退避自动重连（配置错误为致命异常，停止重试）
         ├── ScreenManager     → Win32 SetWindowPos 定位 + SetClickThrough 穿透
         ├── ToastWindow       → 右上角启动/保存提示浮窗
         └── NotifyIcon        → 系统托盘图标 + 右键菜单

SetupWindow (首次启动 / 连接失败要求重配)
    └── 服务地址 / 活动码 / 活动名称 / 服务端下发开关

SettingsWindow (托盘双击打开)
    └── 服务地址 / 活动码 / 活动名称 / 服务端下发开关 /
        显示器 / 字体 / 速度 / 字号 / 不透明度 / 测试弹幕
```

### 渲染器

`config.json` 中 `RendererMode` 可选值：

| 值 | 说明 |
|---|---|
| `Auto` | 默认。优先尝试 GPU 渲染，失败自动降级到软件渲染 |
| `Software` | 强制软件渲染（当前唯一实现） |
| `Gpu` | 强制 GPU 渲染（尚未实现，会抛出明确错误） |

渲染层只包含渲染语义，业务逻辑（WS 订阅、审核、抽奖）不渗入渲染层。
