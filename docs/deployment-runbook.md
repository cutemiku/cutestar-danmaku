# 部署运行手册

## 推荐拓扑

参与者浏览器、运营控制台和 WPF 大屏均通过 HTTPS/WSS 访问云端反向代理。Python 服务连接 PostgreSQL、Redis 和对象存储。大屏不开放公网入站端口。

## TLS 强制部署（安全基线）

**现场 Wi-Fi 环境下所有流量（弹幕内容、参与者令牌、管理员密码）都应走 HTTPS/WSS，明文 HTTP 可被任意嗅探。** 生产部署必须满足：

1. **反向代理终止 TLS**：推荐 Caddy（自动证书）或 nginx，将 `https://danmaku.example.com` 反代到后端 8000 端口；`docker-compose.yml` 的 8000 端口不要直接暴露公网。
2. **各端连接地址配置**：
   - **大屏客户端**（SetupWindow/SettingsWindow「服务地址」）：填写 `https://danmaku.example.com`，客户端自动使用 `wss://` 连接；校验强制 http(s) 且含主机名。
   - **mobile-sender**：静态部署到与后端同域名下（同源，自动 https），或通过 `?api=https://danmaku.example.com` 查询参数指定（推荐反代同源）。
   - **web 前端**：`VITE_API_URL` 部署时留空（同源）或指向 https 地址；vite dev 的 http 仅限本机开发。
3. **证书校验**：大屏 HttpClient/ClientWebSocket 走系统信任链，不要跳过证书校验；自签名证书需安装到系统信任存储。
4. **移动端防降级**：mobile-sender 优先同源部署，避免硬编码 `http://localhost:8000` 遗留导致明文请求。

### 反向代理安全响应头（生产必须）

前端 SPA 由反向代理托管时，除静态资源外需下发安全响应头（vite dev/preview 已内置相同集合，见 `web/vite.config.ts`）。Caddy 示例：

```caddyfile
danmaku.example.com {
    reverse_proxy 127.0.0.1:8000
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options SAMEORIGIN
        Referrer-Policy strict-origin-when-cross-origin
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        -Server
    }
}
```

nginx 示例：

```nginx
server {
    listen 443 ssl;
    # ... ssl_certificate / ssl_certificate_key ...
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /api/v1/activities/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";   # WebSocket 透传（大屏事件流）
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 说明：`connect-src 'self' ws: wss:` 允许同源 WebSocket（大屏/后台实时事件）；`style-src 'unsafe-inline'` 为 React 动态样式所需，不要移除。

## 活动前预检

1. 创建活动、生成二维码并确认起止时间。
2. 配置词库、投稿长度、频率和审核模式。
3. 在管理面板为活动申请**大屏授权密钥**，配对大屏（服务地址 + 活动码 + 密钥）。
4. 用备用网络完成一次投稿、审核、撤回和抽奖演练。
5. 确认数据库备份、日志告警和备用大屏设备可用。

## 故障处理

- 大屏断线：客户端继续显示已确认缓存，指数退避重连并按序号补偿。
- 管理端断线：恢复后以服务端审核队列快照为准，不继续操作旧本地状态。
- 云服务故障：停止对外宣称活动状态；恢复后优先检查数据、事件序列和导出权限。
- 大屏崩溃：重新启动客户端或备用机配对；不在现场机器上启用内网穿透作为常规修复。
- 大屏连接被拒（1008）：检查大屏密钥是否在管理面板申请且未吊销、活动码是否正确。
