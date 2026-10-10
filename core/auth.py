"""用户系统：注册、登录、退出、密码校验与加盐哈希、验证码、实名认证。

对应需求书「一、用户系统」。全部逻辑离线可测，不 import streamlit。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from . import db

MAX_USERS = 1000                 # 注册用户总数上限
CODE_TTL_SECONDS = 60            # 短信/邮箱验证码有效期
CODE_MAX_TRIES = 5               # 验证码最大错误次数
LOCK_MINUTES = 10                # 账号锁定 / 验证码锁定 时长
MAX_LOGIN_FAILS = 5              # 连续登录失败次数上限
PBKDF2_ROUNDS = 120_000

DIGITS_RE = re.compile(r"^\d{6}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
IDCARD_RE = re.compile(r"^\d{17}[\dXx]$")

# 演示用管理员凭据（首次初始化时写入）
DEFAULT_ADMIN = ("admin", "123456")

POINT_RULES = {
    "post": 5, "like": 1, "be_liked": 2, "upload": 5,
    "sign_in": 10, "buy_course": 20, "watch_lesson": 2, "comment": 2,
}


class AuthError(Exception):
    """业务校验失败。message 直接面向用户，可展示。"""


# --------------------------------------------------------------------------
# 密码
# --------------------------------------------------------------------------
def validate_password(password: str) -> tuple[bool, str]:
    """密码必须恰好 6 位阿拉伯数字。"""
    if password is None:
        return False, "请输入密码"
    password = str(password).strip()
    if not password:
        return False, "请输入密码"
    if not password.isdigit():
        return False, "密码只能包含数字，请检查是否输入了字母或符号"
    if len(password) != 6:
        return False, f"密码必须恰好为 6 位数字，当前为 {len(password)} 位"
    return True, ""


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """加盐哈希：PBKDF2-HMAC-SHA256。返回 (hash, salt)。"""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS)
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def password_strength(password: str) -> tuple[int, str]:
    """返回 (0-100, 文案)。6 位纯数字场景下主要看是否弱口令。"""
    weak = {"123456", "000000", "111111", "666666", "888888", "654321", "123123", "112233"}
    if not DIGITS_RE.match(password or ""):
        return 10, "不符合规则"
    if password in weak:
        return 20, "弱口令（建议更换）"
    if len(set(password)) <= 2:
        return 40, "偏弱"
    return 70, "合格"


def level_of(points: int) -> int:
    """积分 → 等级：每 100 分一级，封顶 10 级。"""
    return max(1, min(10, 1 + int(points or 0) // 100))


def level_title(level: int) -> str:
    titles = ["初学乍练", "渐入门径", "小有所成", "融会贯通", "登堂入室",
              "炉火纯青", "出类拔萃", "独当一面", "一代宗师", "登峰造极"]
    return titles[max(0, min(len(titles) - 1, int(level) - 1))]


# --------------------------------------------------------------------------
# 注册 / 登录 / 退出
# --------------------------------------------------------------------------
def user_count() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM users WHERE status<>'cancelled'", default=0))


def get_user(uid: int):
    return db.query_one("SELECT * FROM users WHERE id=?", (uid,))


def get_user_by_name(username: str):
    return db.query_one("SELECT * FROM users WHERE username=?", (username,))


def _new_user(username, password, nickname="", email="", phone=""):
    ok, msg = validate_password(password)
    if not ok:
        raise AuthError(msg)
    if not USERNAME_RE.match(username or ""):
        raise AuthError("用户名需为 2–20 位中文、字母、数字或下划线")
    if email and not EMAIL_RE.match(email):
        raise AuthError("邮箱格式不正确")
    if phone and not PHONE_RE.match(phone):
        raise AuthError("手机号格式不正确")
    if get_user_by_name(username):
        raise AuthError(f"用户名「{username}」已被注册，请更换")
    if user_count() >= MAX_USERS:
        raise AuthError(f"注册用户数已达上限 {MAX_USERS} 人，暂无法注册新账号")
    pw_hash, salt = hash_password(password)
    ts = db.now_str()
    uid = db.execute(
        """INSERT INTO users(username,password_hash,salt,nickname,email,phone,points,level,
                             created_at,last_active_at,online)
           VALUES(?,?,?,?,?,?,0,1,?,?,1)""",
        (username, pw_hash, salt, nickname or username, email, phone, ts, ts),
    )
    add_points(uid, POINT_RULES["sign_in"], "注册奖励")
    log(uid, username, "register", "新用户注册")
    return uid


def register(username: str, password: str, email: str = "", phone: str = "") -> int:
    return _new_user(username, password, email=email, phone=phone)


def register_by_phone(phone: str, code: str, password: str, username: str = "") -> int:
    verify_code(phone, "sms", "register", code)
    uname = username.strip() or f"u{phone[-6:]}"
    if get_user_by_name(uname):
        uname = f"{uname}_{secrets.randbelow(9000) + 1000}"
    uid = _new_user(uname, password, phone=phone)
    db.execute("UPDATE users SET phone_verified=1 WHERE id=?", (uid,))
    return uid


def _is_locked(user) -> int:
    lu = (user or {}).get("locked_until") or ""
    if not lu:
        return 0
    try:
        until = datetime.strptime(lu, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0
    delta = (until - datetime.now()).total_seconds()
    return max(0, int(delta // 60) + (1 if delta % 60 else 0)) if delta > 0 else 0


def login(username: str, password: str) -> dict:
    """返回用户字典；失败抛 AuthError（含明确提示）。"""
    user = get_user_by_name((username or "").strip())
    if not user:
        raise AuthError("用户名不存在，请检查后重试")
    if user["status"] == "banned":
        raise AuthError("该账号已被封禁，如有疑问请联系管理员")
    if user["status"] == "cancelled":
        raise AuthError("该账号已注销")
    mins = _is_locked(user)
    if mins:
        raise AuthError(f"登录失败次数过多，账号已锁定，请 {mins} 分钟后再试")
    if not verify_password(password, user["password_hash"], user["salt"]):
        fails = int(user["fail_count"]) + 1
        if fails >= MAX_LOGIN_FAILS:
            until = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("UPDATE users SET fail_count=?, locked_until=? WHERE id=?", (fails, until, user["id"]))
            log(user["id"], user["username"], "login_lock", f"连续失败 {fails} 次，锁定 {LOCK_MINUTES} 分钟")
            raise AuthError(f"密码错误次数过多，账号已锁定 {LOCK_MINUTES} 分钟")
        db.execute("UPDATE users SET fail_count=? WHERE id=?", (fails, user["id"]))
        log(user["id"], user["username"], "login_fail", f"第 {fails} 次密码错误")
        raise AuthError(f"密码错误，还可尝试 {MAX_LOGIN_FAILS - fails} 次")
    db.execute(
        "UPDATE users SET fail_count=0, locked_until='', online=1, last_active_at=? WHERE id=?",
        (db.now_str(), user["id"]),
    )
    log(user["id"], user["username"], "login", "登录成功")
    return get_user(user["id"])


def login_by_phone(phone: str, code: str) -> dict:
    verify_code(phone, "sms", "login", code)
    user = db.query_one("SELECT * FROM users WHERE phone=?", (phone,))
    if not user:
        raise AuthError("该手机号尚未注册，请先注册")
    if user["status"] == "banned":
        raise AuthError("该账号已被封禁")
    db.execute(
        "UPDATE users SET phone_verified=1, online=1, last_active_at=? WHERE id=?",
        (db.now_str(), user["id"]),
    )
    log(user["id"], user["username"], "login_sms", "验证码登录")
    return get_user(user["id"])


def logout(uid: int) -> None:
    db.execute("UPDATE users SET online=0, last_active_at=? WHERE id=?", (db.now_str(), uid))


def change_password(uid: int, old: str, new: str) -> None:
    user = get_user(uid)
    if not user:
        raise AuthError("用户不存在")
    if not verify_password(old, user["password_hash"], user["salt"]):
        raise AuthError("原密码错误")
    ok, msg = validate_password(new)
    if not ok:
        raise AuthError(msg)
    pw_hash, salt = hash_password(new)
    db.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (pw_hash, salt, uid))
    log(uid, user["username"], "change_password", "修改密码")


def reset_password_by_email(email: str, code: str, new: str) -> None:
    if not EMAIL_RE.match(email or ""):
        raise AuthError("邮箱格式不正确")
    verify_code(email, "email", "reset", code)
    user = db.query_one("SELECT * FROM users WHERE email=?", (email,))
    if not user:
        raise AuthError("该邮箱未绑定任何账号")
    ok, msg = validate_password(new)
    if not ok:
        raise AuthError(msg)
    pw_hash, salt = hash_password(new)
    db.execute(
        "UPDATE users SET password_hash=?, salt=?, fail_count=0, locked_until='' WHERE id=?",
        (pw_hash, salt, user["id"]),
    )
    log(user["id"], user["username"], "reset_password", "邮箱重置密码")


def cancel_account(uid: int, strategy: str = "anonymize") -> None:
    """账号注销。strategy: anonymize(发言匿名化) / delete(删除发言)。"""
    user = get_user(uid)
    if not user:
        raise AuthError("用户不存在")
    if strategy == "delete":
        db.execute("DELETE FROM posts WHERE user_id=?", (uid,))
        db.execute("DELETE FROM comments WHERE user_id=?", (uid,))
    else:
        db.execute("UPDATE posts SET user_id=0 WHERE user_id=?", (uid,))
        db.execute("UPDATE comments SET user_id=0 WHERE user_id=?", (uid,))
    db.execute(
        "UPDATE users SET status='cancelled', online=0, email='', phone='', bio='' WHERE id=?",
        (uid,),
    )
    log(uid, user["username"], "cancel_account", f"注销策略: {strategy}")


# --------------------------------------------------------------------------
# 验证码（短信 / 邮箱）
# --------------------------------------------------------------------------
def send_code(target: str, channel: str = "sms", purpose: str = "login") -> str:
    """生成并"发送"6 位验证码。演示模式：直接返回验证码，由 UI 提示用户。

    真实接入时把本函数替换为短信/邮件服务商 SDK 调用即可（接口已预留）。
    """
    if channel == "sms" and not PHONE_RE.match(target or ""):
        raise AuthError("手机号格式不正确")
    if channel == "email" and not EMAIL_RE.match(target or ""):
        raise AuthError("邮箱格式不正确")

    # 60 秒内不可重复发送
    last = db.query_one(
        "SELECT * FROM verifications WHERE target=? AND channel=? AND purpose=? "
        "ORDER BY id DESC LIMIT 1",
        (target, channel, purpose),
    )
    if last:
        try:
            c_at = datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")
            wait = CODE_TTL_SECONDS - int((datetime.now() - c_at).total_seconds())
            if wait > 0 and not last["used"]:
                raise AuthError(f"验证码已发送，请 {wait} 秒后再试")
        except ValueError:
            pass

    code = f"{secrets.randbelow(1_000_000):06d}"
    exp = (datetime.now() + timedelta(seconds=CODE_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO verifications(target,channel,code,purpose,expires_at,created_at) VALUES(?,?,?,?,?,?)",
        (target, channel, code, purpose, exp, db.now_str()),
    )
    db.execute("DELETE FROM verifications WHERE expires_at < ?", (db.days_ago_str(1),))
    log(0, target, "send_code", f"{channel}/{purpose} 下发验证码")
    return code


def verify_code(target: str, channel: str, purpose: str, code: str) -> None:
    """校验验证码：超时 / 错误次数过多 / 已使用 均给出明确提示。"""
    code = (code or "").strip()
    if not code:
        raise AuthError("请输入验证码")
    row = db.query_one(
        "SELECT * FROM verifications WHERE target=? AND channel=? AND purpose=? "
        "ORDER BY id DESC LIMIT 1",
        (target, channel, purpose),
    )
    if not row:
        raise AuthError("请先获取验证码")
    if row["used"]:
        raise AuthError("该验证码已使用，请重新获取")
    if row["tries"] >= CODE_MAX_TRIES:
        raise AuthError(f"验证码错误次数过多，已失效，请 {LOCK_MINUTES} 分钟后重新获取")
    try:
        expired = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now()
    except ValueError:
        expired = True
    if expired:
        raise AuthError(f"验证码已过期（有效期 {CODE_TTL_SECONDS} 秒），请重新获取")
    if code != row["code"]:
        db.execute("UPDATE verifications SET tries=tries+1 WHERE id=?", (row["id"],))
        left = CODE_MAX_TRIES - (row["tries"] + 1)
        if left <= 0:
            raise AuthError("验证码错误次数过多，已失效，请重新获取")
        raise AuthError(f"验证码错误，还可尝试 {left} 次")
    db.execute("UPDATE verifications SET used=1 WHERE id=?", (row["id"],))


def bind_email(uid: int, email: str, code: str) -> None:
    if not EMAIL_RE.match(email or ""):
        raise AuthError("邮箱格式不正确")
    verify_code(email, "email", "bind", code)
    db.execute("UPDATE users SET email=?, email_verified=1 WHERE id=?", (email, uid))
    log(uid, "", "bind_email", f"绑定邮箱 {email}")


def bind_phone(uid: int, phone: str, code: str) -> None:
    verify_code(phone, "sms", "bind", code)
    db.execute("UPDATE users SET phone=?, phone_verified=1 WHERE id=?", (phone, uid))
    log(uid, "", "bind_phone", f"绑定手机 {phone}")


# --------------------------------------------------------------------------
# 实名认证
# --------------------------------------------------------------------------
def is_realname_ok(uid: int) -> bool:
    u = get_user(uid)
    return bool(u and u["realname_status"] == "approved")


def submit_realname(uid: int, real_name: str, id_card: str, phone: str) -> None:
    real_name = (real_name or "").strip()
    id_card = (id_card or "").strip().upper()
    if len(real_name) < 2:
        raise AuthError("请输入真实姓名（至少 2 个字）")
    if not IDCARD_RE.match(id_card):
        raise AuthError("身份证号格式不正确（应为 18 位）")
    if not PHONE_RE.match(phone or ""):
        raise AuthError("手机号格式不正确")
    db.execute(
        "UPDATE users SET real_name=?, id_card=?, phone=?, realname_status='pending' WHERE id=?",
        (real_name, mask_id(id_card), phone, uid),
    )
    log(uid, "", "realname_submit", "提交实名认证")


def mask_id(id_card: str) -> str:
    """身份证脱敏存储：仅保留前 6 位与后 4 位。"""
    if not id_card or len(id_card) < 10:
        return id_card or ""
    return id_card[:6] + "*" * (len(id_card) - 10) + id_card[-4:]


def review_realname(uid: int, approve: bool) -> None:
    db.execute(
        "UPDATE users SET realname_status=? WHERE id=?",
        ("approved" if approve else "rejected", uid),
    )
    log(uid, "", "realname_review", "实名审核通过" if approve else "实名审核驳回")


# --------------------------------------------------------------------------
# 积分 / 日志
# --------------------------------------------------------------------------
def add_points(uid: int, delta: int, reason: str) -> int:
    if not uid or delta == 0:
        return 0
    db.execute("INSERT INTO points_log(user_id,delta,reason,created_at) VALUES(?,?,?,?)",
               (uid, delta, reason, db.now_str()))
    db.execute("UPDATE users SET points = points + ? WHERE id=?", (delta, uid))
    pts = int(db.scalar("SELECT points FROM users WHERE id=?", (uid,), 0))
    db.execute("UPDATE users SET level=? WHERE id=?", (level_of(pts), uid))
    return pts


def log(uid: int, username: str, action: str, detail: str = "") -> None:
    db.execute(
        "INSERT INTO access_logs(user_id,username,action,detail,created_at) VALUES(?,?,?,?,?)",
        (uid or 0, username or "", action, detail, db.now_str()),
    )


def heartbeat(uid: int) -> None:
    if uid:
        db.execute("UPDATE users SET online=1, last_active_at=? WHERE id=?", (db.now_str(), uid))


def presence_text(user) -> str:
    if not user:
        return "未知"
    if user.get("online"):
        return "在线"
    la = user.get("last_active_at") or ""
    if not la:
        return "离线"
    try:
        dt = datetime.strptime(la, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "离线"
    mins = int((datetime.now() - dt).total_seconds() // 60)
    if mins < 1:
        return "刚刚活跃"
    if mins < 60:
        return f"{mins} 分钟前活跃"
    if mins < 1440:
        return f"{mins // 60} 小时前活跃"
    return f"{mins // 1440} 天前活跃"


def mask_phone(phone: str) -> str:
    return phone[:3] + "****" + phone[-4:] if phone and len(phone) == 11 else (phone or "")
