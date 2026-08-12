import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 生产安全响应头：由反向代理（Caddy/nginx）下发，见 docs/deployment-runbook.md。
// Vite 仅对 preview（构建产物预览）生效；dev server 不发 CSP，因为 @vitejs/plugin-react
// 的 preamble/HMR 需要内联脚本与 eval，收紧会直接拦掉页面渲染。
const productionHeaders = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "SAMEORIGIN",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  // React 无内联脚本，script-src 收紧为 self；内联样式（React style= 属性）需要 unsafe-inline
  "Content-Security-Policy": [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self' ws: wss:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; "),
};

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true },
    },
  },
  preview: {
    headers: productionHeaders,
  },
});
