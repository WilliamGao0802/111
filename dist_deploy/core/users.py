"""用户资料、关注/粉丝、个人主页、排行榜、在线状态与管理员用户管理。"""

from __future__ import annotations

from . import auth, db, notify


def update_profile(uid: int, nickname=None, avatar=None, bio=None) -> None:
    sets, params = [], []
    if nickname is not None:
        nick = str(nickname).strip()
        if len(nick) > 20:
            raise auth.AuthError("昵称不能超过 20 个字符")
        sets.append("nickname=?"); params.append(nick or (auth.get_user(uid) or {}).get("username", ""))
    if avatar is not None:
        sets.append("avatar=?"); params.append(str(avatar).strip())
    if bio is not None:
        if len(str(bio)) > 200:
            raise auth.AuthError("个性签名不能超过 200 个字符")
        sets.append("bio=?"); params.append(str(bio).strip())
    if not sets:
        return
    params.append(uid)
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(params))


def display_name(user) -> str:
    if not user:
        return "已注销用户"
    return user.get("nickname") or user.get("username") or "匿名用户"


def avatar_of(user) -> str:
    if not user:
        return "👤"
    return user.get("avatar") or "👤"


# ---------------------------- 关注 / 粉丝 ----------------------------
def follow(uid: int, target: int) -> None:
    if uid == target:
        raise auth.AuthError("不能关注自己")
    if not auth.get_user(target):
        raise auth.AuthError("该用户不存在")
    if is_following(uid, target):
        return
    db.execute("INSERT INTO follows(follower_id,followee_id,created_at) VALUES(?,?,?)",
               (uid, target, db.now_str()))
    notify.push(target, "follow", f"{display_name(auth.get_user(uid))} 关注了你")
    auth.add_points(uid, auth.POINT_RULES["like"], "关注他人")


def unfollow(uid: int, target: int) -> None:
    db.execute("DELETE FROM follows WHERE follower_id=? AND followee_id=?", (uid, target))


def is_following(uid: int, target: int) -> bool:
    return db.query_one("SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?",
                        (uid, target)) is not None


def mutual(uid: int, target: int) -> bool:
    return is_following(uid, target) and is_following(target, uid)


def following_list(uid: int) -> list:
    return db.query(
        """SELECT u.* FROM follows f JOIN users u ON u.id=f.followee_id
           WHERE f.follower_id=? ORDER BY f.created_at DESC""", (uid,))


def follower_list(uid: int) -> list:
    return db.query(
        """SELECT u.* FROM follows f JOIN users u ON u.id=f.follower_id
           WHERE f.followee_id=? ORDER BY f.created_at DESC""", (uid,))


def following_ids(uid: int) -> list[int]:
    return [r["followee_id"] for r in db.query(
        "SELECT followee_id FROM follows WHERE follower_id=?", (uid,))]


