#!/usr/bin/env bash
# BGL 的 AI 学习 —— macOS / Linux 一键启动
set -euo pipefail
cd "$(dirname "$0")"

PY="./.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python)"
fi

echo "使用解释器: $PY"
exec "$PY" launch.py
