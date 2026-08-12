using Cutestar.Screen.Models;

namespace Cutestar.Screen.Rendering;

/// <summary>
/// 大屏弹幕渲染器抽象。业务逻辑（WS 订阅、审核、抽奖）不得渗入渲染层。
/// 现有实现：SoftwareDanmakuRenderer（软件渲染）；未来：GpuDanmakuRenderer。
/// </summary>
public interface IDanmakuRenderer : IDisposable
{
    /// <summary>入队一条弹幕。color 为 "#RRGGBB" 十六进制，无效时渲染为白色。</summary>
    void Push(string nickname, string content, string color);

    /// <summary>清屏并清空待渲染队列。</summary>
    void Clear();

    /// <summary>更新渲染参数（速度/字号/透明度等），实时生效。</summary>
    void SetConfig(OverlayConfig config);

    /// <summary>启动渲染循环。</summary>
    void Start();

    /// <summary>停止渲染循环并清理当前画面。</summary>
    void Stop();
}
