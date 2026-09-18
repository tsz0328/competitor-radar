#!/bin/sh
# 容器入口：迁移到最新 -> 启动应用
#
# 迁移总是先跑（已是最新时是 no-op），保证应用起来时表结构一定就绪；
# 配合 compose 里 MySQL 的 healthcheck（depends_on: service_healthy），
# 应用侧不需要再写"等数据库"的循环。
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> Applying database migrations (alembic upgrade head)"
    attempt=1
    max_attempts="${MIGRATION_MAX_ATTEMPTS:-20}"
    until alembic upgrade head; do
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "!! Migration failed after $attempt attempts" >&2
            exit 1
        fi
        echo "    database not ready (attempt $attempt/$max_attempts), retry in 3s"
        attempt=$((attempt + 1))
        sleep 3
    done
else
    echo "==> Skipping migrations (RUN_MIGRATIONS=false)"
fi

echo "==> Starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
