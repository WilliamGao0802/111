"""课程体系：课程/章节/课时管理、上架下架、搜索筛选、试看、报名、进度、评价、问答、结业证书。"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from . import auth, db, notify, users

CATEGORIES = ["大模型基础", "提示词工程", "微调实战", "AI 应用开发", "数据与算力", "职业发展"]
CTYPES = {"recorded": "录播课", "live": "直播课", "text": "图文课"}
LTYPES = {"video": "视频", "live": "直播", "doc": "文档", "quiz": "测验"}


# ---------------------------- 课程 CRUD ----------------------------
def create_course(instructor_id: int, title: str, intro: str = "", category: str = "大模型基础",
                  price: float = 0, original_price: float = 0, ctype: str = "recorded",
                  cover: str = "", tags: str = "", validity_days: int = 0,
                  status: str = "draft") -> int:
    u = auth.get_user(instructor_id)
    if not u or u["instructor_status"] != "approved":
        raise auth.AuthError("只有通过认证的讲师才能创建课程")
    if not (title or "").strip():
        raise auth.AuthError("课程标题不能为空")
    if category not in CATEGORIES:
        category = "大模型基础"
    if ctype not in CTYPES:
        ctype = "recorded"
    return db.execute(
        """INSERT INTO courses(instructor_id,title,cover,intro,category,tags,price,original_price,
                               ctype,status,validity_days,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (instructor_id, title.strip(), cover, intro, category, tags, float(price or 0),
         float(original_price or 0), ctype, status, int(validity_days or 0), db.now_str()),
    )


