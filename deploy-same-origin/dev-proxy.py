#!/usr/bin/env python3
"""本地同源验证代理：模拟 all-in-one nginx 行为
- 静态文件来自 web/dist（React 构建产物）
- /m/ 前缀映射到 mobile-sender（轻量发送端）
- /api 与 /health 转发到后端（默认 127.0.0.1:8000）
用法: python dev-proxy.py [端口]
"""
import http.client
import http.server
import os
import sys

BACKEND = ("127.0.0.1", 8000)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "dist")
MOBILE_SENDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mobile-sender")

# 请求头白名单（去掉 host/connection/编码相关的头，避免代理歧义）
SKIP_HEADERS = {"host", "connection", "accept-encoding", "content-length"}


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIP_HEADERS}
        conn = http.client.HTTPConnection(*BACKEND, timeout=15)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        except Exception as exc:  # 后端不可达
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.log_message("proxy error: %s", exc)
            return
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in ("transfer-encoding", "connection", "content-length"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        conn.close()

    def _serve_mobile_sender(self, rel: str):
        """服务 /m/ 下的 mobile-sender 静态文件。"""
        target = os.path.normpath(os.path.join(MOBILE_SENDER, rel))
        if not target.startswith(os.path.normpath(MOBILE_SENDER)):
            self.send_error(403)
            return
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            # SPA 兜底
            target = os.path.join(MOBILE_SENDER, "index.html")
        with open(target, "rb") as f:
            payload = f.read()
        ctype = self.guess_type(target)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/api/") or self.path.startswith("/health"):
            self._proxy()
        elif self.path.startswith("/m/"):
            self._serve_mobile_sender(self.path[len("/m/"):])
        else:
            super().do_GET()

    def do_POST(self):
        self._proxy()


if __name__ == "__main__":
    # 用法: python dev-proxy.py [端口] [监听地址]
    # 默认监听 0.0.0.0：局域网内其他机器（含大屏）可通过 http://<本机IP>:端口 访问
    host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    print(f"[dev-proxy] 静态: {ROOT}  /m: {MOBILE_SENDER}  反代: http://{BACKEND[0]}:{BACKEND[1]}/api")
    http.server.ThreadingHTTPServer((host, port), ProxyHandler).serve_forever()
