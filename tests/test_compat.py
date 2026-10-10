"""跨版本兼容性静态检查（v1.1.1 起）。

背景：云端沙箱的 Python 可能低于 3.12。3.12 之前（PEP 701 之前）f-string 有两条
铁律，本地 3.13 编译通过 ≠ 云端能跑。v1.1.0/v1.1.1 连续在线上踩了这两类坑：

  A. 表达式部分不能含反斜杠
     f"<span class=\"x\">"            ← 3.12+ 合法，3.11 SyntaxError
  B. 表达式部分不能复用外层同类引号
     f'答对 {res['correct']} 题'      ← 3.12+ 合法，3.11 SyntaxError

检查原理（零误报）：
  在**合法的** pre-3.12 代码里，`f'` 之后出现的第一个裸 `'` 必然终止字符串，
  所以「f' 后接 { 再接裸 '」这样的序列在旧代码里不可能存在 —— 命中即违规。
  双引号同理。已知局限：跨物理行的 f-string 表达式不在检查范围内。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A. f-string 表达式花括号内出现反斜杠
BACKSLASH_IN_EXPR = re.compile(r'^\s*f["\'][^\n]*\{[^}\n]*\\[^\n]*\}', re.M)
# B. 同类引号嵌套：f'...' 内部 { } 里又出现裸 '
SAME_QUOTE_SINGLE = re.compile(r"f'[^'\n]*\{[^}]*'[^}]*\}")
SAME_QUOTE_DOUBLE = re.compile(r'f"[^"\n]*\{[^}]*"[^}]*\}')


def iter_source_files() -> list[Path]:
    """扫描所有业务源码；本文件排除——它包含违规示例本身。"""
    files: list[Path] = []
    for pattern in ("*.py", "core/*.py", "ui/*.py", "tools/*.py", "tests/*.py"):
        files.extend(ROOT.glob(pattern))
    return sorted(set(files) - {Path(__file__).resolve()})


class TestPythonCompat(unittest.TestCase):
    def test_fstring_compatible_with_python_3_11(self) -> None:
        offenders: list[str] = []
        for py in iter_source_files():
            text = py.read_text(encoding="utf-8")
            rel = py.relative_to(ROOT)
            if BACKSLASH_IN_EXPR.search(text):
                offenders.append(f"{rel}: f-string 表达式含反斜杠（规则A）")
            if SAME_QUOTE_SINGLE.search(text):
                offenders.append(f"{rel}: f'...' 表达式内复用了单引号（规则B）")
            if SAME_QUOTE_DOUBLE.search(text):
                offenders.append(f'{rel}: f"..." 表达式内复用了双引号（规则B）')
        self.assertEqual(
            offenders, [],
            "以下 f-string 在 Python 3.12 以下会 SyntaxError，请把表达式先算成变量：\n  "
            + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
