@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BGL 的 AI 学习 - 启动中

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo 使用解释器: %PY%
"%PY%" launch.py

echo.
echo 服务已停止。按任意键关闭窗口。
pause >nul
