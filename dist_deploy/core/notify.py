"""站内通知中心 + 消息推送（含每日精选、开播提醒、订单通知）。"""

from __future__ import annotations

from . import db

NTYPE_LABEL = {
    "like": "点赞", "comment": "评论", "follow": "关注", "mention": "@提及",
    "live": "直播", "system": "系统", "order": "交易", "points": "积分", "news": "新闻",
}


def push(user_id: int, ntype: str, content: str, link: str = "") -> int:
    if not user_id:
        return 0
    return db.execute(
        "INSERT INTO notifications(user_id,ntype,content,link,is_read,created_at) VALUES(?,?,?,?,0,?)",
        (user_id, ntype, content, link, db.now_str()),
    )


def list_notifications(user_id: int, limit: int = 50, unread_only: bool = False) -> list:
    sql = "SELECT * FROM notifications WHERE user_id=?"
    params: list = [user_id]
    if unread_only:
        sql += " AND is_read=0"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def unread_count(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
                         (user_id,), 0))


def mark_read(user_id: int, nid: int | None = None) -> None:
    if nid:
        db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, user_id))
    else:
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))


def mark_all_read(user_id: int) -> None:
    db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))


# ---------------------------- 私信 ----------------------------
def send_message(from_id: int, to_id: int, content: str) -> int:
    mid = db.execute(
        "INSERT INTO messages(from_id,to_id,content,is_read,created_at) VALUES(?,?,?,0,?)",
        (from_id, to_id, content, db.now_str()),
    )
    push(to_id, "system", "你收到一条新的私信", link="inbox")
    return mid


def conversation(a: int, b: int, limit: int = 100) -> list:
    return db.query(
        """SELECT * FROM messages
           WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
           ORDER BY id ASC LIMIT ?""",
        (a, b, b, a, limit),
    )


def contacts(user_id: int) -> list:
    rows = db.query(
        """SELECT DISTINCT CASE WHEN from_id=? THEN to_id ELSE from_id END AS peer
           FROM messages WHERE from_id=? OR to_id=?""",
        (user_id, user_id, user_id),
    )
    out = []
    for r in rows:
        u = db.query_one("SELECT id,username,nickname,avatar,online FROM users WHERE id=?", (r["peer"],))
        if u:
            last = db.query_one(
                """SELECT content,created_at FROM messages
                   WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
                   ORDER BY id DESC LIMIT 1""",
                (user_id, r["peer"], r["peer"], user_id),
            )
            u = dict(u)
            u["last"] = (last or {}).get("content", "")
            u["last_at"] = (last or {}).get("created_at", "")
            out.append(u)
    out.sort(key=lambda x: x.get("last_at") or "", reverse=True)
    return out


def unread_messages(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM messages WHERE to_id=? AND is_read=0", (user_id,), 0))


def mark_conversation_read(user_id: int, peer_id: int) -> None:
    db.execute("UPDATE messages SET is_read=1 WHERE to_id=? AND from_id=?", (user_id, peer_id))
