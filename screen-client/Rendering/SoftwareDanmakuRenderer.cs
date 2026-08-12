using System.Collections.Concurrent;
using System.Globalization;
using System.Windows;
using System.Windows.Media;
using Cutestar.Screen.Models;

namespace Cutestar.Screen.Rendering;

/// <summary>
/// 软件渲染器：WPF DrawingVisual + CompositionTarget.Rendering。
/// 不依赖 GPU，任何 Windows 机器可运行；单屏弹幕容量约 500-800 条。
/// </summary>
public sealed class SoftwareDanmakuRenderer : IDanmakuRenderer
{
    private readonly System.Windows.Controls.Panel _host;
    private readonly Func<double> _getPixelsPerDip;
    private readonly ConcurrentQueue<Entry> _pending = new();
    private readonly List<Entry> _active = new();
    private readonly Dictionary<System.Windows.Media.Color, System.Windows.Media.Brush> _brushCache = new();
    private OverlayConfig _config = null!;
    private DateTime _lastFrame = DateTime.UtcNow;
    private bool _started;

    private sealed class Entry
    {
        public required string Text { get; init; }
        public required System.Windows.Media.Color Color { get; init; }
        public double X { get; set; }
        public double Y { get; set; }
        public double TextWidth { get; set; }
        public int Lane { get; init; }
    }

    public SoftwareDanmakuRenderer(System.Windows.Controls.Panel host, Func<double> getPixelsPerDip)
    {
        _host = host;
        _getPixelsPerDip = getPixelsPerDip;
    }

    public void Start()
    {
        if (_started) return;
        _started = true;
        CompositionTarget.Rendering += OnRendering;
    }

    public void Stop()
    {
        if (!_started) return;
        _started = false;
        CompositionTarget.Rendering -= OnRendering;
        Clear();
        _brushCache.Clear();
    }

    public void Push(string nickname, string content, string color)
    {
        var displayText = DanmakuSanitizer.Sanitize(nickname, content);
        var canvasH = _host.ActualHeight > 0 ? _host.ActualHeight : SystemParameters.PrimaryScreenHeight;
        var maxLanes = Math.Max(1, (int)(canvasH / _config.LaneHeight));

        _pending.Enqueue(new Entry
        {
            Text = displayText,
            Color = DanmakuColor.Parse(color),
            Lane = Random.Shared.Next(0, maxLanes),
        });
    }

    public void Clear()
    {
        _active.Clear();
        while (_pending.TryDequeue(out _)) { }
        _host.Children.Clear();
    }

    public void SetConfig(OverlayConfig config)
    {
        _config = config;
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        if (_config is null) return;

        var now = DateTime.UtcNow;
        var dt = (now - _lastFrame).TotalSeconds;
        _lastFrame = now;
        if (dt > 0.1) dt = 0.1;

        var canvasW = _host.ActualWidth;
        var canvasH = _host.ActualHeight;
        if (canvasW < 1 || canvasH < 1) return;

        var shadowBrush = new SolidColorBrush(System.Windows.Media.Color.FromArgb(179, 0, 0, 0)); // 黑色 70% 阴影（与 GPU 渲染器一致）

        while (_pending.TryDequeue(out var entry))
        {
            var ft = CreateFormattedText(entry.Text, GetBrush(entry.Color));
            entry.TextWidth = ft.Width;
            entry.X = canvasW;
            entry.Y = entry.Lane * _config.LaneHeight + 8;
            if (entry.Y + ft.Height > canvasH)
                entry.Y = Math.Max(8, canvasH - ft.Height - 8);
            _active.Add(entry);
        }

        if (_active.Count == 0) return;

        var dv = new DrawingVisual();
        using (var dc = dv.RenderOpen())
        {
            for (int i = _active.Count - 1; i >= 0; i--)
            {
                var entry = _active[i];
                entry.X -= _config.DanmakuSpeed * dt;

                if (entry.X + entry.TextWidth < -20)
                {
                    _active.RemoveAt(i);
                    continue;
                }

                var text = CreateFormattedText(entry.Text, GetBrush(entry.Color));
                var shadow = CreateFormattedText(entry.Text, shadowBrush);
                dc.DrawText(shadow, new System.Windows.Point(entry.X + 1.5, entry.Y + 1.5));
                dc.DrawText(text, new System.Windows.Point(entry.X, entry.Y));
            }
        }

        _host.Children.Clear();
        _host.Children.Add(new VisualHost(dv));
    }

    /// <summary>按颜色取缓存画刷，不透明度实时烘焙进颜色 alpha（缓存上限防内存膨胀）。</summary>
    private System.Windows.Media.Brush GetBrush(System.Windows.Media.Color baseColor)
    {
        var alpha = (byte)Math.Round(255 * _config.MaxOpacity);
        var key = System.Windows.Media.Color.FromArgb(alpha, baseColor.R, baseColor.G, baseColor.B);
        if (_brushCache.TryGetValue(key, out var brush)) return brush;
        if (_brushCache.Count > 128) _brushCache.Clear();
        var created = new SolidColorBrush(key);
        created.Freeze();
        _brushCache[key] = created;
        return created;
    }

    private FormattedText CreateFormattedText(string text, System.Windows.Media.Brush brush)
    {
        var dpi = _getPixelsPerDip();
        return new FormattedText(
            text,
            CultureInfo.CurrentUICulture,
            System.Windows.FlowDirection.LeftToRight,
            new System.Windows.Media.Typeface(
                new System.Windows.Media.FontFamily(_config.FontFamily),
                System.Windows.FontStyles.Normal,
                System.Windows.FontWeights.Bold,
                System.Windows.FontStretches.Normal),
            _config.FontSize,
            brush,
            dpi);
    }

    public void Dispose()
    {
        Stop();
    }

    private sealed class VisualHost : UIElement
    {
        private readonly DrawingVisual _visual;
        public VisualHost(DrawingVisual visual) { _visual = visual; }
        protected override int VisualChildrenCount => 1;
        protected override Visual GetVisualChild(int index) => _visual;
    }
}
