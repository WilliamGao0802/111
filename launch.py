#!/usr/bin/env python
"""BGL 的 AI 学习 —— 一键启动器。

要点（来自技能踩坑清单）：
  启动后**轮询端口真正就绪**再打开浏览器，而不是写死 `sleep N`。
  冷启动慢时写死等待会打开一个还不存在的端口，表现为浏览器一直转圈。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("BGL_PORT", "8501"))
HOST = os.environ.get("BGL_HOST", "127.0.0.1")
APP = ROOT / "app.py"
REQ = ROOT / "requirements.txt"
READY_TIMEOUT = int(os.environ.get("BGL_READY_TIMEOUT", "180"))


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def has_deps(python: str) -> bool:
    try:
        subprocess.run([python, "-c", "import streamlit, pandas, altair"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_deps(python: str) -> None:
    if has_deps(python):
        return
    print("→ 检测到运行依赖未安装，正在安装（首次启动需要几分钟）…", flush=True)
    subprocess.check_call([python, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([python, "-m", "pip", "install", "-r", str(REQ)])
    print("→ 依赖安装完成", flush=True)


def wait_ready(host: str, port: int, proc: subprocess.Popen, timeout: int = READY_TIMEOUT) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        if port_open(host, port):
            return True
        time.sleep(0.35)
    return False


def free_port_hint(port: int) -> None:
    print(f"\n⚠️  端口 {port} 已被占用。\n"
          f"   换一个端口启动：设置环境变量 BGL_PORT，例如 BGL_PORT=8600\n"
          f"   或结束占用进程后重试。\n", flush=True)


def main() -> int:
    if not APP.exists():
        print(f"找不到 app.py：{APP}")
        return 1

    if port_open(HOST, PORT):
        free_port_hint(PORT)
        return 1

    ensure_deps(sys.executable)

    url = f"http://{HOST}:{PORT}"
    print("=" * 62)
    print("  🎓 BGL 的 AI 学习 —— 正在启动")
    print(f"  地址：{url}")
    print("  演示账号：admin / 123456（管理员）")
    print("            fangyuan / 123456（学员）")
    print("            liyuan / 123456（讲师）")
    print("  停止服务：在本窗口按 Ctrl+C")
    print("=" * 62, flush=True)

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP),
         "--server.port", str(PORT),
         "--server.address", HOST,
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false",
         "--server.maxUploadSize", "50"],
        cwd=str(ROOT),
    )

    if wait_ready(HOST, PORT, proc):
        print(f"\n✅ 服务已就绪：{url}\n", flush=True)
        if os.environ.get("BGL_NO_BROWSER") != "1":
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass
    else:
        print("\n⚠️  启动超时，请查看上方日志排查（端口被占用 / 依赖缺失 / 数据目录权限）\n", flush=True)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
