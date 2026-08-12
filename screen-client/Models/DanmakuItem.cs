using System.Windows.Controls;

namespace Cutestar.Screen.Models;

public sealed class DanmakuItem
{
    public required string Id { get; init; }
    public required string Nickname { get; init; }
    public required string Content { get; init; }
    public required TextBlock Visual { get; init; }
    public int Lane { get; set; }
}
