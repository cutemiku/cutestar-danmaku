using System.Diagnostics;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Cutestar.Screen.Controls;
using Cutestar.Screen.Models;
using Cutestar.Screen.Rendering;
using Cutestar.Screen.Services;
using Forms = System.Windows.Forms;
using Microsoft.Win32;

namespace Cutestar.Screen;

public partial class MainWindow : Window
{
    /// <summary>连接校验失败（无法连接服务器 / 活动不存在或已结束）时抛出，要求重新配置。</summary>
    private sealed class ConfigRequiredException : Exception
    {
        public ConfigRequiredException(string message) : base(message) { }
    }

    private readonly OverlayConfig _config;
    private readonly WsClient _ws = new();
    private readonly Reconnector _reconnector;
    private readonly DispatcherTimer _syncTimer = new() { Interval = TimeSpan.FromSeconds(30) };
    private readonly Queue<(string Nickname, string Content, string Color)> _replayQueue = new();
    private readonly Random _replayRng = new();
    private bool _replayDraining;
    private DateTime _lastSequenceSave = DateTime.MinValue;
    private bool _wasConnected;
    private bool _everConnected;
    private string? _lastToast;
    private DateTime _lastToastAt = DateTime.MinValue;
    private DateTime _lastSetupAt = DateTime.MinValue;
    private CancellationTokenSource? _approvalPollCts;
    private IDanmakuRenderer _renderer = null!;
    private Forms.NotifyIcon _trayIcon = null!;

    public MainWindow()
    {
        InitializeComponent();
        _config = OverlayConfig.Load();
        _reconnector = new Reconnector(ConnectAsync, isFatal: ex => ex is ConfigRequiredException);

        InitTrayIcon();

        Loaded += OnLoaded;
        Closing += OnClosing;
        // 兜底持久化：系统注销/关机（SessionEnding）或进程被结束（ProcessExit）时，
        // 即使 Closing 未触发也要把最后确认的序列号写盘，避免下次启动重放已播弹幕
        SystemEvents.SessionEnding += (_, _) => PersistSequenceNow();
        AppDomain.CurrentDomain.ProcessExit += (_, _) => PersistSequenceNow();
    }

    private void PersistSequenceNow() => _config.Save();

    private void InitTrayIcon()
    {
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("设置(_S)", null, (_, _) => Dispatcher.BeginInvoke(OpenSettings));
        menu.Items.Add("马上重连(_R)", null, (_, _) => Dispatcher.BeginInvoke(ReconnectNow));
        menu.Items.Add("清屏(_C)", null, (_, _) => Dispatcher.BeginInvoke(_renderer.Clear));
        menu.Items.Add("查看日志与运行状态(_L)", null, (_, _) => Dispatcher.BeginInvoke(OpenLogViewer));
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("退出(_X)", null, (_, _) => Dispatcher.BeginInvoke(() =>
        {
            _trayIcon.Visible = false;
            Close();
        }));

        _trayIcon = new Forms.NotifyIcon
        {
            Icon = CreateTrayIcon(),
            Text = "星萌弹幕姬 大屏",
            Visible = true,
            ContextMenuStrip = menu,
        };
        _trayIcon.DoubleClick += (_, _) => Dispatcher.BeginInvoke(OpenSettings);
    }

    private void OpenLogViewer()
    {
        new LogViewerWindow(_trayIcon.Text).Show();
    }

