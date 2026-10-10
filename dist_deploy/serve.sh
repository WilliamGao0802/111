#!/usr/bin/env sh
# 容器 / Linux 部署入口（平台 startCmd 用 `bash serve.sh` 调用）。
# 只做一件事：挑一个可用的 Python 解释器，转交给 serve.py。
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "未找到 python / python3 解释器" >&2
  exit 127
fi

echo "使用解释器: $PY"
exec "$PY" serve.py
