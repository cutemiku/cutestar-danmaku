using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.Direct2D1;
using Vortice.DirectWrite;
using Vortice.DXGI;
using Vortice.Mathematics;
using Cutestar.Screen.Models;
using Cutestar.Screen.Services;
using D2D1 = Vortice.Direct2D1;
using DCommon = Vortice.DCommon;

namespace Cutestar.Screen.Rendering;

/// <summary>
/// GPU 渲染器：Direct3D 11 + Direct2D + DirectWrite + DirectComposition。
/// 创建自己的原生透明窗口，绕开 WPF AllowsTransparency 的软件渲染限制。
/// 同屏弹幕容量 2000+ 条，稳定 60fps。
/// </summary>
public sealed class GpuDanmakuRenderer : IDanmakuRenderer
{
    private readonly OverlayConfig _config;

    // 窗口
    private IntPtr _hwnd;
    private WndProcDelegate? _wndProc;

    // D3D11 / DXGI
    private ID3D11Device _d3dDevice = null!;
    private ID3D11DeviceContext _d3dContext = null!;
    private IDXGISwapChain1 _swapChain = null!;
    private IDXGIFactory2 _factory = null!;

    // DirectComposition
    private IDCompositionDevice? _dcompDevice;
    private IDCompositionTarget? _dcompTarget;
    private IDCompositionVisual? _dcompVisual;

    // Direct2D
    private ID2D1Factory1 _d2dFactory = null!;
    private ID2D1Device _d2dDevice = null!;
    private ID2D1DeviceContext _d2dContext = null!;
    private ID2D1Bitmap1 _targetBitmap = null!;
    private ID2D1SolidColorBrush _shadowBrush = null!;

    // DirectWrite
    private IDWriteFactory _dwriteFactory = null!;
    private IDWriteTextFormat _textFormat = null!;

    // 弹幕状态
    private readonly ConcurrentQueue<Entry> _pending = new();
    private readonly List<Entry> _active = new();
    private readonly Dictionary<uint, ID2D1SolidColorBrush> _brushCache = new();
    private readonly object _lock = new();
    private CancellationTokenSource? _cts;
    private Thread? _renderThread;
    private bool _started;
    private DateTime _lastFrame = DateTime.UtcNow;

    private sealed class Entry
    {
        public required string Text { get; init; }
        public required Color4 Color { get; init; }
        public float X { get; set; }
        public float Y { get; set; }
        public float TextWidth { get; set; }
        public int Lane { get; init; }
    }

    public GpuDanmakuRenderer(OverlayConfig config)
    {
        _config = config;
    }

    public void Start()
    {
        if (_started) return;
        _started = true;
        try
        {
            CreateWindowAndDevice();
            _cts = new CancellationTokenSource();
            _renderThread = new Thread(RenderLoop)
            {
                IsBackground = true,
                Name = "GpuDanmakuRender"
            };
            _renderThread.Start();
        }
        catch (Exception ex)
        {
            _started = false;
            Cleanup();
            throw new InvalidOperationException($"GPU 渲染初始化失败: {ex.Message}", ex);
        }
    }

    public void Stop()
    {
        if (!_started) return;
        _started = false;
        _cts?.Cancel();
        _renderThread?.Join(1000);
        _cts?.Dispose();
        _cts = null;
        Clear();
        Cleanup();
    }

    public void Push(string nickname, string content, string color)
    {
        var displayText = DanmakuSanitizer.Sanitize(nickname, content);
        var height = _hwnd != IntPtr.Zero ? GetWindowHeight() : 1080;
        var maxLanes = Math.Max(1, height / _config.LaneHeight);
        var c = DanmakuColor.Parse(color);
        _pending.Enqueue(new Entry
        {
            Text = displayText,
            Color = new Color4(c.R / 255f, c.G / 255f, c.B / 255f, 1f),
            Lane = Random.Shared.Next(0, maxLanes),
        });
    }

    public void Clear()
    {
        lock (_lock) { _active.Clear(); }
        while (_pending.TryDequeue(out _)) { }
    }

    public void SetConfig(OverlayConfig config)
    {
        // 速度/透明度等参数在渲染循环中实时读取 _config；字号变化重建 textFormat。
        // config 与 _config 是同一实例（MainWindow 传入），无需替换。
        RecreateTextFormatIfNeeded();
    }

