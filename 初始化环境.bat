@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 初始化 BGL 运行环境

echo [1/3] 创建虚拟环境 .venv ...
python -m venv .venv || goto :err

echo [2/3] 升级 pip ...
.venv\Scripts\python.exe -m pip install --upgrade pip || goto :err

echo [3/3] 安装依赖（首次需要几分钟）...
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err

echo.
echo 环境初始化完成。以后双击「一键启动.bat」即可。
pause
exit /b 0

:err
echo.
echo 初始化失败，请确认已安装 Python 3.10+ 并加入 PATH。
pause
exit /b 1
