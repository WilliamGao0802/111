"""把项目同步成一份**干净的部署包**（默认 `dist_deploy/`）。

为什么需要它：
  * 项目根目录里有 `.venv/`（约 357 MB）和本地运行数据，整目录上传既慢又含隐私；
  * 平台只需要「源码 + 依赖清单 + 入口脚本」这一小撮文件。

同步策略（技能 `references/03` 的纪律）：
  * **逐文件覆盖**，不用 `rmtree + copytree` —— 后者在有批量删除保护的机器上会被拦；
  * 默认**不带数据库**：云上首启由 `app.py::ensure_ready()` 自举建库+灌演示数据，
    这样部署包不含本地会话痕迹；要带库加 `--with-db`（会自动合并 WAL）；
  * **清理本地测试残留**：`uploads/`（seed 上传的示例文件）与 `data/*.db-wal` 一律剔除，
    只做单文件 `unlink` + 空目录 `rmdir`，**绝不 rmtree**；
  * `--prune` 额外清理代码类残留（core/ui/.streamlit 与顶层 .py/.sh/.toml/.md）。

用法：
    python tools/deploy_sync.py                  # 同步到 dist_deploy/
    python tools/deploy_sync.py --out D:/tmp/x   # 指定输出目录
    python tools/deploy_sync.py --prune          # 顺便清理代码类残留
    python tools/deploy_sync.py --with-db        # 带上本地 bgl.db（含本地数据）
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 顶层要带上的文件
TOP_FILES = [
    "app.py", "serve.py", "serve.sh", "version.py",
    "requirements.txt", "README.md", "使用说明.md", "部署上线说明.md",
]
# 要带上的目录（递归，排除 __pycache__）
DIRS = ["core", "ui"]
# 目录内额外的相对文件
EXTRA = [".streamlit/config.toml"]

SKIP_NAMES = {"__pycache__", ".venv", ".git", "tests", "tools", "assets", "uploads"}
PRUNE_SUFFIXES = (".py", ".sh", ".toml", ".md", ".txt", ".bat")
# 运行时目录：这里面的东西一律不带进部署包（本地测试残留）
RUNTIME_DIRS = ["uploads", "data"]
RUNTIME_KEEP = {"bgl.db"}  # 仅在 --with-db 时保留


def checkpoint_wal(src_db: Path) -> None:
    """把 -wal 里的内容合并回主库，避免部署包带着半截事务。"""
    if not src_db.exists():
        return
    try:
        conn = sqlite3.connect(str(src_db))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        print(f"→ 已合并 WAL：{src_db.name}")
    except sqlite3.Error as e:  # noqa: BLE001
        print(f"! WAL 合并失败（不影响部署）：{e}")


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for item in sorted(src.rglob("*")):
        if any(part in SKIP_NAMES for part in item.parts):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            n += 1
    return n


def clean_runtime(out: Path, keep_db: bool) -> int:
    """剔除运行时残留（本地测试跑出来的 uploads/、WAL 文件等）。

    只做单文件 unlink 与空目录 rmdir —— 不用 rmtree，避免触发批量删除保护。
    """
    removed = 0
    for name in RUNTIME_DIRS:
        d = out / name
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file():
                if name == "data" and keep_db and p.name in RUNTIME_KEEP:
                    continue
                p.unlink()
                removed += 1
                print(f"- 清理运行时残留 {p.relative_to(out)}")
        # 自底向上删空目录（rmdir 只能删空目录，天然安全）
        for p in sorted(d.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    return removed


def sync(out: Path, prune: bool, keep_db: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    copied = 0

    for name in TOP_FILES:
        src = ROOT / name
        if not src.exists():
            print(f"! 跳过（不存在）：{name}")
            continue
        shutil.copy2(src, out / name)
        expected.add(Path(name))
        copied += 1
        print(f"✓ {name}")

    for d in DIRS:
        src = ROOT / d
        if not src.exists():
            print(f"! 跳过（不存在）：{d}/")
            continue
        copied += copy_tree(src, out / d)
        expected |= {p.relative_to(out) for p in (out / d).rglob("*") if p.is_file()}
        print(f"✓ {d}/")

    for rel in EXTRA:
        src = ROOT / rel
        if not src.exists():
            print(f"! 跳过（不存在）：{rel}")
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / rel)
        expected.add(Path(rel))
        copied += 1
        print(f"✓ {rel}")

    # 运行时目录：默认清空（云上自举），--with-db 时带上本地库
    (out / "data").mkdir(parents=True, exist_ok=True)
    if keep_db:
        checkpoint_wal(ROOT / "data" / "bgl.db")
        db_src = ROOT / "data" / "bgl.db"
        if db_src.exists():
            shutil.copy2(db_src, out / "data" / "bgl.db")
            print(f"✓ data/bgl.db（{db_src.stat().st_size // 1024} KB，含本地数据）")
        else:
            print("! --with-db 但本地没有 data/bgl.db")
    else:
        print("→ data/ 不带数据库：首次启动由 app.py::ensure_ready() 自举建库+灌演示数据")

    if prune:
        removed = 0
        for p in sorted(out.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(out)
            if rel.parts and rel.parts[0] in RUNTIME_DIRS:
                continue
            if rel in expected:
                continue
            if p.suffix in PRUNE_SUFFIXES or "__pycache__" in rel.parts:
                p.unlink()
                removed += 1
                print(f"- 清理残留 {rel}")
        print(f"→ 清理 {removed} 个残留文件")

    clean_runtime(out, keep_db)

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    files = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"\n✅ 部署包就绪：{out}\n   文件 {files} 个（本次复制 {copied}），合计 {total / 1024:.0f} KB")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist_deploy"))
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--with-db", action="store_true",
                    help="带上本地 data/bgl.db（默认不带，云端首启自举）")
    a = ap.parse_args()
    return sync(Path(a.out).resolve(), a.prune, a.with_db)


if __name__ == "__main__":
    raise SystemExit(main())
