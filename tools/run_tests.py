"""一键跑全部测试：core 业务层 + UI 主链路（AppTest）。

用法：python tools/run_tests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print("=" * 60)
    print("  BGL 的 AI 学习 · 测试套件")
    print("=" * 60)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                       cwd=str(ROOT))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
