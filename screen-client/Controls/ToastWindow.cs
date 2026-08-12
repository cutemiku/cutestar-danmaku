using System.Windows;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace Cutestar.Screen.Controls;

public class ToastWindow : Window
{
    public ToastWindow(string message, int durationMs = 3000)
    {
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = System.Windows.Media.Brushes.Transparent;
        Topmost = true;
        ShowInTaskbar = false;
        Width = 340;
        Height = 56;
        Left = SystemParameters.PrimaryScreenWidth - Width - 24;
        Top = 24;

        var border = new System.Windows.Controls.Border
        {
            Background = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromArgb(0xE0, 0x2A, 0x3A, 0x2C)),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(16, 10, 16, 10),
            Child = new System.Windows.Controls.TextBlock
            {
                Text = message,
                Foreground = System.Windows.Media.Brushes.White,
                FontSize = 14,
                VerticalAlignment = VerticalAlignment.Center,
            }
        };
        Content = border;

        var fadeIn = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(250));
        border.BeginAnimation(OpacityProperty, fadeIn);

        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(durationMs) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            var fadeOut = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(400));
            fadeOut.Completed += (_, _) => Close();
            border.BeginAnimation(OpacityProperty, fadeOut);
        };
        timer.Start();
    }

    public static void Show(string message, int durationMs = 3000)
    {
        var toast = new ToastWindow(message, durationMs);
        toast.Show();
    }
}
