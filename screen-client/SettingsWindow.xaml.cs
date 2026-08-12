using System.Windows;
using Cutestar.Screen.Models;
using Cutestar.Screen.Services;

namespace Cutestar.Screen;

public partial class SettingsWindow : Window
{
    private static readonly string[] CommonFonts =
    {
        "Microsoft YaHei", "Segoe UI", "DengXian", "SimHei", "KaiTi",
        "Microsoft JhengHei", "SimSun", "Arial",
    };

    private readonly OverlayConfig _config;
    private readonly MainWindow _overlay;

    public SettingsWindow(OverlayConfig config, MainWindow overlay)
    {
        InitializeComponent();
        _config = config;
        _overlay = overlay;

        ServerUrl.Text = config.ServerUrl;
        ActivityCode.Text = config.ActivityCode;
        ScreenKey.Text = config.ScreenKey;
        ActivityName.Text = config.ActivityName;
        UseServerSettings.IsChecked = config.UseServerSettings;
        UpdateServerSettingsHint();
        SpeedSlider.Value = config.DanmakuSpeed;
        FontSlider.Value = config.FontSize;
        OpacitySlider.Value = config.MaxOpacity;

        SpeedLabel.Text = $"  {config.DanmakuSpeed:F0} px/s";
        FontLabel.Text = $"  {config.FontSize:F0}px";
        OpacityLabel.Text = $"  {config.MaxOpacity:P0}";

        foreach (var font in CommonFonts)
            FontCombo.Items.Add(font);
        FontCombo.Text = config.FontFamily;

        var screens = ScreenManager.GetAllScreens();
        for (int i = 0; i < screens.Length; i++)
        {
            var s = screens[i];
            var label = $"显示器 {i + 1}：{s.Bounds.Width}×{s.Bounds.Height}";
            if (s.Primary) label += "（主显示器）";
            MonitorCombo.Items.Add(label);
        }
        MonitorCombo.SelectedIndex = Math.Min(config.MonitorIndex, screens.Length - 1);
    }

    private void OnServerSettingsToggled(object sender, RoutedEventArgs e) => UpdateServerSettingsHint();

    private void UpdateServerSettingsHint()
    {
        if (ServerSettingsHint == null) return;
        ServerSettingsHint.Text = UseServerSettings.IsChecked == true
            ? "已开启服务端下发：以下本地参数会在连接后被服务端统一下发的值覆盖。"
            : "已关闭服务端下发：使用下方本地参数。";
    }

    private void OnSpeedChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (SpeedLabel != null)
            SpeedLabel.Text = $"  {SpeedSlider.Value:F0} px/s";
    }

    private void OnFontChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (FontLabel != null)
            FontLabel.Text = $"  {FontSlider.Value:F0}px";
    }

    private void OnOpacityChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (OpacityLabel != null)
            OpacityLabel.Text = $"  {OpacitySlider.Value:P0}";
    }

    private void OnSendTest(object sender, RoutedEventArgs e)
    {
        var content = TestContent.Text.Trim();
        if (string.IsNullOrEmpty(content)) return;
        _overlay.ShowDanmakuDirect("测试", content);
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        var newServerUrl = ServerUrl.Text.Trim();
        var newCode = ActivityCode.Text.Trim().ToUpper();
        var newScreenKey = ScreenKey.Text.Trim();
        if (!OverlayConfig.IsValidServerUrl(newServerUrl))
        {
            System.Windows.MessageBox.Show(this, "服务地址无效：请填写 http(s):// 开头的完整地址", "配置错误");
            return;
        }
        if (!OverlayConfig.IsValidActivityCode(newCode))
        {
            System.Windows.MessageBox.Show(this, "活动码无效：3-32 位字母数字", "配置错误");
            return;
        }
        if (!OverlayConfig.IsValidScreenKey(newScreenKey))
        {
            System.Windows.MessageBox.Show(this, "大屏密钥无效：请在管理面板为活动申请", "配置错误");
            return;
        }

        _config.ServerUrl = newServerUrl;
        // 切换活动码后重置序列号，避免用旧活动的进度跳过新活动的事件
        if (newCode != _config.ActivityCode)
            _config.LastSequence = 0;
        _config.ActivityCode = newCode;
        _config.ScreenKey = newScreenKey;
        _config.ActivityName = ActivityName.Text.Trim();
        _config.UseServerSettings = UseServerSettings.IsChecked == true;
        _config.MonitorIndex = MonitorCombo.SelectedIndex;
        _config.FontFamily = string.IsNullOrWhiteSpace(FontCombo.Text) ? "Microsoft YaHei" : FontCombo.Text.Trim();
        _config.DanmakuSpeed = SpeedSlider.Value;
        _config.FontSize = FontSlider.Value;
        _config.MaxOpacity = OpacitySlider.Value;
        _config.Save();
        DialogResult = true;
    }

    private void OnCancel(object sender, RoutedEventArgs e) => DialogResult = false;
}
