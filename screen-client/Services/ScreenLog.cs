using System;
using System.Collections.Generic;

namespace Cutestar.Screen.Services;

/// <summary>大屏运行日志：内存环形缓冲（上限 1000 条），供托盘"查看日志"窗口展示。
/// 线程安全：事件来自 WS 接收线程/UI 线程/后台线程，统一加锁。</summary>
public static class ScreenLog
{
    private const int MaxEntries = 1000;
    private static readonly Queue<string> Entries = new();
    private static readonly object Lock = new();

    public static void Write(string message)
    {
        var line = $"{DateTime.Now:HH:mm:ss} {message}";
        lock (Lock)
        {
            Entries.Enqueue(line);
            while (Entries.Count > MaxEntries)
                Entries.Dequeue();
        }
    }

    public static string[] Snapshot()
    {
        lock (Lock)
        {
            return Entries.ToArray();
        }
    }
}
