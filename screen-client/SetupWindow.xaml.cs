using System.Windows;
using Cutestar.Screen.Models;

namespace Cutestar.Screen;

/// <summary>首次启动或连接失败时要求重新配置基础信息的对话框。</summary>
public partial class SetupWindow : Window
{
    private readonly OverlayConfig _config;

    /// <param name="firstLaunch">首次启动模式（无错误提示，标题为“首次配置”）。</param>
    /// <param name="errorMessage">重新配置时的失败原因，显示为红色提示。</param>
    public SetupWindow(OverlayConfig config, bool firstLaunch = false, string? errorMessage = null)
    {
        InitializeComponent();
        _config = config;

        Title = firstLaunch ? "首次配置" : "重新配置";
        TitleLabel.Text = firstLaunch ? "首次配置大屏客户端" : "需要重新配置";
        if (!string.IsNullOrEmpty(errorMessage))
        {
            Message.Text = $"无法连接活动：{errorMessage}";
            Message.Visibility = Visibility.Visible;
        }

        ServerUrl.Text = config.ServerUrl;
        ActivityCode.Text = config.ActivityCode;
        ScreenKey.Text = config.ScreenKey;
        ActivityName.Text = config.ActivityName;
        UseServerSettings.IsChecked = config.UseServerSettings;
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        var serverUrl = ServerUrl.Text.Trim();
        var activityCode = ActivityCode.Text.Trim().ToUpper();
        var screenKey = ScreenKey.Text.Trim();
        if (!OverlayConfig.IsValidServerUrl(serverUrl))
        {
            Message.Text = "服务地址无效：请填写 http(s):// 开头的完整地址";
            Message.Visibility = Visibility.Visible;
            return;
        }
        if (!OverlayConfig.IsValidActivityCode(activityCode))
        {
            Message.Text = "活动码无效：3-32 位字母数字";
            Message.Visibility = Visibility.Visible;
            return;
        }
        if (!OverlayConfig.IsValidScreenKey(screenKey))
        {
            Message.Text = "请在管理面板为活动申请大屏密钥并填写";
            Message.Visibility = Visibility.Visible;
            return;
        }

        _config.ServerUrl = serverUrl;
        // 切换活动码后重置序列号，避免用旧活动的进度跳过新活动的事件
        if (activityCode != _config.ActivityCode)
            _config.LastSequence = 0;
        _config.ActivityCode = activityCode;
        _config.ScreenKey = screenKey;
        _config.ActivityName = ActivityName.Text.Trim();
        _config.UseServerSettings = UseServerSettings.IsChecked == true;
        _config.Save();
        DialogResult = true;
    }

    private void OnExit(object sender, RoutedEventArgs e) => DialogResult = false;
}
