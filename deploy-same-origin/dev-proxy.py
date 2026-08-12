#!/usr/bin/env python3
"""本地同源验证代理：模拟 nginx 行为
- 静态文件来自 ./public
- /api 与 /health 转发到后端（默认 127.0.0.1:8000）
用法: python dev-proxy.py [端口]
"""
import http.client
import http.server
import os
import sys

BACKEND = ("127.0.0.1", 8000)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

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

    def do_GET(self):
        if self.path.startswith("/api/") or self.path.startswith("/health"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        self._proxy()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    print(f"[dev-proxy] 静态: {ROOT}  反代: http://{BACKEND[0]}:{BACKEND[1]}/api  ->  http://127.0.0.1:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), ProxyHandler).serve_forever()
