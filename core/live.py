"""直播讲课系列：直播列表、预约提醒、直播间、实时聊天、互动工具、连麦、回放、讲师体系。"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import auth, courses, db, notify, users

REPLAY_ACCESS = {"free": "免费", "paid": "仅购课用户可看", "limited": "限时免费"}


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------- 直播 CRUD ----------------------------
def create_live(instructor_id: int, title: str, start_at: str = "", intro: str = "",
                price: float = 0, replay_access: str = "paid", course_id: int = 0,
                cover: str = "") -> int:
    u = auth.get_user(instructor_id)
    if not u or u["instructor_status"] != "approved":
        raise auth.AuthError("只有认证讲师才能开播")
    if not (title or "").strip():
        raise auth.AuthError("直播标题不能为空")
    if not start_at:
        start_at = _fmt(datetime.now() + timedelta(days=1))
    if replay_access not in REPLAY_ACCESS:
        replay_access = "paid"
    return db.execute(
        """INSERT INTO lives(course_id,instructor_id,title,cover,intro,start_at,status,
                             price,replay_access,created_at)
           VALUES(?,?,?,?,?,?,'upcoming',?,?,?)""",
        (course_id, instructor_id, title.strip(), cover, intro, start_at,
         float(price or 0), replay_access, db.now_str()),
    )


def get_live(lid: int):
    return db.query_one(
        """SELECT l.*, u.username AS instructor_name, u.nickname AS instructor_nick,
                  u.avatar AS instructor_avatar, c.title AS course_title
           FROM lives l LEFT JOIN users u ON u.id=l.instructor_id
           LEFT JOIN courses c ON c.id=l.course_id WHERE l.id=?""", (lid,))


def list_lives(status: str = "", instructor_id: int = 0, limit: int = 100) -> list:
    sql = ("SELECT l.*, u.nickname AS instructor_nick, u.avatar AS instructor_avatar "
           "FROM lives l LEFT JOIN users u ON u.id=l.instructor_id WHERE 1=1")
    params: list = []
    if status:
        sql += " AND l.status=?"; params.append(status)
    if instructor_id:
        sql += " AND l.instructor_id=?"; params.append(instructor_id)
    sql += " ORDER BY CASE l.status WHEN 'live' THEN 0 WHEN 'upcoming' THEN 1 ELSE 2 END, l.start_at"
    sql += " LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def grouped_lives() -> dict:
    return {
        "live": list_lives("live"),
        "upcoming": list_lives("upcoming"),
        "replay": list_lives("replay") + list_lives("ended"),
    }


def set_status(lid: int, status: str, by: int = 0) -> None:
    l = get_live(lid)
    if not l:
        raise auth.AuthError("直播不存在")
    if by and l["instructor_id"] != by:
        raise auth.AuthError("只有本场讲师可以控制直播状态")
    if status not in ("upcoming", "live", "replay", "ended"):
        raise auth.AuthError("非法状态")
    db.execute("UPDATE lives SET status=? WHERE id=?", (status, lid))
    if status == "live":
        for r in db.query("SELECT user_id FROM live_reservations WHERE live_id=?", (lid,)):
            notify.push(r["user_id"], "live", f"你预约的直播《{l['title']}》正在直播中，点击进入直播间。",
                        link=f"live:{lid}")
    if status == "replay" and l["course_id"]:
        _attach_replay_lesson(l)


def _attach_replay_lesson(l: dict) -> None:
    """直播结束自动生成回放课时，进入课程体系（需求书 8.10）。"""
    cid = l["course_id"]
    ch = db.query_one("SELECT * FROM chapters WHERE course_id=? AND title='直播回放'", (cid,))
    chapter_id = ch["id"] if ch else courses.add_chapter(cid, "直播回放")
    exist = db.query_one("SELECT id FROM lessons WHERE course_id=? AND title=? AND ltype='video'",
                         (cid, f"回放 · {l['title']}"))
    if not exist:
        courses.add_lesson(cid, chapter_id, f"回放 · {l['title']}", "video",
                           content=f"直播回放（原直播 #{l['id']}）", duration=3600, is_free=False)


# ---------------------------- 预约与提醒 ----------------------------
def reserve(lid: int, uid: int) -> None:
    if not uid:
        raise auth.AuthError("请先登录")
    l = get_live(lid)
    if not l:
        raise auth.AuthError("直播不存在")
    db.execute("INSERT OR IGNORE INTO live_reservations(live_id,user_id,created_at) VALUES(?,?,?)",
               (lid, uid, db.now_str()))


def unreserve(lid: int, uid: int) -> None:
    db.execute("DELETE FROM live_reservations WHERE live_id=? AND user_id=?", (lid, uid))


def is_reserved(lid: int, uid: int) -> bool:
    return db.query_one("SELECT 1 FROM live_reservations WHERE live_id=? AND user_id=?",
                        (lid, uid)) is not None


def my_reservations(uid: int) -> list:
    return db.query("""SELECT l.* FROM live_reservations r JOIN lives l ON l.id=r.live_id
                       WHERE r.user_id=? ORDER BY l.start_at""", (uid,))


def remind_due(minutes: int = 15) -> int:
    """开播前 N 分钟提醒（由后台定时任务调用）。"""
    now = datetime.now()
    lo, hi = _fmt(now), _fmt(now + timedelta(minutes=minutes))
    rows = db.query("SELECT * FROM lives WHERE status='upcoming' AND start_at BETWEEN ? AND ?", (lo, hi))
    cnt = 0
    for l in rows:
        for r in db.query("SELECT user_id FROM live_reservations WHERE live_id=? AND reminded=0", (l["id"],)):
            notify.push(r["user_id"], "live", f"直播《{l['title']}》将在 {minutes} 分钟后开播，请做好准备。",
                        link=f"live:{l['id']}")
            db.execute("UPDATE live_reservations SET reminded=1 WHERE live_id=? AND user_id=?",
                       (l["id"], r["user_id"]))
            cnt += 1
    return cnt


def reservation_count(lid: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM live_reservations WHERE live_id=?", (lid,), 0))


# ---------------------------- 直播间：聊天 / 互动 ----------------------------
def send_chat(lid: int, uid: int, content: str) -> int:
    if not uid:
        raise auth.AuthError("仅登录用户可在直播间发言")
    if not (content or "").strip():
        raise auth.AuthError("发言内容不能为空")
    if len(content) > 500:
        raise auth.AuthError("单条发言不能超过 500 字")
    return db.execute("INSERT INTO live_chat(live_id,user_id,content,created_at) VALUES(?,?,?,?)",
                      (lid, uid, content.strip(), db.now_str()))


def list_chat(lid: int, limit: int = 200) -> list:
    rows = db.query(
        """SELECT c.*, u.nickname, u.username, u.avatar, u.role, u.instructor_status
           FROM live_chat c LEFT JOIN users u ON u.id=c.user_id
           WHERE c.live_id=? ORDER BY c.id ASC LIMIT ?""", (lid, limit))
    return rows


def toggle_like(lid: int, uid: int) -> int:
    db.execute("UPDATE lives SET likes=likes+1 WHERE id=?", (lid,))
    return int(db.scalar("SELECT likes FROM lives WHERE id=?", (lid,), 0))


def join_room(lid: int) -> int:
    """进入直播间，在线人数 +1（会话级计数，退出时减 1）。"""
    db.execute("UPDATE lives SET online_count=online_count+1 WHERE id=?", (lid,))
    return int(db.scalar("SELECT online_count FROM lives WHERE id=?", (lid,), 0))


def leave_room(lid: int) -> None:
    db.execute("UPDATE lives SET online_count=MAX(online_count-1,0) WHERE id=?", (lid,))


def create_interaction(lid: int, itype: str, question: str, options: list) -> int:
    import json
    if itype not in ("poll", "question", "lottery", "quiz"):
        raise auth.AuthError("不支持的互动类型")
    return db.execute(
        "INSERT INTO live_interactions(live_id,itype,question,payload,created_at) VALUES(?,?,?,?,?)",
        (lid, itype, question, json.dumps(options, ensure_ascii=False), db.now_str()),
    )


def list_interactions(lid: int) -> list:
    import json
    rows = db.query("SELECT * FROM live_interactions WHERE live_id=? ORDER BY id DESC", (lid,))
    for r in rows:
        try:
            r["options"] = json.loads(r["payload"])
        except Exception:
            r["options"] = []
        r["votes"] = vote_stats(r["id"])
    return rows


def vote_stats(iid: int) -> dict:
    rows = db.query("SELECT choice, COUNT(*) AS c FROM live_votes WHERE interaction_id=? GROUP BY choice", (iid,))
    return {r["choice"]: r["c"] for r in rows}


def vote(iid: int, uid: int, choice: str) -> None:
    if not uid:
        raise auth.AuthError("请先登录")
    db.execute(
        "INSERT INTO live_votes(interaction_id,user_id,choice,created_at) VALUES(?,?,?,?) "
        "ON CONFLICT(interaction_id,user_id) DO UPDATE SET choice=excluded.choice",
        (iid, uid, choice, db.now_str()),
    )


def my_vote(iid: int, uid: int):
    r = db.query_one("SELECT choice FROM live_votes WHERE interaction_id=? AND user_id=?", (iid, uid))
    return r["choice"] if r else None


# ---------------------------- 连麦 ----------------------------
def raise_hand(lid: int, uid: int) -> None:
    if not uid:
        raise auth.AuthError("请先登录")
    db.execute("INSERT OR REPLACE INTO live_handraise(live_id,user_id,status,created_at) "
               "VALUES(?,?,'pending',?)", (lid, uid, db.now_str()))


def hand_queue(lid: int) -> list:
    return db.query(
        """SELECT h.*, u.nickname, u.username, u.avatar FROM live_handraise h
           LEFT JOIN users u ON u.id=h.user_id WHERE h.live_id=? ORDER BY h.created_at""", (lid,))


def set_hand(lid: int, uid: int, status: str) -> None:
    db.execute("UPDATE live_handraise SET status=? WHERE live_id=? AND user_id=?", (status, lid, uid))
    if status == "approved":
        notify.push(uid, "live", "讲师已同意你的连麦申请，请准备发言。", link=f"live:{lid}")


# ---------------------------- 回放权限 ----------------------------
def can_watch_replay(l: dict, uid: int) -> tuple[bool, str]:
    if not l:
        return False, "直播不存在"
    if l["status"] in ("live",):
        return True, ""
    if l["status"] in ("upcoming",):
        return False, "直播尚未开始"
    access = l["replay_access"]
    if access == "free":
        return True, ""
    if access == "limited":
        try:
            ended_ok = True
        except Exception:
            ended_ok = True
        return True, ""
    if l["course_id"]:
        if courses.is_enrolled(uid, l["course_id"]):
            return True, ""
        return False, "该回放仅购课用户可看，请先购买对应课程"
    return False, "该回放仅购课用户可看"


def player_placeholder(l: dict) -> str:
    """占位播放器地址。真实接入时替换为腾讯云直播/阿里云直播/OBS-RTMP 的可播地址。"""
    return f"rtmp://demo.bgl.local/live/{l['id']}"
