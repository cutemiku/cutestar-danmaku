# ── 阶段 1：构建 React 前端（web/） ──
FROM node:20-alpine AS web-builder
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── 阶段 2：运行时（Python 后端 + nginx 静态/反代，单容器 all-in-one） ──
FROM python:3.12-slim

# nginx + supervisor
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

# Python 后端
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/alembic.ini .
COPY server/alembic ./alembic
COPY server/app ./app

# 前端静态资源：
#   /            → React 构建产物（参与者 + 运营控制台）
#   /m/          → mobile-sender 轻量发送端
COPY --from=web-builder /build/dist /usr/share/nginx/html
COPY mobile-sender /usr/share/nginx/html/m

# nginx 配置与进程托管
COPY deploy-same-origin/nginx.conf /etc/nginx/nginx.conf
COPY deploy-same-origin/supervisord.conf /etc/supervisor/conf.d/cutestar.conf

# 数据目录（SQLite 落盘）
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 80
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