    private static System.Drawing.Icon CreateTrayIcon()
    {
        using var bmp = new System.Drawing.Bitmap(32, 32);
        using var g = System.Drawing.Graphics.FromImage(bmp);
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        g.Clear(System.Drawing.Color.Transparent);
        using var bgBrush = new System.Drawing.SolidBrush(
            System.Drawing.Color.FromArgb(0xE0, 0x6B, 0x3C));
        g.FillEllipse(bgBrush, 1, 1, 30, 30);
        using var font = new System.Drawing.Font("Segoe UI", 16,
            System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Pixel);
        using var textBrush = new System.Drawing.SolidBrush(System.Drawing.Color.White);
        var sf = new System.Drawing.StringFormat
        {
            Alignment = System.Drawing.StringAlignment.Center,
            LineAlignment = System.Drawing.StringAlignment.Center
        };
        g.DrawString("C", font, textBrush, 16, 17, sf);
        return System.Drawing.Icon.FromHandle(bmp.GetHicon());
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        ScreenManager.PlaceOnMonitor(this, _config.MonitorIndex);
        ScreenManager.SetClickThrough(this, enable: true);
        // 软件渲染模式下窗口常驻：从 Alt+Tab 隐藏，仅托盘/任务管理器可关闭
        ScreenManager.HideFromTaskSwitcher(this);

        var screens = ScreenManager.GetAllScreens();
        var monitorName = _config.MonitorIndex < screens.Length
            ? $"显示器 {_config.MonitorIndex + 1}" : "默认显示器";
        ScreenLog.Write($"大屏启动 · {monitorName} · 服务 {_config.ServerUrl} · 活动 {_config.ActivityCode}");
        ToastWindow.Show($"星萌弹幕姬 大屏已启动 · {monitorName}", 3500);

        // 创建渲染器并启动渲染循环
        _renderer = RendererFactory.Create(_config, DanmakuCanvas,
            () => VisualTreeHelper.GetDpi(this).PixelsPerDip);
        _renderer.Start();

        // GPU 渲染器使用自己的原生透明窗口，隐藏 WPF 窗口避免重复叠加
        if (_renderer is GpuDanmakuRenderer)
            Hide();

        _ws.OnEvent += OnWsEvent;
        // 跨重启跳过历史：携带上次持久化的序列号连接，收事件后回写 config.json
        _config.EnsureDeviceId();
        _ws.InitialSequence = _config.LastSequence;
        _ws.ScreenKey = _config.ScreenKey;
        _ws.DeviceId = _config.DeviceId;
        _ws.OnSequenceAdvanced += PersistSequence;
        _ws.OnConnectionChanged += (connected, rejectReason) =>
        {
            Debug.WriteLine($"[Overlay] WS connected={connected} reject={rejectReason}");
            ScreenLog.Write($"[Overlay] WS connected={connected} reject={rejectReason}");
            // 被服务端拒绝（close 1008）：
            //   - "等待管理员审批" → 大屏已自动注册接入请求，启动轮询领钥（不弹窗打扰）
            //   - 其他（密钥无效等）→ 配置错误，弹窗重新配置
            if (!connected && !string.IsNullOrEmpty(rejectReason))
            {
                if (rejectReason.Contains("审批"))
                {
                    _reconnector.Stop();
                    StartApprovalPolling();
                }
                else
                {
                    _reconnector.Stop(); // 停止指数退避重连，避免弹窗反复打断
                    Dispatcher.BeginInvoke(() =>
                    {
                        ToastOnce($"连接被拒绝：{rejectReason}");
                        OpenSetupRequired(rejectReason);
                    });
                }
                return;
            }
            var dropped = _wasConnected && !connected;
            var recovered = !_wasConnected && connected;
            _wasConnected = connected;
            if (connected)
                _everConnected = true;
            Dispatcher.BeginInvoke(() =>
            {
                _trayIcon.Text = connected
                    ? "星萌弹幕姬 大屏 - 已连接"
                    : "星萌弹幕姬 大屏 - 断线重连中…";
                // 已建立连接后掉线（服务器重启 / uvicorn --reload / 网络抖动）：
                // 右上角轻提示 + 立即重连；初次连接失败由 Reconnector 指数退避处理，避免空转
                if (dropped)
                {
                    ToastOnce("连接已断开，正在重连…");
                    _reconnector.Start();
                }
                else if (recovered && _everConnected)
                {
                    ToastOnce("连接已恢复");
                }
            });
        };
        // 开启服务端下发时，周期拉取管理面板保存的配置并同步（WS 事件漏收也不丢）
        _syncTimer.Tick += async (_, _) => await SyncServerOverlayAsync();
        _syncTimer.Start();
        _reconnector.Start();
    }

