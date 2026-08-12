using System.Globalization;
using System.Windows.Media;

namespace Cutestar.Screen.Rendering;

/// <summary>弹幕颜色工具：解析服务端下发的 "#RRGGBB" 十六进制颜色。</summary>
public static class DanmakuColor
{
    public const string DefaultHex = "#FFFFFF";

    /// <summary>解析 "#RRGGBB"；无效输入回落到白色。</summary>
    public static System.Windows.Media.Color Parse(string? hex)
    {
        if (TryParse(hex, out var color))
            return color;
        return Colors.White;
    }

    public static bool TryParse(string? hex, out System.Windows.Media.Color color)
    {
        color = Colors.White;
        if (string.IsNullOrWhiteSpace(hex)) return false;
        var h = hex.Trim();
        if (h.Length != 7 || h[0] != '#') return false;
        if (int.TryParse(h.AsSpan(1, 2), NumberStyles.HexNumber, null, out var r) &&
            int.TryParse(h.AsSpan(3, 2), NumberStyles.HexNumber, null, out var g) &&
            int.TryParse(h.AsSpan(5, 2), NumberStyles.HexNumber, null, out var b))
        {
            color = System.Windows.Media.Color.FromRgb((byte)r, (byte)g, (byte)b);
            return true;
        }
        return false;
    }
}
