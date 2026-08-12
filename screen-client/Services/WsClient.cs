using System.Diagnostics;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace Cutestar.Screen.Services;

public sealed class WsClient : IDisposable
{
    public event Action<JsonElement>? OnEvent;
    /// <summary>连接状态变化；rejectReason 非空表示被服务端拒绝（如密钥无效），区别于普通断线。</summary>
    public event Action<bool, string?>? OnConnectionChanged;
    public event Action<long>? OnSequenceAdvanced;

    private ClientWebSocket? _ws;
    private CancellationTokenSource? _cts;
    private long _lastSequence;
    private bool _disposed;

    public bool IsConnected => _ws?.State == WebSocketState.Open;

    /// <summary>连接时携带的初始序列号（上次持久化的进度），跨重启跳过历史事件。</summary>
    public long InitialSequence { get; set; }

    /// <summary>大屏授权密钥：管理面板申请后配置，连接时携带才能读取弹幕事件。</summary>
    public string ScreenKey { get; set; } = "";

    /// <summary>设备标识：接入请求与自动领钥凭证。</summary>
    public string DeviceId { get; set; } = "";

    public async Task ConnectAsync(string serverUrl, string activityId, CancellationToken ct = default)
    {
        if (_disposed) return;
        Disconnect();

        _lastSequence = InitialSequence;
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _ws = new ClientWebSocket();
        // 宝塔 WAF 等防护会拦截无 Origin / 非浏览器 UA 的 WebSocket 握手（表现为 403），
        // 补齐浏览器特征请求头以通过防护；服务端不校验 Origin，不影响鉴权。
        _ws.Options.SetRequestHeader(
            "Origin",
            serverUrl.Replace("ws://", "http://").Replace("wss://", "https://"));
        _ws.Options.SetRequestHeader(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36");

        var wsUrl = serverUrl.Replace("http://", "ws://").Replace("https://", "wss://")
            + $"/api/v1/activities/{activityId}/events?last_sequence={_lastSequence}";
        if (!string.IsNullOrEmpty(ScreenKey))
            wsUrl += $"&sk={Uri.EscapeDataString(ScreenKey)}";
        if (!string.IsNullOrEmpty(DeviceId))
            wsUrl += $"&device_id={Uri.EscapeDataString(DeviceId)}";

        try
        {
            await _ws.ConnectAsync(new Uri(wsUrl), _cts.Token);
            // 服务端可能在握手成功后立即 close（如大屏密钥无效 close 1008），此时 ConnectAsync
            // 返回成功。接收循环首帧会收到 Close 帧并上报拒绝原因，MainWindow 据此区分"配置被拒"
            // 与"运行中断线"。连接成功状态先上报，由 MainWindow 的首次连接逻辑处理。
            OnConnectionChanged?.Invoke(true, null);
            _ = ReceiveLoopAsync(_cts.Token);
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[WsClient] Connect failed: {ex.Message}");
            ScreenLog.Write($"[WsClient] 连接失败: {ex.Message}");
            OnConnectionChanged?.Invoke(false, null);
            throw; // 让 Reconnector 感知到连接失败并触发指数退避重试
        }
    }

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        var buffer = new byte[8192];
        try
        {
            while (!ct.IsCancellationRequested && _ws?.State == WebSocketState.Open)
            {
                var sb = new StringBuilder();
                WebSocketReceiveResult result;
                do
                {
                    result = await _ws.ReceiveAsync(buffer, ct);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        // 拒绝（1008）或异常关闭时携带原因；正常关闭（1000）reason 为空，作普通断线
                        var reason = result.CloseStatus == WebSocketCloseStatus.PolicyViolation
                            ? (result.CloseStatusDescription ?? "被服务器拒绝")
                            : "";
                        OnConnectionChanged?.Invoke(false, reason);
                        return;
                    }
                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                } while (!result.EndOfMessage);

                var msg = sb.ToString();
                if (string.IsNullOrWhiteSpace(msg)) continue;

                try
                {
                    var doc = JsonDocument.Parse(msg);
                    var root = doc.RootElement;
                    if (root.TryGetProperty("sequence", out var seq))
                    {
                        _lastSequence = seq.GetInt64();
                        // 回传已确认的序列号，让服务端知道客户端的进度
                        _ = SendLastSequenceAsync(_lastSequence, ct);
                        OnSequenceAdvanced?.Invoke(_lastSequence);
                    }
                    OnEvent?.Invoke(root.Clone());
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"[WsClient] Parse error: {ex.Message}");
                    ScreenLog.Write($"[WsClient] 消息解析失败: {ex.Message}");
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (WebSocketException ex)
        {
            Debug.WriteLine($"[WsClient] WS error: {ex.Message}");
            ScreenLog.Write($"[WsClient] WS 异常: {ex.Message}");
        }
        finally
        {
            OnConnectionChanged?.Invoke(false, null);
        }
    }

    private async Task SendLastSequenceAsync(long sequence, CancellationToken ct)
    {
        try
        {
            if (_ws?.State != WebSocketState.Open) return;
            var json = JsonSerializer.Serialize(new { last_sequence = sequence });
            var bytes = Encoding.UTF8.GetBytes(json);
            await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, ct);
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[WsClient] Send ack failed: {ex.Message}");
            ScreenLog.Write($"[WsClient] 序列号回传失败: {ex.Message}");
        }
    }

    public void Disconnect()
    {
        try
        {
            _cts?.Cancel();
            if (_ws?.State == WebSocketState.Open)
                _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None).Wait(1000);
            _ws?.Dispose();
        }
        catch { }
        _ws = null;
        _cts = null;
    }

    public void Dispose()
    {
        _disposed = true;
        Disconnect();
    }
}
