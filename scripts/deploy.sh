#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

step() { printf '\n\033[1;36m[%s]\033[0m %s\n' "$1" "$2"; }
fail() { printf '\033[1;31m[失败]\033[0m %s\n' "$1" >&2; exit 1; }

if ! command -v docker >/dev/null 2>&1; then
    fail "未安装 docker"
fi

if [ ! -f .env ]; then
    step "0/6" "未找到 .env，从模板复制"
    cp .env.example .env
    echo "请修改 .env 里的 JWT_SECRET 后重新执行本脚本"
    exit 1
fi

step "1/6" "构建镜像"
docker compose build

step "2/6" "镜像自检（不依赖数据库）"
docker compose run --rm --no-deps -T app python scripts/smoke_test.py \
    || fail "冒烟测试未通过，先修代码再部署"

step "3/6" "启动数据库"
docker compose up -d db

printf '等待数据库就绪'
for _ in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U docqa -d docqa >/dev/null 2>&1; then
        printf '\n数据库已就绪\n'
        break
    fi
    printf '.'
    sleep 2
done

step "4/6" "启动应用与 worker"
docker compose up -d app worker

step "5/6" "启动 nginx"
docker compose up -d nginx

step "6/6" "健康检查"
for _ in $(seq 1 30); do
    if curl -fsS http://localhost/healthz >/dev/null 2>&1; then
        echo "部署完成：http://localhost/docs"
        exit 0
    fi
    sleep 2
done

docker compose ps
docker compose logs --tail 50 app
fail "健康检查未通过，请查看上面的日志，或对照 docs/故障排查手册.md 的 F01 / F03"
