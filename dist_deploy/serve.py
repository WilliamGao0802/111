#!/usr/bin/env python
"""云端 / 容器部署入口（本地一键启动请用 launch.py）。

与 launch.py 的区别：
  * 本地版：固定端口、绑 127.0.0.1、就绪后自动开浏览器；
  * 部署版：读取平台注入的 **环境变量 PORT**、绑 **0.0.0.0**、
    关掉 CORS 与 XSRF 校验（反向代理必须，否则 WebSocket 握手被拒）、不开浏览器。

用法：
    PORT=8080 python serve.py          # 平台会这样调（见 serve.sh）
    PORT=8080 BGL_DB_PATH=/data/bgl.db python serve.py   # 数据落到持久卷
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PORT = os.environ.get("PORT") or os.environ.get("BGL_PORT") or "8501"
ADDRESS = os.environ.get("BGL_HOST", "0.0.0.0")
MAX_UPLOAD_MB = os.environ.get("BGL_MAX_UPLOAD_MB", "50")


def main() -> int:
    # 延迟导入：让「没装 streamlit」时给出可读报错，而不是 import 期就炸
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print("缺少依赖：请先执行  pip install -r requirements.txt", file=sys.stderr)
        return 1

    print(f"→ 启动 BGL 的 AI 学习：http://{ADDRESS}:{PORT}  (cwd={ROOT})", flush=True)
    # Python 版本写进启动日志：排查「本地能跑云端报错」时第一眼看这里
    print(f"→ 解释器：Python {sys.version.split()[0]}  ({sys.executable})", flush=True)

    sys.argv = [
        "streamlit", "run", str(ROOT / "app.py"),
        "--server.port", str(PORT),
        "--server.address", str(ADDRESS),
        "--server.headless", "true",
        # 反向代理场景：平台域名 → 容器端口，必须关闭这两项
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--server.maxUploadSize", str(MAX_UPLOAD_MB),
        "--browser.gatherUsageStats", "false",
    ]
    return int(stcli.main())


if __name__ == "__main__":
    raise SystemExit(main())
