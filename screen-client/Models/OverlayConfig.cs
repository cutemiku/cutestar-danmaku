using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Cutestar.Screen.Models;

public sealed class OverlayConfig
{
    private static readonly string ConfigPath =
        Path.Combine(AppContext.BaseDirectory, "config.json");

    public string ServerUrl { get; set; } = "http://localhost:8000";
    public string ActivityCode { get; set; } = "MEET2026";
    public string ActivityName { get; set; } = "";
    public bool UseServerSettings { get; set; } = true;
    public int MonitorIndex { get; set; } = 0;
    public string RendererMode { get; set; } = "Auto";
    public double DanmakuSpeed { get; set; } = 120;
    public double FontSize { get; set; } = 28;
    public double MaxOpacity { get; set; } = 0.92;
    public int MaxConcurrent { get; set; } = 40;
    public string FontFamily { get; set; } = "Microsoft YaHei";
    public int LaneHeight { get; set; } = 48;
    /// <summary>上次确认的事件序列号：跨重启跳过已处理的历史事件，避免重放。</summary>
    public long LastSequence { get; set; }

    /// <summary>大屏授权密钥：管理面板为活动申请，连接时携带才能读取弹幕事件。</summary>
    public string ScreenKey { get; set; } = "";

    /// <summary>设备标识：首次启动生成并持久化，作为大屏接入请求与领钥凭证。</summary>
    public string DeviceId { get; set; } = "";

    public static bool ConfigExists() => File.Exists(ConfigPath);

    /// <summary>校验服务地址：必须为 http/https 且含主机名（防任意协议/内网 SSRF 注入）。</summary>
    public static bool IsValidServerUrl(string url)
    {
        return Uri.TryCreate(url, UriKind.Absolute, out var uri)
            && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
            && !string.IsNullOrEmpty(uri.Host);
    }

    /// <summary>校验活动码：3-32 位字母数字（与服务端 ActivityCreate 规则一致）。</summary>
    public static bool IsValidActivityCode(string code)
        => code.Length >= 3 && code.Length <= 32 && code.All(char.IsLetterOrDigit);

    /// <summary>校验大屏密钥：非空且长度合理（服务端生成值通常 ≥ 43 字符）。</summary>
    public static bool IsValidScreenKey(string key)
        => !string.IsNullOrWhiteSpace(key) && key.Length >= 16;

    public static OverlayConfig Load()
    {
        OverlayConfig cfg;
        if (!ConfigExists())
            return new OverlayConfig();
        try
        {
            var json = File.ReadAllText(ConfigPath);
            cfg = JsonSerializer.Deserialize<OverlayConfig>(json) ?? new OverlayConfig();
        }
        catch
        {
            return new OverlayConfig();
        }
        // 防篡改：config.json 被改坏时回退安全默认值，避免注入任意 URL/跳事件
        if (!IsValidServerUrl(cfg.ServerUrl))
            cfg.ServerUrl = "http://localhost:8000";
        if (!IsValidActivityCode(cfg.ActivityCode))
            cfg.ActivityCode = "MEET2026";
        if (cfg.LastSequence < 0)
            cfg.LastSequence = 0;
        return cfg;
    }

    public void Save()
    {
        var opts = new JsonSerializerOptions { WriteIndented = true };
        File.WriteAllText(ConfigPath, JsonSerializer.Serialize(this, opts));
    }

    /// <summary>确保设备标识存在：首次调用生成并落盘，之后保持稳定（接入请求与领钥凭证）。</summary>
    public void EnsureDeviceId()
    {
        if (!string.IsNullOrEmpty(DeviceId)) return;
        DeviceId = Guid.NewGuid().ToString("N");
        Save();
    }
}
