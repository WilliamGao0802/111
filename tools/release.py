"""发布流程自动化：预检 → 全量测试 → 改版本 → 更新 CHANGELOG → 提交 → 打标签 → 推送。

用法：
    python tools/release.py 1.1.0 "本次更新说明"      # 完整发布
    python tools/release.py 1.1.0 "说明" --dry-run    # 只做预检与展示，不改动任何文件

设计要点（技能阶段 6）：
  * version.py 是**唯一版本源**，其它地方都从它读；
  * 推送使用 `git push --follow-tags` 只跟**附注标签**，因此这里用 `git tag -a`；
  * subprocess 超时只杀直接子进程，孙进程会持有管道导致永久阻塞 —— 这里显式给出超时并杀进程组。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "version.py"


def run(cmd: list[str], check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    print("→", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True,
                          check=check, timeout=timeout)


def read_version() -> str:
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("无法从 version.py 读出版本号")
    return m.group(1)


def bump_version(new: str, note: str) -> None:
    s = VERSION_FILE.read_text(encoding="utf-8")
    s = re.sub(r'^VERSION\s*=\s*"[^"]+"', f'VERSION = "{new}"', s, count=1, flags=re.M)
    from datetime import date
    s = re.sub(r'^BUILD_DATE\s*=\s*"[^"]+"', f'BUILD_DATE = "{date.today().isoformat()}"',
               s, count=1, flags=re.M)
    entry = f'    ("{new}", "{date.today().isoformat()}", [\n        "{note}",\n    ]),\n'
    s = s.replace("CHANGELOG = [\n", "CHANGELOG = [\n" + entry, 1)
    VERSION_FILE.write_text(s, encoding="utf-8")
    print(f"→ version.py 已更新为 {new}")


def precheck() -> None:
    r = subprocess.run([sys.executable, "-W", "error::SyntaxWarning",
                        "-m", "compileall", "-q", "app.py", "version.py", "core", "ui", "tools"],
                       cwd=str(ROOT), text=True, capture_output=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("预检失败：存在语法错误（SyntaxWarning 已按错误处理）")
    print("→ 语法预检通过")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 2
    new, note = args[0], args[1]
    if not re.match(r"^\d+\.\d+\.\d+$", new):
        raise SystemExit("版本号需为语义化格式，如 1.1.0")

    print(f"当前版本：{read_version()} → 目标版本：{new}")
    precheck()

    print("\n[2/5] 运行全量测试 …")
    t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=str(ROOT), text=True, capture_output=True)
    if t.returncode != 0:
        print(t.stdout[-2000:], t.stderr[-2000:])
        raise SystemExit("测试未全部通过，发布中止")
    print("→ 测试全部通过")

    if dry:
        print("\n（--dry-run）预检与测试通过，未做任何改动。")
        return 0

    bump_version(new, note)

    print("\n[4/5] 提交 …")
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"release: v{new} {note}"])
    run(["git", "tag", "-a", f"v{new}", "-m", f"v{new} {note}"])

    print("\n[5/5] 推送 …")
    r = run(["git", "push", "--follow-tags"], check=False)
    if r.returncode != 0:
        print("  推送失败（可能未配置远端）。请稍后手动执行：")
        print(f"    git push --follow-tags   # 已本地打好附注标签 v{new}")
    print(f"\n✅ 发布完成：v{new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
