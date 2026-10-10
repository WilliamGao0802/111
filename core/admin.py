"""管理员后台：数据看板、审核队列、用户/内容管理、访问日志、对账。"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import commerce, db, forum, news, notify, users


def dashboard() -> dict:
    d = {
        "users": int(db.scalar("SELECT COUNT(*) FROM users WHERE status<>'cancelled'", (), 0)),
        "active_users": int(db.scalar("SELECT COUNT(*) FROM users WHERE online=1", (), 0)),
        "banned": int(db.scalar("SELECT COUNT(*) FROM users WHERE status='banned'", (), 0)),
        "instructors": int(db.scalar("SELECT COUNT(*) FROM users WHERE instructor_status='approved'", (), 0)),
        "posts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='published'", (), 0)),
        "comments": int(db.scalar("SELECT COUNT(*) FROM comments", (), 0)),
        "news": int(db.scalar("SELECT COUNT(*) FROM news WHERE status='published'", (), 0)),
        "files": int(db.scalar("SELECT COUNT(*) FROM files WHERE deleted=0", (), 0)),
        "courses": int(db.scalar("SELECT COUNT(*) FROM courses", (), 0)),
        "lives": int(db.scalar("SELECT COUNT(*) FROM lives", (), 0)),
        "enrollments": int(db.scalar("SELECT COUNT(*) FROM enrollments", (), 0)),
        "knowledge": int(db.scalar("SELECT COUNT(*) FROM knowledge", (), 0)),
        "questions": int(db.scalar("SELECT COUNT(*) FROM questions", (), 0)),
        "quizzes": int(db.scalar("SELECT COUNT(*) FROM quiz_records", (), 0)),
        "pending_news": int(db.scalar("SELECT COUNT(*) FROM news WHERE status='pending'", (), 0)),
        "pending_instructors": int(db.scalar("SELECT COUNT(*) FROM users WHERE instructor_status='pending'", (), 0)),
        "pending_realnames": int(db.scalar("SELECT COUNT(*) FROM users WHERE realname_status='pending'", (), 0)),
        "pending_reports": int(db.scalar("SELECT COUNT(*) FROM reports WHERE status='pending'", (), 0)),
        "pending_invoices": int(db.scalar("SELECT COUNT(*) FROM invoices WHERE status='pending'", (), 0)),
    }
    d.update(commerce.platform_summary())
    return d


def trend_data(days: int = 14) -> list:
    """按天统计注册 / 发帖 / 下单，用于趋势图。"""
    out = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        like = f"{day}%"
        out.append({
            "date": day,
            "注册": int(db.scalar("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (like,), 0)),
            "发帖": int(db.scalar("SELECT COUNT(*) FROM posts WHERE created_at LIKE ?", (like,), 0)),
            "订单": int(db.scalar("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (like,), 0)),
            "学习": int(db.scalar("SELECT COUNT(*) FROM lesson_progress WHERE updated_at LIKE ?", (like,), 0)),
        })
    return out


def category_distribution() -> list:
    out = []
    for c in ["大模型基础", "提示词工程", "微调实战", "AI 应用开发", "数据与算力", "职业发展"]:
        n = int(db.scalar("SELECT COUNT(*) FROM courses WHERE category=?", (c,), 0))
        out.append({"category": c, "count": n})
    return out


def recent_logs(limit: int = 200, action: str = "", username: str = "") -> list:
    sql = "SELECT * FROM access_logs WHERE 1=1"
    params: list = []
    if action:
        sql += " AND action LIKE ?"; params.append(f"%{action}%")
    if username:
        sql += " AND username LIKE ?"; params.append(f"%{username}%")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def moderation_queue() -> dict:
    return {
        "reports": forum.list_reports("pending"),
        "news": news.pending_news(),
        "instructors": users.pending_instructors(),
        "realnames": users.pending_realnames(),
        "refunds": commerce.list_refunds("pending"),
        "withdrawals": commerce.list_withdrawals("pending"),
        "invoices": db.query("SELECT * FROM invoices WHERE status='pending' ORDER BY id DESC"),
    }


def review_invoice(iid: int, approve: bool = True) -> None:
    db.execute("UPDATE invoices SET status=? WHERE id=?", ("issued" if approve else "rejected", iid))


def hide_content(target_type: str, target_id: int) -> None:
    if target_type == "post":
        db.execute("UPDATE posts SET status='hidden' WHERE id=?", (target_id,))
    elif target_type == "comment":
        db.execute("DELETE FROM comments WHERE id=?", (target_id,))
    elif target_type == "file":
        db.execute("UPDATE files SET deleted=1, deleted_at=? WHERE id=?", (db.now_str(), target_id))
    elif target_type == "news":
        db.execute("UPDATE news SET status='rejected' WHERE id=?", (target_id,))


def broadcast(title: str, content: str) -> int:
    """全站公告：给所有活跃用户推送站内通知。"""
    n = 0
    for u in db.query("SELECT id FROM users WHERE status='active'"):
        notify.push(u["id"], "system", f"{title}：{content}", link="")
        n += 1
    return n


def export_table(table: str, limit: int = 5000) -> list:
    allow = {"users", "posts", "comments", "news", "files", "courses", "orders", "refunds",
             "transactions", "withdrawals", "live_chat", "access_logs", "quiz_records", "knowledge", "questions"}
    if table not in allow:
        raise ValueError("不允许导出该表")
    return db.query(f"SELECT * FROM {table} LIMIT ?", (limit,))
