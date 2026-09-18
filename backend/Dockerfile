# 后端镜像（里程碑 11）
#
# 分层要点：先 COPY requirements 并安装，再 COPY 源码——
# 平时改代码不会触发重装依赖，构建快、缓存命中率高。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # 统一 UTF-8：Alembic 读配置用的是 locale 编码，非 UTF-8 locale（如中文
    # Windows 默认 GBK）会直接 UnicodeDecodeError，见 migrations/README
    PYTHONUTF8=1

WORKDIR /app

# ---- 依赖层 ----
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium 及其系统依赖（SPA 页面渲染用）。
# 装进 /opt 并设 PLAYWRIGHT_BROWSERS_PATH：默认会装进 root 的 home 目录，
# 之后切到 appuser 就找不到内核了
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update
RUN playwright install --with-deps chromium

# ---- 源码层 ----
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# ---- 入口脚本 ----
# sed 兜底：若仓库里的脚本带 CRLF（Windows 检出），进容器前统一转成 LF，
# 否则 Linux 下 shebang 行会带 \r 导致容器起不来
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# 非 root 运行；storage 是抓取落盘目录，需要写权限
RUN useradd --create-home appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
