"""数据备份与恢复：全库导出 / 导入、一键备份文件、备份列表与还原。"""

from __future__ import annotations

import json
from pathlib import Path

from . import db

BACKUP_DIR = Path(__file__).resolve().parent.parent / "data" / "backups"

TABLES = [
    "users", "follows", "verifications", "points_log",
    "news", "news_likes", "news_favs",
    "posts", "comments", "post_likes", "drafts", "reports", "notifications", "messages", "files",
    "courses", "chapters", "lessons", "enrollments", "lesson_progress",
    "course_reviews", "course_qa",
    "lives", "live_reservations", "live_chat", "live_interactions", "live_votes", "live_handraise",
    "products", "cart", "coupons", "user_coupons", "orders", "order_items",
    "refunds", "transactions", "withdrawals", "invoices",
    "knowledge", "questions", "quiz_records", "wrong_book",
    "access_logs", "settings",
]


def export_all() -> dict:
    data = {"__meta__": {"version": 1, "exported_at": db.now_str()}}
    for t in TABLES:
        try:
            data[t] = db.query(f"SELECT * FROM {t}")
        except Exception:
            data[t] = []
    return data


def import_all(data: dict, replace: bool = True) -> dict:
    """导入备份。replace=True 时先清空对应表。"""
    stat = {}
    for t in TABLES:
        rows = data.get(t) or []
        if replace:
            db.execute(f"DELETE FROM {t}")
        n = 0
        for row in rows:
            cols = list(row.keys())
            sql = (f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) "
                   f"VALUES ({','.join('?' * len(cols))})")
            try:
                db.execute(sql, tuple(row[c] for c in cols))
                n += 1
            except Exception:
                continue
        stat[t] = n
    return stat


def create_backup(tag: str = "") -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"backup_{db.now_str().replace(':', '').replace(' ', '_').replace('-', '')}"
    if tag:
        name += f"_{tag}"
    path = BACKUP_DIR / f"{name}.json"
    path.write_text(json.dumps(export_all(), ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)


def list_backups() -> list:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(BACKUP_DIR.glob("backup_*.json"), reverse=True):
        out.append({"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1),
                    "path": str(p)})
    return out


def restore_backup(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return import_all(data, replace=True)
