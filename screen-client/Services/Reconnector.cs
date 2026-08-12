using System.Diagnostics;

namespace Cutestar.Screen.Services;

public sealed class Reconnector : IDisposable
{
    private readonly Func<Task> _connect;
    private readonly Action<bool>? _onStatus;
    private readonly Func<Exception, bool>? _isFatal;
    private CancellationTokenSource? _cts;
    private int _attempt;

    public Reconnector(Func<Task> connect, Action<bool>? onStatus = null, Func<Exception, bool>? isFatal = null)
    {
        _connect = connect;
        _onStatus = onStatus;
        _isFatal = isFatal;
    }

    public void Start()
    {
        Stop();
        _cts = new CancellationTokenSource();
        _ = LoopAsync(_cts.Token);
    }

    public void Stop() { _cts?.Cancel(); _cts = null; _attempt = 0; }

    private async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                await _connect();
                _attempt = 0;
                _onStatus?.Invoke(true);
                await Task.Delay(Timeout.Infinite, ct);
            }
            catch (OperationCanceledException) { return; }
            catch (Exception ex)
            {
                // 致命异常（如配置无效需重新配置）：停止重试，等待用户处理
                if (_isFatal?.Invoke(ex) == true)
                {
                    Debug.WriteLine($"[Reconnector] Fatal: {ex.Message}");
                    ScreenLog.Write($"[Reconnector] 致命错误: {ex.Message}");
                    return;
                }
                _attempt++;
                // 退避从 5s 起步、封顶 60s：降低握手频率，规避中间层（ESA/防火墙）对高频
                // WS 握手的临时封禁；长退避间隙由"马上重连"菜单与断线检测兜底
                var delay = Math.Min(60, 5 * (int)Math.Pow(2, _attempt - 1));
                Debug.WriteLine($"[Reconnector] Retry {_attempt} in {delay}s: {ex.Message}");
                ScreenLog.Write($"[Reconnector] 重连 {_attempt} 次，{delay}s 后重试: {ex.Message}");
                _onStatus?.Invoke(false);
                await Task.Delay(TimeSpan.FromSeconds(delay), ct);
            }
        }
    }

    public void Dispose() => Stop();
}
