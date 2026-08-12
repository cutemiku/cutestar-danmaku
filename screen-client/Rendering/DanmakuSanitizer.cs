using System.Text;

namespace Cutestar.Screen.Rendering;

/// <summary>渲染前文本净化：剥离控制字符（防渲染层异常/注入载体）、限制长度（防超长刷屏）。
/// 昵称与内容来自网络事件，属不可信输入，两个渲染器统一经此清洗后再绘制。</summary>
public static class DanmakuSanitizer
{
    /// <summary>昵称 + 内容拼接后的最大渲染长度（服务端单条 120 字上限 + 昵称余量）。</summary>
    public const int MaxRenderLength = 200;

    /// <summary>清洗显示文本：去除控制字符（保留换行用于多行）、截断超长。</summary>
    public static string Sanitize(string nickname, string content)
    {
        var text = string.IsNullOrEmpty(nickname) ? content : $"{nickname}：{content}";
        var sb = new StringBuilder(text.Length);
        foreach (var ch in text)
        {
            if (sb.Length >= MaxRenderLength) break;
            // 允许可见字符、空白与换行；剥离 C0/C1 控制字符（如 \u0000、转义序列）
            if (char.IsControl(ch) && ch is not ('\n' or '\t' or '\r')) continue;
            sb.Append(ch);
        }
        // 压缩连续换行为单行边界，避免多行撑破渲染布局
        var result = sb.ToString().Trim();
        var collapsed = new StringBuilder(result.Length);
        var prevNewline = false;
        foreach (var ch in result)
        {
            if (ch == '\n')
            {
                if (!prevNewline) collapsed.Append('\n');
                prevNewline = true;
            }
            else
            {
                collapsed.Append(ch);
                prevNewline = false;
            }
        }
        return collapsed.ToString().TrimEnd();
    }
}