    #region 初始化

    private void CreateWindowAndDevice()
    {
        // 1. 原生透明窗口（WS_EX_NOREDIRECTIONBITMAP 支持 DirectComposition GPU 合成；
        //    WS_EX_TOOLWINDOW 使其不进入 Alt+Tab/任务视图，只能经托盘或任务管理器关闭）
        var screens = ScreenManager.GetAllScreens();
        var idx = Math.Min(_config.MonitorIndex, screens.Length - 1);
        var area = screens[idx].Bounds;

        _wndProc = WndProc;
        var wc = new WNDCLASSEX
        {
            cbSize = Marshal.SizeOf<WNDCLASSEX>(),
            lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_wndProc),
            hInstance = GetModuleHandle(null),
            lpszClassName = "CutestarGpuOverlay",
        };
        RegisterClassEx(ref wc);

        const int exStyle = WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_LAYERED
            | WS_EX_NOACTIVATE | WS_EX_NOREDIRECTIONBITMAP | WS_EX_TOOLWINDOW;
        _hwnd = CreateWindowEx(exStyle, "CutestarGpuOverlay", "星萌弹幕姬 GPU Overlay",
            WS_POPUP, area.X, area.Y, area.Width, area.Height,
            IntPtr.Zero, IntPtr.Zero, wc.hInstance, IntPtr.Zero);
        if (_hwnd == IntPtr.Zero)
            throw new InvalidOperationException($"CreateWindowEx failed: {Marshal.GetLastWin32Error()}");
        ShowWindow(_hwnd, SW_SHOW);

        // 2. D3D11 设备（BGRA 支持供 D2D 使用）
        var hr = Vortice.Direct3D11.D3D11.D3D11CreateDevice(
            IntPtr.Zero, Vortice.Direct3D.DriverType.Hardware,
            DeviceCreationFlags.BgraSupport,
            [Vortice.Direct3D.FeatureLevel.Level_11_1, Vortice.Direct3D.FeatureLevel.Level_11_0],
            out _d3dDevice, out _d3dContext);
        if (hr.Failure)
            throw new InvalidOperationException($"D3D11CreateDevice failed: {hr.Code}");

        // 3. DXGI factory + 合成 swap chain（Premultiplied alpha 透明）
        using var dxgiDevice = _d3dDevice.QueryInterface<IDXGIDevice>();
        using var adapter = dxgiDevice.GetAdapter();
        _factory = adapter.GetParent<IDXGIFactory2>();

        var desc = new SwapChainDescription1(
            area.Width, area.Height,
            Format.B8G8R8A8_UNorm, false,
            Usage.RenderTargetOutput, 2,
            Scaling.Stretch, SwapEffect.FlipSequential,
            AlphaMode.Premultiplied, SwapChainFlags.None);

        _swapChain = _factory.CreateSwapChainForComposition(_d3dDevice, desc, null);
        if (_swapChain is null)
            throw new InvalidOperationException("CreateSwapChainForComposition failed");

        // 4. DirectComposition 绑定
        _dcompDevice = DirectComposition.CreateDevice(_d3dDevice.NativePointer);
        if (_dcompDevice is null)
            throw new InvalidOperationException("DCompositionCreateDevice failed");
        ThrowHr(_dcompDevice.CreateTargetForHwnd(_hwnd, true, out _dcompTarget), "CreateTargetForHwnd");
        ThrowHr(_dcompDevice.CreateVisual(out _dcompVisual), "CreateVisual");

        // 硬检测：某些精简/远程环境 dcomp.dll 为占位实现，返回 S_OK 但不产出对象
        if (_dcompTarget is null || _dcompVisual is null)
            throw new InvalidOperationException(
                "DirectComposition 不可用（CreateTargetForHwnd/CreateVisual 未产出对象），请使用 Software 或 Auto 模式");

        ThrowHr(_dcompTarget.SetRoot(_dcompVisual), "SetRoot");
        ThrowHr(_dcompVisual.SetContent(_swapChain.NativePointer), "SetContent");
        ThrowHr(_dcompDevice.Commit(), "Commit");

