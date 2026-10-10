"""互动功能区 · 讨论区：发帖、多级评论、@提及、话题标签、点赞、草稿、举报、置顶加精。"""

from __future__ import annotations

import re

from . import auth, db, notify, users

TOPICS = ["综合讨论", "大模型", "提示词工程", "微调实战", "AI 应用开发", "求职交流", "资源分享"]

MENTION_RE = re.compile(r"@([A-Za-z0-9_\u4e00-\u9fa5]{2,20})")
TAG_RE = re.compile(r"#([^#\s]{1,20})#")


def parse_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(MENTION_RE.findall(text or "")))


def parse_tags(text: str, extra: str = "") -> str:
    tags = TAG_RE.findall(text or "")
    if extra:
        tags += [t.strip() for t in str(extra).replace("，", ",").split(",") if t.strip()]
    return ",".join(dict.fromkeys(tags))


def create_post(uid: int, title: str, content: str, topic: str = "综合讨论", tags: str = "") -> int:
    if not uid:
        raise auth.AuthError("请先登录后再发言")
    if not (content or "").strip():
        raise auth.AuthError("发言内容不能为空")
    if len(content) > 20000:
        raise auth.AuthError("发言内容过长（上限 20000 字）")
    if topic not in TOPICS:
        topic = "综合讨论"
    ts = db.now_str()
    pid = db.execute(
        """INSERT INTO posts(user_id,title,content,topic,tags,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (uid, (title or "").strip(), content.strip(), topic, parse_tags(content, tags), ts, ts),
    )
    author = auth.get_user(uid)
    for name in parse_mentions(content):
        target = auth.get_user_by_name(name)
        if target and target["id"] != uid:
            notify.push(target["id"], "mention",
                        f"{users.display_name(author)} 在帖子中提到了你：「{title or content[:20]}」",
                        link=f"post:{pid}")
    auth.add_points(uid, auth.POINT_RULES["post"], "发布帖子")
    auth.log(uid, (author or {}).get("username", ""), "post", f"发帖 #{pid}")
    return pid


def update_post(pid: int, uid: int, title=None, content=None, topic=None, tags=None) -> None:
    post = get_post(pid)
    if not post:
        raise auth.AuthError("帖子不存在")
    if post["user_id"] != uid:
        raise auth.AuthError("只能编辑自己的发言")
    sets, params = ["edited=1", "updated_at=?"], [db.now_str()]
    if title is not None:
        sets.append("title=?"); params.append(str(title).strip())
    if content is not None:
        if not str(content).strip():
            raise auth.AuthError("发言内容不能为空")
        sets.append("content=?"); params.append(str(content).strip())
        sets.append("tags=?"); params.append(parse_tags(content, tags or ""))
    if topic:
        sets.append("topic=?"); params.append(topic if topic in TOPICS else post["topic"])
    params.append(pid)
    db.execute(f"UPDATE posts SET {', '.join(sets)} WHERE id=?", tuple(params))


def delete_post(pid: int, uid: int, is_admin: bool = False) -> None:
    post = get_post(pid)
    if not post:
        return
    if post["user_id"] != uid and not is_admin:
        raise auth.AuthError("只能删除自己的发言")
    db.execute("UPDATE posts SET status='hidden' WHERE id=?", (pid,))


def get_post(pid: int):
    return db.query_one(
        """SELECT p.*, u.username, u.nickname, u.avatar, u.level, u.instructor_status
           FROM posts p LEFT JOIN users u ON u.id=p.user_id WHERE p.id=?""", (pid,))


def list_posts(sort: str = "new", topic: str = "", tag: str = "", keyword: str = "",
               following_only: bool = False, uid: int = 0, limit: int = 50) -> list:
    sql = ("SELECT p.*, u.username, u.nickname, u.avatar, u.level, "
           "(SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) AS comment_count "
           "FROM posts p LEFT JOIN users u ON u.id=p.user_id WHERE p.status='published'")
    params: list = []
    if topic:
        sql += " AND p.topic=?"; params.append(topic)
    if tag:
        sql += " AND p.tags LIKE ?"; params.append(f"%{tag}%")
    if keyword:
        sql += " AND (p.title LIKE ? OR p.content LIKE ?)"; params += [f"%{keyword}%"] * 2
    if following_only and uid:
        ids = users.following_ids(uid)
        if not ids:
            return []
        sql += f" AND p.user_id IN ({','.join('?' * len(ids))})"; params += ids
    order = {"new": "p.is_pinned DESC, p.id DESC",
             "hot": "p.is_pinned DESC, (p.likes + (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id)*2) DESC",
             "likes": "p.is_pinned DESC, p.likes DESC, p.id DESC"}.get(sort, "p.is_pinned DESC, p.id DESC")
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def my_posts(uid: int, limit: int = 50) -> list:
    return db.query("SELECT * FROM posts WHERE user_id=? AND status='published' ORDER BY id DESC LIMIT ?",
                    (uid, limit))


def toggle_like(uid: int, pid: int) -> bool:
    if not uid:
        raise auth.AuthError("请先登录")
    post = get_post(pid)
    if not post:
        raise auth.AuthError("帖子不存在")
    exists = db.query_one("SELECT 1 FROM post_likes WHERE user_id=? AND post_id=?", (uid, pid))
    if exists:
        db.execute("DELETE FROM post_likes WHERE user_id=? AND post_id=?", (uid, pid))
        db.execute("UPDATE posts SET likes=MAX(likes-1,0) WHERE id=?", (pid,))
        return False
    db.execute("INSERT INTO post_likes(user_id,post_id,created_at) VALUES(?,?,?)", (uid, pid, db.now_str()))
    db.execute("UPDATE posts SET likes=likes+1 WHERE id=?", (pid,))
    auth.add_points(uid, auth.POINT_RULES["like"], "点赞帖子")
    if post["user_id"]:
        auth.add_points(post["user_id"], auth.POINT_RULES["be_liked"], "帖子被点赞")
        notify.push(post["user_id"], "like",
                    f"{users.display_name(auth.get_user(uid))} 点赞了你的发言", link=f"post:{pid}")
    return True


def liked_ids(uid: int) -> set:
    if not uid:
        return set()
    return {r["post_id"] for r in db.query("SELECT post_id FROM post_likes WHERE user_id=?", (uid,))}


def add_comment(pid: int, uid: int, content: str, parent_id: int = 0) -> int:
    if not uid:
        raise auth.AuthError("请先登录")
    if not (content or "").strip():
        raise auth.AuthError("评论内容不能为空")
    post = get_post(pid)
    if not post:
        raise auth.AuthError("帖子不存在")
    cid = db.execute(
        "INSERT INTO comments(post_id,user_id,parent_id,content,created_at) VALUES(?,?,?,?,?)",
        (pid, uid, parent_id or 0, content.strip(), db.now_str()),
    )
    author = auth.get_user(uid)
    if post["user_id"] and post["user_id"] != uid:
        notify.push(post["user_id"], "comment",
                    f"{users.display_name(author)} 评论了你的发言：{content[:30]}", link=f"post:{pid}")
    if parent_id:
        parent = db.query_one("SELECT user_id FROM comments WHERE id=?", (parent_id,))
        if parent and parent["user_id"] not in (uid, post["user_id"]):
            notify.push(parent["user_id"], "comment",
                        f"{users.display_name(author)} 回复了你的评论", link=f"post:{pid}")
    for name in parse_mentions(content):
        target = auth.get_user_by_name(name)
        if target and target["id"] != uid:
            notify.push(target["id"], "mention",
                        f"{users.display_name(author)} 在评论中提到了你", link=f"post:{pid}")
    auth.add_points(uid, auth.POINT_RULES["comment"], "发表评论")
    return cid


def post_comments(pid: int) -> list:
    return db.query(
        """SELECT c.*, u.username, u.nickname, u.avatar, u.level, u.instructor_status
           FROM comments c LEFT JOIN users u ON u.id=c.user_id
           WHERE c.post_id=? ORDER BY c.id ASC""", (pid,))


def comment_tree(pid: int) -> list:
    """把扁平评论整理成多级讨论串。"""
    rows = post_comments(pid)
    by_id = {r["id"]: dict(r, children=[]) for r in rows}
    roots = []
    for r in rows:
        node = by_id[r["id"]]
        pid_ = node.get("parent_id") or 0
        if pid_ and pid_ in by_id:
            by_id[pid_]["children"].append(node)
        else:
            roots.append(node)
    return roots


def comment_count(pid: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM comments WHERE post_id=?", (pid,), 0))


def all_tags() -> list:
    tags: set[str] = set()
    for r in db.query("SELECT tags FROM posts WHERE tags<>''"):
        for t in str(r["tags"]).split(","):
            if t.strip():
                tags.add(t.strip())
    return sorted(tags)


# ---------------------------- 举报 / 审核 ----------------------------
def report(uid: int, target_type: str, target_id: int, reason: str) -> int:
    if not uid:
        raise auth.AuthError("请先登录")
    if not (reason or "").strip():
        raise auth.AuthError("请填写举报原因")
    rid = db.execute(
        "INSERT INTO reports(target_type,target_id,reporter_id,reason,created_at) VALUES(?,?,?,?,?)",
        (target_type, target_id, uid, reason.strip(), db.now_str()),
    )
    auth.log(uid, "", "report", f"{target_type}#{target_id}: {reason[:30]}")
    return rid


def list_reports(status: str = "pending") -> list:
    sql = """SELECT r.*, u.username AS reporter FROM reports r
             LEFT JOIN users u ON u.id=r.reporter_id"""
    params: list = []
    if status:
        sql += " WHERE r.status=?"; params.append(status)
    sql += " ORDER BY r.id DESC LIMIT 200"
    return db.query(sql, tuple(params))


def handle_report(rid: int, action: str = "handled") -> None:
    db.execute("UPDATE reports SET status=? WHERE id=?", (action, rid))
    auth.log(0, "", "handle_report", f"#{rid} -> {action}")


def set_pin(pid: int, value: bool) -> None:
    db.execute("UPDATE posts SET is_pinned=? WHERE id=?", (1 if value else 0, pid))


def set_essence(pid: int, value: bool) -> None:
    db.execute("UPDATE posts SET is_essence=? WHERE id=?", (1 if value else 0, pid))
    if value:
        post = get_post(pid)
        if post and post["user_id"]:
            notify.push(post["user_id"], "system", "你的发言被标记为精华，感谢分享！", link=f"post:{pid}")


# ---------------------------- 草稿箱 ----------------------------
def save_draft(uid: int, title: str, content: str, topic: str = "综合讨论") -> int:
    exist = db.query_one("SELECT id FROM drafts WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
    if exist:
        db.execute("UPDATE drafts SET title=?,content=?,topic=?,updated_at=? WHERE id=?",
                   (title, content, topic, db.now_str(), exist["id"]))
        return exist["id"]
    return db.execute("INSERT INTO drafts(user_id,title,content,topic,updated_at) VALUES(?,?,?,?,?)",
                      (uid, title, content, topic, db.now_str()))


def list_drafts(uid: int) -> list:
    return db.query("SELECT * FROM drafts WHERE user_id=? ORDER BY updated_at DESC", (uid,))


def delete_draft(did: int, uid: int) -> None:
    db.execute("DELETE FROM drafts WHERE id=? AND user_id=?", (did, uid))
