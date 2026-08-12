using System.Windows;
using Cutestar.Screen.Models;

namespace Cutestar.Screen;

public partial class App : System.Windows.Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var config = OverlayConfig.Load();

        // 首次启动：必须先完成基础配置（服务地址 + 活动码）
        if (!OverlayConfig.ConfigExists())
        {
            var setup = new SetupWindow(config, firstLaunch: true)
            {
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
            };
            if (setup.ShowDialog() != true)
            {
                Shutdown();
                return;
            }
        }

        new MainWindow().Show();
    }
}