    private void OnClosing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _syncTimer.Stop();
        _approvalPollCts?.Cancel();
        _approvalPollCts = null;
        PersistSequenceNow(); // 持久化最后确认的序列号，下次启动跳过历史
        _renderer.Stop();
        _renderer.Dispose();
        _reconnector.Dispose();
        _ws.Dispose();
        _trayIcon.Visible = false;
        _trayIcon.Dispose();
    }

    /// <summary>记录已确认的事件序列号并节流写盘（1 秒窗口，缩短最后未落盘的时间跨度）。</summary>
    private void PersistSequence(long sequence)
    {
        _config.LastSequence = sequence;
        if ((DateTime.Now - _lastSequenceSave).TotalSeconds >= 1)
        {
            _lastSequenceSave = DateTime.Now;
            _config.Save();
        }
    }

    private async Task ConnectAsync()
    {
        var validation = await ValidateActivityAsync();
        if (!validation.Ok)
        {
            var activityMissing = validation.Message.Contains("活动不存在");
            // 初次启动从未连上（配置可能无效），或活动已注销（活动不存在）：必须重新配置
            if (!_everConnected || activityMissing)
            {
                Dispatcher.Invoke(() => OpenSetupRequired(validation.Message));
                throw new ConfigRequiredException(validation.Message);
            }
            // 正常运行中断线 / 活动结束：右上角轻提示，继续自动重试（活动重新开放后自动恢复）
            ToastOnce(validation.Message.StartsWith("活动已结束") ? "活动已结束" : validation.Message);
            throw new Exception(validation.Message);
        }

        // 服务端统一下发显示设置
        if (_config.UseServerSettings && ApplyServerOverlay(validation.Activity))
        {
            _config.Save();
            _renderer?.SetConfig(_config);
        }

        // 每次（含重连）都用最新持久化序列号连接，避免把已确认历史当补偿重放
        _ws.InitialSequence = _config.LastSequence;
        await _ws.ConnectAsync(_config.ServerUrl, validation.ActivityId);
    }

    /// <summary>右上角轻提示（自动切到 UI 线程）；相同文案 30 秒内不重复，避免重连失败循环刷屏。</summary>
    private void ToastOnce(string message)
    {
        if (message == _lastToast && (DateTime.Now - _lastToastAt).TotalSeconds < 30)
            return;
        _lastToast = message;
        _lastToastAt = DateTime.Now;
        Dispatcher.BeginInvoke(() => ToastWindow.Show(message, 3500));
    }

    private sealed record ValidationResult(bool Ok, string Message, string ActivityId, JsonElement Activity);

    private async Task<ValidationResult> ValidateActivityAsync()
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
        HttpResponseMessage resp;
        try
        {
            resp = await http.GetAsync(
                $"{_config.ServerUrl}/api/v1/public/activities/{_config.ActivityCode}");
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            return new ValidationResult(false, $"无法连接服务器（{ex.GetBaseException().Message}）", "", default);
        }

        if (resp.StatusCode == System.Net.HttpStatusCode.NotFound)
            return new ValidationResult(false, "活动不存在，请检查活动码", "", default);
        if (!resp.IsSuccessStatusCode)
            return new ValidationResult(false, $"服务端返回错误（{(int)resp.StatusCode}）", "", default);

        using var body = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
        var root = body.RootElement;

        var status = root.TryGetProperty("status", out var s) ? s.GetString() : null;
        if (status == "closed")
            return new ValidationResult(false, "活动已结束（过期），请联系活动管理员", "", default);
        if (status is not ("live" or "paused"))
            return new ValidationResult(false, $"活动状态不可用（{status ?? "未知"}）", "", default);

        var activityId = root.GetProperty("id").GetString() ?? "";
        if (string.IsNullOrEmpty(activityId))
            return new ValidationResult(false, "服务端返回的活动数据无效", "", default);

        // 活动名称与活动码解耦：仅在本地未自定义名称时同步服务端名称
        if (string.IsNullOrEmpty(_config.ActivityName) && root.TryGetProperty("name", out var name))
            _config.ActivityName = name.GetString() ?? "";

        return new ValidationResult(true, "", activityId, root.Clone());
    }

    /// <summary>应用服务端下发的显示设置（字号、速度、不透明度、字体），返回是否有变化。</summary>
    private bool ApplyServerOverlay(JsonElement activity)
    {
        var changed = false;
        if (activity.TryGetProperty("overlay_font_size", out var fontSize) && fontSize.TryGetInt32(out var fs))
        {
            var target = Math.Clamp(fs, 12, 160);
            if (Math.Abs(_config.FontSize - target) > 0.5) { _config.FontSize = target; changed = true; }
        }
        if (activity.TryGetProperty("overlay_speed", out var speed) && speed.TryGetInt32(out var sp))
        {
            var target = Math.Clamp(sp, 10, 1000);
            if (Math.Abs(_config.DanmakuSpeed - target) > 0.5) { _config.DanmakuSpeed = target; changed = true; }
        }
        if (activity.TryGetProperty("overlay_opacity", out var opacity) && opacity.TryGetDouble(out var op))
        {
            var target = Math.Clamp(op, 0.1, 1.0);
            if (Math.Abs(_config.MaxOpacity - target) > 0.001) { _config.MaxOpacity = target; changed = true; }
        }
        if (activity.TryGetProperty("overlay_font", out var font) && font.GetString() is { Length: > 0 } f)
        {
            if (_config.FontFamily != f) { _config.FontFamily = f; changed = true; }
        }
        return changed;
    }

    /// <summary>周期拉取服务端活动配置并同步显示设置（开启服务端下发时）；同时感知活动注销。</summary>
    private async Task SyncServerOverlayAsync()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
            var resp = await http.GetAsync(
                $"{_config.ServerUrl}/api/v1/public/activities/{_config.ActivityCode}");
            // 活动已注销（404）：即使 WS 未断开也要求重新配置（弹窗，60s 去重避免重复打扰）
            if (resp.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                if (_everConnected && (DateTime.Now - _lastSetupAt).TotalSeconds >= 60)
                {
                    _lastSetupAt = DateTime.Now;
                    Dispatcher.Invoke(() => OpenSetupRequired("活动已注销，请重新配置"));
                }
                return;
            }
            if (!resp.IsSuccessStatusCode || !_config.UseServerSettings) return;
            using var body = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
            if (ApplyServerOverlay(body.RootElement))
            {
                _config.Save();
                _renderer?.SetConfig(_config);
                Debug.WriteLine("[Overlay] 已从服务端同步显示配置");
                ScreenLog.Write("[Overlay] 已从服务端同步显示配置");
            }
        }
        catch
        {
            // 周期同步失败静默，等待下次轮询或 WS 事件补偿
        }
    }

    private void OpenSetupRequired(string message)
    {
        var dlg = new SetupWindow(_config, errorMessage: message) { Owner = this };
        if (dlg.ShowDialog() == true)
        {
            _config.Save();
            _renderer?.SetConfig(_config);
            _reconnector.Start();
        }
    }

    /// <summary>
    /// 手动立即重连：重置指数退避并立刻发起一次连接尝试。
    /// 用于服务端短期断线后 Reconnector 退避过长、连不回去的场景。
    /// </summary>
    private void ReconnectNow()
    {
        ToastWindow.Show("正在重新连接…", 2500);
        // 手动重连前先停掉旧循环并等待旧连接释放，避免新旧握手挤在同 1 秒内
        // （中间层常对瞬时多握手做临时封禁），再由 Reconnector 立即发起新连接
        _reconnector.Stop();
        _ = Task.Delay(1000).ContinueWith(_ => Dispatcher.BeginInvoke(_reconnector.Start));
    }

    /// <summary>
    /// 首次连接被拒（等待管理员审批）后轮询授权状态：管理员批准后自动领取 sk 并重连。
    /// </summary>
    private void StartApprovalPolling()
    {
        if (_approvalPollCts is not null) return; // 已在轮询
        _approvalPollCts = new CancellationTokenSource();
        ScreenLog.Write($"[Overlay] 大屏接入待审批，等待管理员批准…（device {_config.DeviceId[..8]}…）");
        ToastWindow.Show("已向管理员发起大屏接入请求，等待批准…", 5000);
        _ = PollApprovalAsync(_approvalPollCts.Token); // fire-and-forget：轮询由 CancellationToken 终止
    }

    private async Task PollApprovalAsync(CancellationToken ct)
    {
        var lastStatus = "";
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
                var resp = await http.GetAsync(
                    $"{_config.ServerUrl}/api/v1/public/screen-keys/status?device_id={Uri.EscapeDataString(_config.DeviceId)}", ct);
                if (!resp.IsSuccessStatusCode)
                {
                    await Task.Delay(TimeSpan.FromSeconds(5), ct);
                    continue;
                }
                using var body = JsonDocument.Parse(await resp.Content.ReadAsStringAsync(ct));
                var status = body.RootElement.TryGetProperty("status", out var s) ? s.GetString() : "";
                var key = body.RootElement.TryGetProperty("key", out var k) ? k.GetString() : "";
                if (status == "approved" && !string.IsNullOrEmpty(key))
                {
                    // 管理员已批准：保存 sk，更新配置并重连
                    _config.ScreenKey = key;
                    _ws.ScreenKey = key;
                    _config.Save();
                    _approvalPollCts = null;
                    ScreenLog.Write("[Overlay] 已获授权，正在连接…");
                    Dispatcher.BeginInvoke(() => _reconnector.Start());
                    return;
                }
                if (status != lastStatus)
                {
                    lastStatus = status;
                    ScreenLog.Write($"[Overlay] 授权状态: {status}");
                }
            }
            catch (OperationCanceledException) { return; }
            catch (Exception ex)
            {
                ScreenLog.Write($"[Overlay] 查询授权状态失败: {ex.Message}");
            }
            try { await Task.Delay(TimeSpan.FromSeconds(5), ct); }
            catch (OperationCanceledException) { return; }
        }
    }

    private void OnWsEvent(JsonElement evt)
    {
        if (!evt.TryGetProperty("type", out var typeProp)) return;
        var type = typeProp.GetString();

        if (type == "danmaku.published" && evt.TryGetProperty("payload", out var payload))
        {
            var nickname = payload.TryGetProperty("nickname", out var nn) ? nn.GetString() ?? "" : "";
            var content = payload.GetProperty("content").GetString() ?? "";
            var color = payload.TryGetProperty("color", out var c) ? c.GetString() ?? "#FFFFFF" : "#FFFFFF";
            var isReplay = evt.TryGetProperty("replay", out var replay) && replay.GetBoolean();
            ScreenLog.Write($"[Overlay] 收到弹幕{(isReplay ? "(历史补偿)" : "")}: {content}");
            // 断线补偿的历史弹幕：错峰随机延时展示，避免一股脑刷屏；实时弹幕立即上屏
            if (isReplay)
                QueueReplayDanmaku(nickname, content, color);
            else
                _renderer.Push(nickname, content, color);
        }
        else if (type == "screen.clear_requested")
        {
            ScreenLog.Write("[Overlay] 收到清屏指令");
            Dispatcher.BeginInvoke(_renderer.Clear);
        }
        else if (type == "activity.status_changed" && evt.TryGetProperty("payload", out var statusPayload))
        {
            // 运行中活动被管理员结束：右上角轻提示（不弹窗打断）
            var status = statusPayload.TryGetProperty("status", out var st) ? st.GetString() : null;
            if (status == "closed")
                ToastOnce("活动已结束");
        }
        else if (type == "activity.overlay_settings_changed" && evt.TryGetProperty("payload", out var overlay))
        {
            // 服务端在活动进行中统一下发显示设置
            if (!_config.UseServerSettings) return;
            Dispatcher.BeginInvoke(() =>
            {
                if (ApplyServerOverlay(overlay))
                {
                    _config.Save();
                    _renderer?.SetConfig(_config);
                }
            });
        }
    }

    /// <summary>供设置窗口发送测试弹幕，不经过服务器。</summary>
    public void ShowDanmakuDirect(string nickname, string content)
    {
        _renderer.Push(nickname, content, Rendering.DanmakuColor.DefaultHex);
    }

    /// <summary>断线补偿的弹幕入队，由排出循环随机延时逐条展示，避免刷屏。</summary>
    private void QueueReplayDanmaku(string nickname, string content, string color)
    {
        lock (_replayQueue)
        {
            _replayQueue.Enqueue((nickname, content, color));
            if (_replayDraining) return;
            _replayDraining = true;
        }
        _ = DrainReplayQueueAsync();
    }

    private async Task DrainReplayQueueAsync()
    {
        while (true)
        {
            (string Nickname, string Content, string Color) item;
            lock (_replayQueue)
            {
                if (_replayQueue.Count == 0)
                {
                    _replayDraining = false;
                    return;
                }
                item = _replayQueue.Dequeue();
            }
            // 每条之间随机延时 0.8~2.5s，让补偿弹幕陆陆续续出现
            await Task.Delay(TimeSpan.FromMilliseconds(_replayRng.Next(800, 2500)));
            _renderer.Push(item.Nickname, item.Content, item.Color);
        }
    }

    private void OpenSettings()
    {
        var dlg = new SettingsWindow(_config, this);
        dlg.Owner = this;
        if (dlg.ShowDialog() == true)
        {
            _config.Save();
            _renderer.SetConfig(_config);
            ScreenManager.PlaceOnMonitor(this, _config.MonitorIndex);
            ToastWindow.Show("配置已保存并生效", 2000);
        }
    }
}
