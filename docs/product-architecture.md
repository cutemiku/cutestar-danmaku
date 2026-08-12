# 产品架构

## 产品边界

Cutestar 只解决“参与者扫码后发弹幕，运营审核后上大屏”的互动闭环，并提供基础抽奖。云端 Python 服务是活动、审核、抽奖和审计的事实源；Web 是参与入口和运营控制台；C# WPF 是受控的展示设备。

## 部署决策

推荐云端服务与大屏分离。大屏只需主动出网连接，现场电脑或路由器故障不会让参与者投稿、审核和数据留存一起失效。大屏兼后端并用内网穿透只适合内测或封闭内网活动，不作为正式生产架构。

## MVP

活动码/二维码、匿名活动会话、昵称、弹幕投稿、三级违禁词处理、人工审核、撤回、暂停/慢速/清屏、基础抽奖、CSV 导出、审计日志、大屏配对与断线重连。

## 领域边界

- Activity：活动状态和展示配置。
- Participant：单活动匿名参与者和昵称。
- Danmaku：投稿与发布状态。
- Moderation：审核决策与原因。
- Lottery：候选快照、开奖结果和幂等。
- ScreenDevice：设备配对、心跳和订阅。
- Audit/Export：写操作审计和限时导出。

## 关键约束

所有状态变更先落库再广播；写操作使用幂等键；实时事件携带 `sequence`，大屏重连时按序号补偿，超出窗口则拉取快照。审核、抽奖和撤回不能由客户端决定。

## 大屏渲染架构：软件渲染基础版 + GPU 加速性能版

大屏端所有业务逻辑（WS 订阅、断线重连、配置、托盘、事件分发）与渲染无关，渲染层通过接口抽象，提供两套实现：

```csharp
public interface IDanmakuRenderer : IDisposable
{
    void Push(string nickname, string content);   // 入队一条弹幕
    void Clear();                                  // 清屏
    void SetConfig(OverlayConfig config);          // 速度/字号/透明度等
    void Start();                                  // 启动渲染循环
    void Stop();                                   // 停止渲染循环
}
```

- **SoftwareDanmakuRenderer（基础版）**：WPF `DrawingVisual` + `CompositionTarget.Rendering`，不依赖 GPU，任何 Windows 机器可运行；单屏同弹幕容量约 500-800 条。
- **GpuDanmakuRenderer（性能版）**：DirectComposition + D3D11/DirectWrite（Vortice 或 Win2D 封装），GPU 加速，同屏容量 2000+ 条，稳定 60fps。
- **选择策略**：配置项 `RendererMode: "Auto" | "Software" | "Gpu"`。`Auto` 模式启动时尝试初始化 GPU 设备，失败或运行中设备丢失则自动降级到软件版并提示，保证现场不翻车。

接口只包含渲染语义。业务逻辑（审核、抽奖、状态机）不得渗入渲染层，避免两套实现逐渐分叉。两套实现的文本抗锯齿、阴影和动画参数必须与 DESIGN.md 的视觉规范保持一致。
