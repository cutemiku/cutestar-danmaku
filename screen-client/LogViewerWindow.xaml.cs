using System.Windows;
using System.Windows.Threading;
using Cutestar.Screen.Services;

namespace Cutestar.Screen;

/// <summary>运行状态与日志查看窗口：只读展示 ScreenLog 环形缓冲，定时刷新。</summary>
public partial class LogViewerWindow : Window
{
    private readonly DispatcherTimer _timer;

    /// <param name="status">当前连接状态摘要（如 "已连接 / 断线重连中"）。</param>
    public LogViewerWindow(string status)
    {
        InitializeComponent();
        StatusText.Text = status;
        RefreshLogs();
        _timer = new DispatcherTimer { Interval = System.TimeSpan.FromSeconds(2) };
        _timer.Tick += (_, _) => RefreshLogs();
        _timer.Start();
        Closed += (_, _) => _timer.Stop();
    }

    private void RefreshLogs()
    {
        LogBox.Text = string.Join("\n", ScreenLog.Snapshot());
        LogBox.ScrollToEnd();
    }

    private void OnRefresh(object sender, RoutedEventArgs e) => RefreshLogs();
}