def update_course(cid: int, instructor_id: int, **fields) -> None:
    c = get_course(cid)
    if not c:
        raise auth.AuthError("课程不存在")
    if c["instructor_id"] != instructor_id:
        raise auth.AuthError("只能编辑自己的课程")
    allow = {"title", "intro", "category", "price", "original_price", "cover",
             "tags", "validity_days", "status", "ctype", "outline"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allow:
            sets.append(f"{k}=?"); params.append(v)
    if not sets:
        return
    params.append(cid)
    db.execute(f"UPDATE courses SET {', '.join(sets)} WHERE id=?", tuple(params))


def set_status(cid: int, status: str, by: int = 0, is_admin: bool = False) -> None:
    c = get_course(cid)
    if not c:
        raise auth.AuthError("课程不存在")
    if not is_admin and c["instructor_id"] != by:
        raise auth.AuthError("无权操作该课程")
    db.execute("UPDATE courses SET status=? WHERE id=?", (status, cid))
    if is_admin and status == "off":
        notify.push(c["instructor_id"], "system", f"你的课程《{c['title']}》已被管理员强制下架。",
                    link="instructor")


def get_course(cid: int):
    return db.query_one(
        """SELECT c.*, u.username AS instructor_name, u.nickname AS instructor_nick,
                  u.avatar AS instructor_avatar, u.instructor_level, u.instructor_field
           FROM courses c LEFT JOIN users u ON u.id=c.instructor_id WHERE c.id=?""", (cid,))


def list_courses(keyword: str = "", category: str = "", min_price: float = -1,
                 max_price: float = -1, min_rating: float = 0, ctype: str = "",
                 instructor_id: int = 0, sort: str = "sales",
                 status: str = "on", limit: int = 100) -> list:
    sql = ("SELECT c.*, u.nickname AS instructor_nick, u.avatar AS instructor_avatar "
           "FROM courses c LEFT JOIN users u ON u.id=c.instructor_id WHERE 1=1")
    params: list = []
    if status:
        sql += " AND c.status=?"; params.append(status)
    if keyword:
        sql += " AND (c.title LIKE ? OR c.intro LIKE ? OR c.tags LIKE ?)"; params += [f"%{keyword}%"] * 3
    if category:
        sql += " AND c.category=?"; params.append(category)
    if ctype:
        sql += " AND c.ctype=?"; params.append(ctype)
    if min_price >= 0:
        sql += " AND c.price >= ?"; params.append(min_price)
    if max_price >= 0:
        sql += " AND c.price <= ?"; params.append(max_price)
    if min_rating > 0:
        sql += " AND c.rating >= ?"; params.append(min_rating)
    if instructor_id:
        sql += " AND c.instructor_id=?"; params.append(instructor_id)
    order = {"sales": "c.sales DESC, c.rating DESC", "rating": "c.rating DESC, c.rating_count DESC",
             "new": "c.id DESC", "price_asc": "c.price ASC", "price_desc": "c.price DESC"}.get(sort, "c.sales DESC")
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def instructor_courses(instructor_id: int) -> list:
    return db.query("SELECT * FROM courses WHERE instructor_id=? ORDER BY id DESC", (instructor_id,))


# ---------------------------- 章节 / 课时 ----------------------------
def add_chapter(cid: int, title: str) -> int:
    order = int(db.scalar("SELECT COALESCE(MAX(order_no),0)+1 FROM chapters WHERE course_id=?", (cid,), 1))
    return db.execute("INSERT INTO chapters(course_id,title,order_no) VALUES(?,?,?)", (cid, title, order))


def add_lesson(cid: int, chapter_id: int, title: str, ltype: str = "video",
               content: str = "", duration: int = 0, is_free: bool = False) -> int:
    order = int(db.scalar("SELECT COALESCE(MAX(order_no),0)+1 FROM lessons WHERE chapter_id=?",
                          (chapter_id,), 1))
    return db.execute(
        """INSERT INTO lessons(course_id,chapter_id,title,ltype,content,duration,is_free,order_no)
           VALUES(?,?,?,?,?,?,?,?)""",
        (cid, chapter_id, title, ltype if ltype in LTYPES else "video", content,
         int(duration or 0), 1 if is_free else 0, order),
    )


def chapters(cid: int) -> list:
    return db.query("SELECT * FROM chapters WHERE course_id=? ORDER BY order_no, id", (cid,))


def lessons(cid: int, chapter_id: int = 0) -> list:
    if chapter_id:
        return db.query("SELECT * FROM lessons WHERE course_id=? AND chapter_id=? ORDER BY order_no, id",
                        (cid, chapter_id))
    return db.query("SELECT * FROM lessons WHERE course_id=? ORDER BY chapter_id, order_no, id", (cid,))


def lesson_count(cid: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM lessons WHERE course_id=?", (cid,), 0))


def course_tree(cid: int) -> list:
    """返回 [{chapter, lessons:[...]}] 结构，供大纲渲染。"""
    out = []
    for ch in chapters(cid):
        out.append({"chapter": ch, "lessons": lessons(cid, ch["id"])})
    orphan = db.query("SELECT * FROM lessons WHERE course_id=? AND chapter_id=0", (cid,))
    if orphan:
        out.append({"chapter": {"id": 0, "title": "未分章内容", "order_no": 999}, "lessons": orphan})
    return out


# ---------------------------- 报名 / 学习 ----------------------------
def is_enrolled(uid: int, cid: int) -> bool:
    if not uid:
        return False
    return db.query_one("SELECT 1 FROM enrollments WHERE user_id=? AND course_id=?", (uid, cid)) is not None


def enroll(uid: int, cid: int, order_id: int = 0, force: bool = False) -> None:
    """开通课程权限。购课场景要求已完成实名认证（需求书第五章 6.1）。"""
    if not uid:
        raise auth.AuthError("请先登录")
    c = get_course(cid)
    if not c:
        raise auth.AuthError("课程不存在")
    if is_enrolled(uid, cid):
        return
    if c["price"] > 0 and not force and not auth.is_realname_ok(uid):
        raise auth.AuthError("购买课程需要先完成实名认证，请前往「个人中心 → 实名认证」提交")
    expires = ""
    if int(c["validity_days"] or 0) > 0:
        expires = (datetime.now() + timedelta(days=int(c["validity_days"]))).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """INSERT INTO enrollments(user_id,course_id,order_id,progress,completed,created_at,expires_at)
           VALUES(?,?,?,0,0,?,?)""",
        (uid, cid, order_id, db.now_str(), expires),
    )
    db.execute("UPDATE courses SET sales=sales+1 WHERE id=?", (cid,))
    auth.add_points(uid, auth.POINT_RULES["buy_course"], "购课成功")
    notify.push(uid, "order", f"《{c['title']}》已开通，快去学习吧！", link="my")


def is_expired(e: dict) -> bool:
    exp = (e or {}).get("expires_at") or ""
    if not exp:
        return False
    try:
        return datetime.strptime(exp, "%Y-%m-%d %H:%M:%S") < datetime.now()
    except ValueError:
        return False


def my_courses(uid: int) -> list:
    return db.query(
        """SELECT e.*, c.title, c.cover, c.category, c.price, c.ctype, c.validity_days
           FROM enrollments e JOIN courses c ON c.id=e.course_id
           WHERE e.user_id=? ORDER BY e.id DESC""", (uid,))


def get_enrollment(uid: int, cid: int):
    return db.query_one("SELECT * FROM enrollments WHERE user_id=? AND course_id=?", (uid, cid))


def mark_lesson(uid: int, lesson_id: int, completed: bool = True) -> None:
    l = db.query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
    if not l:
        raise auth.AuthError("课时不存在")
    cid = l["course_id"]
    db.execute(
        """INSERT INTO lesson_progress(user_id,lesson_id,course_id,completed,updated_at)
           VALUES(?,?,?,?,?)
           ON CONFLICT(user_id,lesson_id) DO UPDATE SET completed=excluded.completed,
                                                        updated_at=excluded.updated_at""",
        (uid, lesson_id, cid, 1 if completed else 0, db.now_str()),
    )
    if completed:
        auth.add_points(uid, auth.POINT_RULES["watch_lesson"], "完成课时学习")
    _recalc_progress(uid, cid)


def _recalc_progress(uid: int, cid: int) -> None:
    total = lesson_count(cid)
    if total == 0:
        return
    done = int(db.scalar(
        "SELECT COUNT(*) FROM lesson_progress WHERE user_id=? AND course_id=? AND completed=1",
        (uid, cid), 0))
    progress = round(done / total * 100, 1)
    completed = 1 if done >= total else 0
    e = get_enrollment(uid, cid)
    db.execute("UPDATE enrollments SET progress=?, completed=? WHERE user_id=? AND course_id=?",
               (progress, completed, uid, cid))
    if completed and e and not e["certificate_code"]:
        issue_certificate(uid, cid)


def lesson_done(uid: int, lesson_id: int) -> bool:
    return db.query_one("SELECT 1 FROM lesson_progress WHERE user_id=? AND lesson_id=? AND completed=1",
                        (uid, lesson_id)) is not None


def completed_lesson_ids(uid: int, cid: int) -> set:
    return {r["lesson_id"] for r in db.query(
        "SELECT lesson_id FROM lesson_progress WHERE user_id=? AND course_id=? AND completed=1",
        (uid, cid))}


def issue_certificate(uid: int, cid: int) -> str:
    code = f"BGL-{cid:04d}-{uid:05d}-{secrets.token_hex(3).upper()}"
    db.execute("UPDATE enrollments SET certificate_code=? WHERE user_id=? AND course_id=?",
               (code, uid, cid))
    c = get_course(cid)
    notify.push(uid, "system", f"恭喜完成《{c['title'] if c else ''}》，已发放电子结业证书。", link="my")
    auth.log(uid, "", "certificate", code)
    return code


# ---------------------------- 评价 / 问答 ----------------------------
def review_course(uid: int, cid: int, rating: int, content: str = "") -> None:
    if not is_enrolled(uid, cid):
        raise auth.AuthError("只有已购学员才能评价")
    rating = max(1, min(5, int(rating)))
    exist = db.query_one("SELECT id FROM course_reviews WHERE user_id=? AND course_id=?", (uid, cid))
    if exist:
        db.execute("UPDATE course_reviews SET rating=?,content=?,created_at=? WHERE id=?",
                   (rating, content, db.now_str(), exist["id"]))
    else:
        db.execute("INSERT INTO course_reviews(course_id,user_id,rating,content,created_at) "
                   "VALUES(?,?,?,?,?)", (cid, uid, rating, content, db.now_str()))
    _recalc_rating(cid)


def _recalc_rating(cid: int) -> None:
    row = db.query_one("SELECT AVG(rating) AS a, COUNT(*) AS c FROM course_reviews WHERE course_id=?", (cid,))
    avg = round(float((row or {}).get("a") or 0), 2)
    cnt = int((row or {}).get("c") or 0)
    db.execute("UPDATE courses SET rating=?, rating_count=? WHERE id=?", (avg, cnt, cid))


def course_reviews(cid: int) -> list:
    return db.query(
        """SELECT r.*, u.nickname, u.username, u.avatar FROM course_reviews r
           LEFT JOIN users u ON u.id=r.user_id WHERE r.course_id=? ORDER BY r.id DESC""", (cid,))


def ask_question(uid: int, cid: int, question: str) -> int:
    if not (question or "").strip():
        raise auth.AuthError("问题内容不能为空")
    qid = db.execute("INSERT INTO course_qa(course_id,user_id,question,created_at) VALUES(?,?,?,?)",
                     (cid, uid, question.strip(), db.now_str()))
    c = get_course(cid)
    if c:
        notify.push(c["instructor_id"], "system", f"你的课程《{c['title']}》收到新提问。", link="instructor")
    return qid


def answer_question(qid: int, instructor_id: int, answer: str) -> None:
    q = db.query_one("SELECT * FROM course_qa WHERE id=?", (qid,))
    if not q:
        raise auth.AuthError("问题不存在")
    c = get_course(q["course_id"])
    if not c or c["instructor_id"] != instructor_id:
        raise auth.AuthError("只有本课讲师可以回答")
    db.execute("UPDATE course_qa SET answer=?, answer_by=? WHERE id=?", (answer, instructor_id, qid))
    notify.push(q["user_id"], "comment", f"讲师回答了你在《{c['title']}》中的提问。", link="my")


def course_qa(cid: int) -> list:
    return db.query(
        """SELECT q.*, u.nickname, u.username, u.avatar FROM course_qa q
           LEFT JOIN users u ON u.id=q.user_id WHERE q.course_id=? ORDER BY q.id DESC""", (cid,))


def catalog_preview(cid: int) -> str:
    """生成课程大纲纯文本（封面介绍用）。"""
    lines = []
    for node in course_tree(cid):
        lines.append(f"【{node['chapter']['title']}】")
        for l in node["lessons"]:
            tag = "（试看）" if l["is_free"] else ""
            lines.append(f"  · {l['title']}{tag}")
    return "\n".join(lines)


def stats(instructor_id: int = 0) -> dict:
    where = "WHERE instructor_id=?" if instructor_id else ""
    params = (instructor_id,) if instructor_id else ()
    return {
        "courses": int(db.scalar(f"SELECT COUNT(*) FROM courses {where}", params, 0)),
        "on_sale": int(db.scalar(f"SELECT COUNT(*) FROM courses {where}{' AND' if where else ' WHERE'} status='on'", params, 0)),
        "students": int(db.scalar(
            f"""SELECT COUNT(*) FROM enrollments e {'JOIN courses c ON c.id=e.course_id WHERE c.instructor_id=?' if instructor_id else ''}""",
            params, 0)),
    }
