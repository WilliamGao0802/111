"""AI 新闻模块：列表、Top5、详情、分类标签、搜索、排序、收藏点赞、归档、RSS、每日推送。"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import auth, db, notify

CATEGORIES = ["大模型", "政策", "硬件", "应用", "安全"]


def all_tags() -> list:
    tags: set[str] = set()
    for r in db.query("SELECT tags FROM news WHERE tags<>''"):
        for t in str(r["tags"]).replace("，", ",").split(","):
            t = t.strip()
            if t:
                tags.add(t)
    return sorted(tags)


def list_news(category: str = "", tag: str = "", keyword: str = "",
              sort: str = "time", archived: bool = False,
              status: str = "published", limit: int = 50) -> list:
    sql = "SELECT * FROM news WHERE status=?"
    params: list = [status]
    sql += " AND archived=?"; params.append(1 if archived else 0)
    if category:
        sql += " AND category=?"; params.append(category)
    if tag:
        sql += " AND tags LIKE ?"; params.append(f"%{tag}%")
    if keyword:
        sql += " AND (title LIKE ? OR summary LIKE ?)"; params += [f"%{keyword}%"] * 2
    order = {"time": "publish_time DESC", "views": "views DESC", "likes": "likes DESC"}.get(sort, "publish_time DESC")
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def top_news(limit: int = 5) -> list:
    """近一年内最具影响力的 N 条：按「浏览量 + 点赞数×5」综合排序。"""
    year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    return db.query(
        """SELECT * FROM news WHERE status='published' AND archived=0 AND publish_time >= ?
           ORDER BY (views + likes*5) DESC, publish_time DESC LIMIT ?""",
        (year_ago, limit),
    )


def get_news(nid: int, count_view: bool = True):
    row = db.query_one("SELECT * FROM news WHERE id=?", (nid,))
    if row and count_view:
        db.execute("UPDATE news SET views=views+1 WHERE id=?", (nid,))
        row["views"] = row["views"] + 1
    return row


def related_news(nid: int, category: str, limit: int = 4) -> list:
    return db.query(
        "SELECT * FROM news WHERE id<>? AND category=? AND status='published' AND archived=0 "
        "ORDER BY publish_time DESC LIMIT ?", (nid, category, limit))


def create_news(title, summary, content="", category="大模型", tags="", source="",
                url="", image="", publish_time="", status="pending") -> int:
    if not (title or "").strip():
        raise auth.AuthError("新闻标题不能为空")
    if not (summary or "").strip():
        raise auth.AuthError("新闻摘要不能为空")
    if category not in CATEGORIES:
        category = "大模型"
    return db.execute(
        """INSERT INTO news(title,summary,content,category,tags,source,url,image,
                            publish_time,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (title.strip(), summary.strip(), content or "", category, tags or "", source or "",
         url or "", image or "", publish_time or db.now_str(), status, db.now_str()),
    )


def publish_news(nid: int) -> None:
    db.execute("UPDATE news SET status='published' WHERE id=?", (nid,))
    auth.log(0, "", "news_publish", f"发布新闻 #{nid}")


def reject_news(nid: int) -> None:
    db.execute("UPDATE news SET status='rejected' WHERE id=?", (nid,))


def pending_news() -> list:
    return db.query("SELECT * FROM news WHERE status='pending' ORDER BY id DESC")


def archive_old() -> int:
    """超过一年的新闻归档到「往期新闻」。"""
    year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    with db.tx() as conn:
        cur = conn.execute("UPDATE news SET archived=1 WHERE publish_time < ? AND archived=0", (year_ago,))
        return cur.rowcount


def toggle_like(uid: int, nid: int) -> bool:
    if not uid:
        raise auth.AuthError("请先登录")
    exists = db.query_one("SELECT 1 FROM news_likes WHERE user_id=? AND news_id=?", (uid, nid))
    if exists:
        db.execute("DELETE FROM news_likes WHERE user_id=? AND news_id=?", (uid, nid))
        db.execute("UPDATE news SET likes=MAX(likes-1,0) WHERE id=?", (nid,))
        return False
    db.execute("INSERT INTO news_likes(user_id,news_id,created_at) VALUES(?,?,?)", (uid, nid, db.now_str()))
    db.execute("UPDATE news SET likes=likes+1 WHERE id=?", (nid,))
    auth.add_points(uid, auth.POINT_RULES["like"], "点赞新闻")
    return True


def toggle_fav(uid: int, nid: int) -> bool:
    if not uid:
        raise auth.AuthError("请先登录")
    exists = db.query_one("SELECT 1 FROM news_favs WHERE user_id=? AND news_id=?", (uid, nid))
    if exists:
        db.execute("DELETE FROM news_favs WHERE user_id=? AND news_id=?", (uid, nid))
        return False
    db.execute("INSERT INTO news_favs(user_id,news_id,created_at) VALUES(?,?,?)", (uid, nid, db.now_str()))
    return True


def liked_ids(uid: int) -> set:
    if not uid:
        return set()
    return {r["news_id"] for r in db.query("SELECT news_id FROM news_likes WHERE user_id=?", (uid,))}


def faved_ids(uid: int) -> set:
    if not uid:
        return set()
    return {r["news_id"] for r in db.query("SELECT news_id FROM news_favs WHERE user_id=?", (uid,))}


def my_favs(uid: int) -> list:
    return db.query("""SELECT n.* FROM news_favs f JOIN news n ON n.id=f.news_id
                       WHERE f.user_id=? ORDER BY f.created_at DESC""", (uid,))


def daily_pick():
    """每日精选一条：按日期取模，保证同一天稳定。"""
    rows = db.query("SELECT * FROM news WHERE status='published' ORDER BY id ASC")
    if not rows:
        return None
    idx = datetime.now().timetuple().tm_yday % len(rows)
    return rows[idx]


def fetch_from_sources() -> list:
    """定时自动抓取：演示模式下从内置可信源模板生成待审核条目。

    真实接入时替换为 RSS/API 抓取器（接口已预留：返回 list[dict] 即可）。
    """
    from . import seed
    return seed.auto_fetch_templates()


def to_rss(base_url: str = "http://localhost:8501", limit: int = 20) -> str:
    import xml.sax.saxutils as su
    rows = list_news(limit=limit)
    items = []
    for n in rows:
        link = n["url"] or f"{base_url}/?news={n['id']}"
        items.append(
            "    <item>\n"
            f"      <title>{su.escape(n['title'])}</title>\n"
            f"      <link>{su.escape(link)}</link>\n"
            f"      <description>{su.escape(n['summary'])}</description>\n"
            f"      <category>{su.escape(n['category'])}</category>\n"
            f"      <pubDate>{su.escape(n['publish_time'])}</pubDate>\n"
            "    </item>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
            "    <title>BGL 的 AI 学习 · AI 新闻</title>\n"
            f"    <link>{base_url}</link>\n"
            "    <description>AI 领域近一年重要新闻</description>\n"
            + "\n".join(items) + "\n  </channel>\n</rss>\n")


def push_daily(user_ids: list[int]) -> int:
    pick = daily_pick()
    if not pick:
        return 0
    cnt = 0
    for uid in user_ids:
        notify.push(uid, "news", f"每日精选：{pick['title']}", link=f"news:{pick['id']}")
        cnt += 1
    return cnt
