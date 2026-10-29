#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_TAG="${1:-}"

if [ -z "$TARGET_TAG" ]; then
    echo "用法: ./scripts/rollback.sh <git-tag>    例如 ./scripts/rollback.sh v0.1.0"
    echo "当前可回滚的版本:"
    git tag --sort=-creatordate | head -10
    exit 1
fi

echo "回滚到 $TARGET_TAG"
git fetch --tags
git checkout "$TARGET_TAG"
docker compose build
docker compose up -d
./scripts/deploy.sh

echo "回滚完成：$TARGET_TAG"