        // 5. Direct2D 设备与上下文
        _d2dFactory = D2D1.D2D1.D2D1CreateFactory<ID2D1Factory1>(
            Vortice.Direct2D1.FactoryType.SingleThreaded, Vortice.Direct2D1.DebugLevel.None);
        _d2dDevice = _d2dFactory.CreateDevice(dxgiDevice);
        _d2dContext = _d2dDevice.CreateDeviceContext(DeviceContextOptions.None);

        using var surface = _swapChain.GetBuffer<IDXGISurface>(0);
        var bitmapProps = new BitmapProperties1(
            new DCommon.PixelFormat(Format.B8G8R8A8_UNorm, DCommon.AlphaMode.Premultiplied),
            96, 96,
            BitmapOptions.Target | BitmapOptions.CannotDraw);
        _targetBitmap = _d2dContext.CreateBitmapFromDxgiSurface(surface, bitmapProps);
        _d2dContext.Target = _targetBitmap;

        // 6. DirectWrite 文本格式
        _dwriteFactory = DWrite.DWriteCreateFactory<IDWriteFactory>(
            Vortice.DirectWrite.FactoryType.Shared);
        _textFormat = CreateTextFormat();

        // 7. 画刷
        _shadowBrush = _d2dContext.CreateSolidColorBrush(
            new Color4(0f, 0f, 0f, 0.7f), null);
    }

    private IDWriteTextFormat CreateTextFormat()
    {
        return _dwriteFactory.CreateTextFormat(
            _config.FontFamily,
            Vortice.DirectWrite.FontWeight.Bold,
            Vortice.DirectWrite.FontStyle.Normal,
            Vortice.DirectWrite.FontStretch.Normal,
            (float)_config.FontSize);
    }

    private void RecreateTextFormatIfNeeded()
    {
        if (_textFormat == null || _dwriteFactory == null) return;
        if (Math.Abs(_textFormat.FontSize - (float)_config.FontSize) > 0.5f)
        {
            _textFormat.Dispose();
            _textFormat = CreateTextFormat();
        }
    }

    #endregion

    #region 渲染循环

    private void RenderLoop()
    {
        var token = _cts!.Token;
        while (!token.IsCancellationRequested && _started)
        {
            try
            {
                RenderFrame();
                Thread.Sleep(16);
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[GpuRender] {ex.Message}");
                Thread.Sleep(100);
            }
        }
    }

    private void RenderFrame()
    {
        if (_d2dContext == null) return;

        var now = DateTime.UtcNow;
        var dt = (float)(now - _lastFrame).TotalSeconds;
        _lastFrame = now;
        if (dt > 0.1f) dt = 0.1f;

        var width = GetWindowWidth();
        var height = GetWindowHeight();
        if (width < 1 || height < 1) return;

        // 队列中的弹幕进场
        while (_pending.TryDequeue(out var entry))
        {
            using var layout = _dwriteFactory.CreateTextLayout(
                entry.Text, _textFormat, float.MaxValue, float.MaxValue);
            var metrics = layout.Metrics;
            entry.TextWidth = metrics.Width;
            entry.X = width;
            entry.Y = entry.Lane * _config.LaneHeight + 8;
            if (entry.Y + metrics.Height > height)
                entry.Y = Math.Max(8, height - metrics.Height - 8);
            lock (_lock) { _active.Add(entry); }
        }

        if (_active.Count == 0) return;

        RecreateTextFormatIfNeeded();

        _d2dContext.BeginDraw();
        _d2dContext.Clear(new Color4(0f, 0f, 0f, 0f)); // 全透明

        lock (_lock)
        {
            for (int i = _active.Count - 1; i >= 0; i--)
            {
                var entry = _active[i];
                entry.X -= (float)_config.DanmakuSpeed * dt;

                if (entry.X + entry.TextWidth < -20)
                {
                    _active.RemoveAt(i);
                    continue;
                }

                var rect = new Rect(entry.X, entry.Y, float.MaxValue, float.MaxValue);
                var shadowRect = new Rect(entry.X + 1.5f, entry.Y + 1.5f, float.MaxValue, float.MaxValue);
                _d2dContext.DrawText(entry.Text, _textFormat, shadowRect, _shadowBrush);
                _d2dContext.DrawText(entry.Text, _textFormat, rect, GetBrush(entry.Color));
            }
        }

        _d2dContext.EndDraw();
        _swapChain.Present(1, PresentFlags.None);
    }

    /// <summary>按颜色取 D2D 画刷，不透明度实时烘焙进 alpha（仅渲染线程访问）。</summary>
    private ID2D1SolidColorBrush GetBrush(Color4 baseColor)
    {
        var alpha = (float)_config.MaxOpacity;
        var key = PackArgb(baseColor, alpha);
        if (_brushCache.TryGetValue(key, out var brush)) return brush;
        if (_brushCache.Count > 128)
        {
            foreach (var cached in _brushCache.Values) cached.Dispose();
            _brushCache.Clear();
        }
        var created = _d2dContext.CreateSolidColorBrush(
            new Color4(baseColor.R, baseColor.G, baseColor.B, alpha), null);
        _brushCache[key] = created;
        return created;
    }

    private static uint PackArgb(Color4 c, float alpha)
    {
        var r = (uint)Math.Round(c.R * 255f);
        var g = (uint)Math.Round(c.G * 255f);
        var b = (uint)Math.Round(c.B * 255f);
        var a = (uint)Math.Round(alpha * 255f);
        return (a << 24) | (r << 16) | (g << 8) | b;
    }

    #endregion

    #region Win32

    private delegate IntPtr WndProcDelegate(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    private IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
        => DefWindowProc(hWnd, msg, wParam, lParam);

    private int GetWindowWidth()
    {
        GetClientRect(_hwnd, out var r);
        return r.Right - r.Left;
    }

    private int GetWindowHeight()
    {
        GetClientRect(_hwnd, out var r);
        return r.Bottom - r.Top;
    }

    private const int WS_POPUP = unchecked((int)0x80000000);
    private const int WS_EX_TOPMOST = 0x00000008;
    private const int WS_EX_TRANSPARENT = 0x00000020;
    private const int WS_EX_LAYERED = 0x00080000;
    private const int WS_EX_NOACTIVATE = 0x08000000;
    private const int WS_EX_NOREDIRECTIONBITMAP = 0x00200000;
    private const int WS_EX_TOOLWINDOW = 0x00000080;
    private const int SW_SHOW = 5;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WNDCLASSEX
    {
        public int cbSize;
        public int style;
        public IntPtr lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public IntPtr hInstance;
        public IntPtr hIcon;
        public IntPtr hCursor;
        public IntPtr hbrBackground;
        public string? lpszMenuName;
        public string lpszClassName;
        public IntPtr hIconSm;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern ushort RegisterClassEx(ref WNDCLASSEX lpwcx);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowEx(
        int dwExStyle, string lpClassName, string lpWindowName,
        int dwStyle, int x, int y, int nWidth, int nHeight,
        IntPtr hWndParent, IntPtr hMenu, IntPtr hInstance, IntPtr lpParam);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern IntPtr DefWindowProc(IntPtr hWnd, uint uMsg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string? lpModuleName);

    #endregion

    private static void ThrowHr(int hr, string operation)
    {
        if (hr < 0)
            throw new InvalidOperationException(
                $"DirectComposition {operation} failed (HRESULT 0x{hr:X8})");
    }

    private static void ReleaseCom<T>(T? com) where T : class
    {
        if (com is not null)
            Marshal.Release(Marshal.GetIUnknownForObject(com));
    }

    private void Cleanup()
    {
        _textFormat?.Dispose();
        foreach (var cached in _brushCache.Values) cached.Dispose();
        _brushCache.Clear();
        _shadowBrush?.Dispose();
        _targetBitmap?.Dispose();
        _d2dContext?.Dispose();
        _d2dDevice?.Dispose();
        _d2dFactory?.Dispose();
        ReleaseCom(_dcompVisual);
        ReleaseCom(_dcompTarget);
        ReleaseCom(_dcompDevice);
        _swapChain?.Dispose();
        _factory?.Dispose();
        _d3dContext?.Dispose();
        _d3dDevice?.Dispose();
        if (_hwnd != IntPtr.Zero)
        {
            DestroyWindow(_hwnd);
            _hwnd = IntPtr.Zero;
        }
    }

    public void Dispose()
    {
        Stop();
    }
}
