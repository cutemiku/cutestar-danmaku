"""内存速率限制：单 worker 场景的简单滑动窗口限速（Redis 留空时的默认实现）。

生产多 worker 时需替换为 Redis 计数器，但当前架构（单 uvicorn worker）内存即可。
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from fastapi import WebSocket as FastAPIWebSocket

logger = None  # 不在此处引入日志，避免循环依赖


class SlidingWindowLimiter:
    """按 key 的滑动窗口限速：窗口内最多允许 max_requests 次。

    线程安全性：uvicorn 单 worker 事件循环下，协程间无并发数据竞争（同线程切换），
    此处不额外加锁；若未来启用多 worker 需换 Redis。
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.max_requests:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        hits.append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# 限速规则（可按需调整）：
# - 管理员登录：单 IP 每 5 分钟最多 20 次尝试（防暴力破解）
# - 发弹幕：单参与者每 10 秒最多 5 条（配合活动级 slow_mode）
# - 加入活动：单 IP 每 10 秒最多 3 次（防批量注册参与者）
# - WebSocket 连接：单 IP 最多 8 个并发（防连接耗尽）
admin_login_limiter = SlidingWindowLimiter(max_requests=20, window_seconds=300)
danmaku_limiter = SlidingWindowLimiter(max_requests=5, window_seconds=10)
join_limiter = SlidingWindowLimiter(max_requests=3, window_seconds=10)
ws_limiter = SlidingWindowLimiter(max_requests=8, window_seconds=300)


def client_ip(request: Request | FastAPIWebSocket) -> str:
    """与 main._client_ip 一致的取法：优先 X-Forwarded-For 首段，否则直连地址。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"