def stat_counts(uid: int) -> dict:
    return {
        "following": int(db.scalar("SELECT COUNT(*) FROM follows WHERE follower_id=?", (uid,), 0)),
        "followers": int(db.scalar("SELECT COUNT(*) FROM follows WHERE followee_id=?", (uid,), 0)),
        "posts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE user_id=? AND status='published'", (uid,), 0)),
        "files": int(db.scalar("SELECT COUNT(*) FROM files WHERE user_id=? AND deleted=0", (uid,), 0)),
        "courses": int(db.scalar("SELECT COUNT(*) FROM enrollments WHERE user_id=?", (uid,), 0)),
        "orders": int(db.scalar("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,), 0)),
        "liked": int(db.scalar("SELECT COUNT(*) FROM post_likes WHERE user_id=?", (uid,), 0)),
    }


def user_activity(uid: int, limit: int = 20) -> dict:
    return {
        "posts": db.query("SELECT id,title,content,created_at FROM posts WHERE user_id=? "
                          "AND status='published' ORDER BY id DESC LIMIT ?", (uid, limit)),
        "comments": db.query("SELECT c.*, p.title AS post_title FROM comments c "
                             "LEFT JOIN posts p ON p.id=c.post_id WHERE c.user_id=? "
                             "ORDER BY c.id DESC LIMIT ?", (uid, limit)),
        "files": db.query("SELECT * FROM files WHERE user_id=? AND deleted=0 ORDER BY id DESC LIMIT ?",
                          (uid, limit)),
        "enrollments": db.query(
            """SELECT e.*, c.title, c.cover FROM enrollments e JOIN courses c ON c.id=e.course_id
               WHERE e.user_id=? ORDER BY e.id DESC LIMIT ?""", (uid, limit)),
    }


# ---------------------------- 排行榜 ----------------------------
def leaderboard(kind: str = "active", limit: int = 10) -> list:
    if kind == "active":          # 最活跃用户：按积分
        return db.query(
            "SELECT id,username,nickname,avatar,points,level FROM users "
            "WHERE status='active' ORDER BY points DESC, id ASC LIMIT ?", (limit,))
    if kind == "followers":
        return db.query(
            """SELECT u.id,u.username,u.nickname,u.avatar,COUNT(f.follower_id) AS cnt
               FROM users u LEFT JOIN follows f ON f.followee_id=u.id
               WHERE u.status='active' GROUP BY u.id ORDER BY cnt DESC LIMIT ?""", (limit,))
    if kind == "posts":           # 最热帖子
        return db.query(
            "SELECT id,title,likes,user_id FROM posts WHERE status='published' "
            "ORDER BY likes DESC, id DESC LIMIT ?", (limit,))
    if kind == "files":           # 最受欢迎文件
        return db.query("SELECT id,filename,downloads,user_id FROM files WHERE deleted=0 "
                        "ORDER BY downloads DESC LIMIT ?", (limit,))
    if kind == "courses":
        return db.query("SELECT id,title,sales,rating FROM courses WHERE status='on' "
                        "ORDER BY sales DESC LIMIT ?", (limit,))
    if kind == "instructors":
        return db.query(
            """SELECT u.id,u.username,u.nickname,u.avatar,u.instructor_level,
                      COALESCE(SUM(c.sales),0) AS sales, COALESCE(AVG(c.rating),0) AS rating
               FROM users u LEFT JOIN courses c ON c.instructor_id=u.id
               WHERE u.instructor_status='approved'
               GROUP BY u.id ORDER BY sales DESC, rating DESC LIMIT ?""", (limit,))
    return []


# ---------------------------- 管理员：用户管理 ----------------------------
def admin_list_users(keyword: str = "", role: str = "", status: str = "", limit: int = 200) -> list:
    sql = "SELECT * FROM users WHERE 1=1"
    params: list = []
    if keyword:
        sql += " AND (username LIKE ? OR nickname LIKE ? OR email LIKE ?)"
        params += [f"%{keyword}%"] * 3
    if role:
        sql += " AND role=?"; params.append(role)
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def set_user_status(uid: int, status: str, reason: str = "") -> None:
    db.execute("UPDATE users SET status=?, online=0 WHERE id=?", (status, uid))
    auth.log(uid, "", "admin_set_status", f"{status} {reason}".strip())


def set_user_role(uid: int, role: str) -> None:
    db.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    auth.log(uid, "", "admin_set_role", role)


def grant_instructor(uid: int, approve: bool, level: int = 1) -> None:
    if approve:
        db.execute("UPDATE users SET instructor_status='approved', role='instructor', "
                   "instructor_level=? WHERE id=?", (level, uid))
        notify.push(uid, "system", "恭喜！你的讲师申请已通过审核，讲师工作台已开通。", link="instructor")
    else:
        db.execute("UPDATE users SET instructor_status='rejected' WHERE id=?", (uid,))
        notify.push(uid, "system", "很抱歉，你的讲师申请未通过审核，可补充资料后再次提交。", link="profile")
    auth.log(uid, "", "admin_instructor_review", "通过" if approve else "驳回")


def apply_instructor(uid: int, intro: str, field: str, proof: str) -> None:
    if not (intro or "").strip():
        raise auth.AuthError("请填写讲师简介")
    if not (field or "").strip():
        raise auth.AuthError("请填写擅长领域")
    db.execute("UPDATE users SET instructor_status='pending', instructor_intro=?, "
               "instructor_field=?, instructor_proof=? WHERE id=?", (intro, field, proof, uid))
    auth.log(uid, "", "instructor_apply", "提交讲师申请")


def pending_instructors() -> list:
    return db.query("SELECT * FROM users WHERE instructor_status='pending' ORDER BY id DESC")


def pending_realnames() -> list:
    return db.query("SELECT * FROM users WHERE realname_status='pending' ORDER BY id DESC")
