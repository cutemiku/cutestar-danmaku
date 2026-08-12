using System.Runtime.InteropServices;

namespace Cutestar.Screen.Services;

public static class ScreenManager
{
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter,
        int x, int y, int cx, int cy, uint flags);

    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll")]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_SHOWWINDOW = 0x0040;

    private const int GWL_EXSTYLE = -20;
    private const int WS_EX_TRANSPARENT = 0x00000020;
    private const int WS_EX_LAYERED = 0x00080000;
    private const int WS_EX_TOOLWINDOW = 0x00000080;

    public static System.Windows.Forms.Screen[] GetAllScreens()
        => System.Windows.Forms.Screen.AllScreens;

    public static void PlaceOnMonitor(System.Windows.Window wpfWindow, int monitorIndex)
    {
        var screens = GetAllScreens();
        if (monitorIndex < 0 || monitorIndex >= screens.Length)
            monitorIndex = 0;

        var area = screens[monitorIndex].Bounds;
        var helper = new System.Windows.Interop.WindowInteropHelper(wpfWindow);
        SetWindowPos(helper.Handle, HWND_TOPMOST,
            area.X, area.Y, area.Width, area.Height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW);
    }

    public static void SetClickThrough(System.Windows.Window wpfWindow, bool enable)
    {
        var hwnd = new System.Windows.Interop.WindowInteropHelper(wpfWindow).Handle;
        var exStyle = GetWindowLong(hwnd, GWL_EXSTYLE);
        if (enable)
            SetWindowLong(hwnd, GWL_EXSTYLE, exStyle | WS_EX_TRANSPARENT | WS_EX_LAYERED);
        else
            SetWindowLong(hwnd, GWL_EXSTYLE, exStyle & ~WS_EX_TRANSPARENT);
    }

    /// <summary>工具窗口样式：不进入 Alt+Tab / 任务视图，只能经托盘菜单或任务管理器关闭。</summary>
    public static void HideFromTaskSwitcher(System.Windows.Window wpfWindow)
    {
        var hwnd = new System.Windows.Interop.WindowInteropHelper(wpfWindow).Handle;
        var exStyle = GetWindowLong(hwnd, GWL_EXSTYLE);
        SetWindowLong(hwnd, GWL_EXSTYLE, exStyle | WS_EX_TOOLWINDOW);
    }
}
