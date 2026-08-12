using Cutestar.Screen.Models;

namespace Cutestar.Screen.Rendering;

/// <summary>
/// 按 RendererMode 创建渲染器。
/// Auto 模式下优先尝试 GPU 渲染，失败自动降级到软件渲染。
/// </summary>
public static class RendererFactory
{
    public static IDanmakuRenderer Create(OverlayConfig config, System.Windows.Controls.Panel host, Func<double> getPixelsPerDip)
    {
        var mode = config.RendererMode.ToLowerInvariant();

        if (mode == "auto")
        {
            try
            {
                var gpu = new GpuDanmakuRenderer(config);
                gpu.Start();
                return gpu;
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[RendererFactory] GPU 初始化失败，降级到软件渲染: {ex.Message}");
            }
            return CreateSoftware(config, host, getPixelsPerDip);
        }

        if (mode == "gpu")
        {
            var gpu = new GpuDanmakuRenderer(config);
            gpu.Start();
            return gpu;
        }

        // software 或其他值
        return CreateSoftware(config, host, getPixelsPerDip);
    }

    private static IDanmakuRenderer CreateSoftware(OverlayConfig config, System.Windows.Controls.Panel host, Func<double> getPixelsPerDip)
    {
        var renderer = new SoftwareDanmakuRenderer(host, getPixelsPerDip);
        renderer.SetConfig(config);
        return renderer;
    }
}
