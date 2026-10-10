"""全站搜索：一次检索新闻、帖子、文件、用户、课程、直播。"""

from __future__ import annotations

from . import db


def global_search(keyword: str, uid: int = 0, limit: int = 5) -> dict:
    kw = (keyword or "").strip()
    if not kw:
        return {}
    like = f"%{kw}%"
    out: dict[str, list] = {}

    out["新闻"] = db.query(
        "SELECT id,title,summary AS sub,category AS tag FROM news "
        "WHERE status='published' AND (title LIKE ? OR summary LIKE ?) ORDER BY publish_time DESC LIMIT ?",
        (like, like, limit))
    out["帖子"] = db.query(
        "SELECT id,COALESCE(NULLIF(title,''),substr(content,1,40)) AS title,"
        "substr(content,1,60) AS sub,topic AS tag FROM posts "
        "WHERE status='published' AND (title LIKE ? OR content LIKE ?) ORDER BY id DESC LIMIT ?",
        (like, like, limit))
    vis_clause = "(visibility='public'"
    if uid:
        vis_clause += " OR user_id=" + str(int(uid))
    vis_clause += ")"
    out["文件"] = db.query(
        "SELECT id,filename AS title,category AS sub,tags AS tag FROM files "
        "WHERE deleted=0 AND " + vis_clause + " AND (filename LIKE ? OR tags LIKE ?) LIMIT ?",
        (like, like, limit))
    out["用户"] = db.query(
        "SELECT id,username AS title,COALESCE(NULLIF(nickname,''),username) AS sub,bio AS tag "
        "FROM users WHERE status='active' AND (username LIKE ? OR nickname LIKE ? OR bio LIKE ?) LIMIT ?",
        (like, like, like, limit))
    out["课程"] = db.query(
        "SELECT id,title,category AS sub,CAST(price AS TEXT) AS tag FROM courses "
        "WHERE status='on' AND (title LIKE ? OR intro LIKE ? OR tags LIKE ?) LIMIT ?",
        (like, like, like, limit))
    out["直播"] = db.query(
        "SELECT id,title,status AS sub,start_at AS tag FROM lives "
        "WHERE title LIKE ? OR intro LIKE ? LIMIT ?", (like, like, limit))
    out["知识点"] = db.query(
        "SELECT id,title,module AS sub,difficulty AS tag FROM knowledge "
        "WHERE title LIKE ? OR summary LIKE ? OR body LIKE ? LIMIT ?",
        (like, like, like, limit))
    return {k: v for k, v in out.items() if v}


def total_hits(result: dict) -> int:
    return sum(len(v) for v in (result or {}).values())
