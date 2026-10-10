"""网课售卖与线上交易：商品、购物车、优惠券、积分抵扣、下单、支付回调、退款、结算提现、风控。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from . import auth, courses, db, notify, users

# ---------------- 平台规则（均由平台设定，可后台调整） ----------------
POINT_VALUE = 0.01                      # 1 积分 = 0.01 元
POINT_MAX_RATIO = 0.2                   # 积分最多抵扣订单金额的 20%
COMMISSION_BY_LEVEL = {1: 0.30, 2: 0.25, 3: 0.20, 4: 0.18, 5: 0.15}
PAY_METHODS = {"wechat": "微信支付", "alipay": "支付宝", "card": "银行卡"}
REFUND_WATCH_LIMIT = 0.10               # 观看进度超过 10% 不可退款
ORDER_TIMEOUT_MIN = 30                  # 待支付订单超时关闭
SECRET_KEY = "bgl-demo-secret-key-2026"

PTYPES = {"course": "单课", "column": "专栏打包", "member": "会员订阅", "live_ticket": "直播单场票"}


# ============================ 商品 ============================
def sync_course_products() -> int:
    """把平台上架课程同步为可售商品。"""
    n = 0
    for c in courses.list_courses(status="on", limit=500):
        exist = db.query_one("SELECT id FROM products WHERE ptype='course' AND ref_id=?", (c["id"],))
        if exist:
            db.execute("UPDATE products SET title=?,price=?,original_price=?,cover=?,description=? WHERE id=?",
                       (c["title"], c["price"], c["original_price"], c["cover"], c["intro"], exist["id"]))
        else:
            db.execute(
                """INSERT INTO products(ptype,ref_id,title,cover,description,price,original_price,created_at)
                   VALUES('course',?,?,?,?,?,?,?)""",
                (c["id"], c["title"], c["cover"], c["intro"], c["price"], c["original_price"], db.now_str()))
            n += 1
    return n


def list_products(ptype: str = "", keyword: str = "", only_active: bool = True, limit: int = 200) -> list:
    sql = "SELECT * FROM products WHERE 1=1"
    params: list = []
    if only_active:
        sql += " AND active=1"
    if ptype:
        sql += " AND ptype=?"; params.append(ptype)
    if keyword:
        sql += " AND (title LIKE ? OR description LIKE ?)"; params += [f"%{keyword}%"] * 2
    sql += " ORDER BY id DESC LIMIT ?"; params.append(limit)
    return db.query(sql, tuple(params))


def get_product(pid: int):
    return db.query_one("SELECT * FROM products WHERE id=?", (pid,))


# ============================ 购物车 ============================
def add_to_cart(uid: int, product_id: int, qty: int = 1) -> None:
    if not uid:
        raise auth.AuthError("请先登录")
    if not get_product(product_id):
        raise auth.AuthError("商品不存在")
    if is_purchased(uid, product_id):
        raise auth.AuthError("你已拥有该课程，无需重复购买")
    db.execute(
        "INSERT INTO cart(user_id,product_id,qty,created_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,product_id) DO UPDATE SET qty=cart.qty+excluded.qty",
        (uid, product_id, max(1, int(qty)), db.now_str()),
    )


def remove_from_cart(uid: int, product_id: int) -> None:
    db.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (uid, product_id))


def clear_cart(uid: int) -> None:
    db.execute("DELETE FROM cart WHERE user_id=?", (uid,))


def list_cart(uid: int) -> list:
    return db.query(
        """SELECT ct.*, p.title, p.price, p.original_price, p.ptype, p.ref_id, p.cover
           FROM cart ct JOIN products p ON p.id=ct.product_id
           WHERE ct.user_id=? ORDER BY ct.id DESC""", (uid,))


def cart_total(uid: int) -> float:
    return round(sum(float(r["price"]) * int(r["qty"]) for r in list_cart(uid)), 2)


def is_purchased(uid: int, product_id: int) -> bool:
    p = get_product(product_id)
    if not p:
        return False
    if p["ptype"] == "course" and p["ref_id"]:
        return courses.is_enrolled(uid, p["ref_id"])
    row = db.query_one(
        """SELECT 1 FROM order_items oi JOIN orders o ON o.id=oi.order_id
           WHERE o.user_id=? AND oi.product_id=? AND o.status='paid'""", (uid, product_id))
    return row is not None


# ============================ 优惠券 ============================
def create_coupon(code: str, ctype: str, value: float, min_amount: float = 0,
                  days_valid: int = 30, max_uses: int = 100) -> int:
    if ctype not in ("full_reduce", "discount", "newcomer"):
        raise auth.AuthError("不支持的优惠券类型")
    exp = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d %H:%M:%S")
    return db.execute(
        "INSERT OR REPLACE INTO coupons(code,ctype,value,min_amount,expires_at,max_uses,used_count) "
        "VALUES(?,?,?,?,?,?,COALESCE((SELECT used_count FROM coupons WHERE code=?),0))",
        (code.upper(), ctype, float(value), float(min_amount), exp, int(max_uses), code.upper()))


def list_coupons() -> list:
    return db.query("SELECT * FROM coupons ORDER BY id DESC")


def grant_coupon(uid: int, coupon_id: int) -> None:
    db.execute("INSERT OR IGNORE INTO user_coupons(user_id,coupon_id,used,created_at) VALUES(?,?,0,?)",
               (uid, coupon_id, db.now_str()))


def my_coupons(uid: int, usable_only: bool = False) -> list:
    rows = db.query(
        """SELECT c.*, uc.used FROM user_coupons uc JOIN coupons c ON c.id=uc.coupon_id
           WHERE uc.user_id=? ORDER BY c.id DESC""", (uid,))
    if not usable_only:
        return rows
    out = []
    for c in rows:
        if c["used"]:
            continue
        try:
            if datetime.strptime(c["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
                continue
        except ValueError:
            continue
        out.append(c)
    return out


def coupon_discount(coupon: dict, amount: float) -> float:
    """计算优惠金额。"""
    if not coupon or amount <= 0:
        return 0.0
    if amount < float(coupon["min_amount"] or 0):
        return 0.0
    if coupon["ctype"] == "discount":
        return round(amount * (1 - float(coupon["value"])), 2)
    return min(round(float(coupon["value"]), 2), amount)


def validate_coupon(uid: int, code: str, amount: float) -> tuple[dict | None, float, str]:
    """返回 (coupon, discount, message)。"""
    if not code:
        return None, 0.0, ""
    row = db.query_one("SELECT * FROM coupons WHERE code=?", (code.strip().upper(),))
    if not row:
        return None, 0.0, "优惠券不存在"
    try:
        if datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            return None, 0.0, "优惠券已过期"
    except ValueError:
        pass
    if row["used_count"] >= row["max_uses"]:
        return None, 0.0, "优惠券已被领完"
    if amount < float(row["min_amount"] or 0):
        return None, 0.0, f"订单金额未满 {row['min_amount']:.0f} 元，无法使用"
    d = coupon_discount(row, amount)
    if d <= 0:
        return None, 0.0, "该优惠券不适用于本订单"
    return row, d, ""


# ============================ 积分抵扣 ============================
def points_discount(points: int, amount_after_coupon: float) -> float:
    points = max(0, int(points or 0))
    cap = amount_after_coupon * POINT_MAX_RATIO
    return round(min(points * POINT_VALUE, cap, amount_after_coupon), 2)


def max_usable_points(uid: int, amount_after_coupon: float) -> int:
    u = auth.get_user(uid) or {}
    owned = int(u.get("points") or 0)
    cap_points = int((amount_after_coupon * POINT_MAX_RATIO) / POINT_VALUE) if POINT_VALUE else 0
    return max(0, min(owned, cap_points))


# ============================ 订单 ============================
def _order_no() -> str:
    return "BGL" + datetime.now().strftime("%Y%m%d%H%M%S") + f"{secrets.randbelow(9000) + 1000}"


def sign_payload(payload: dict) -> str:
    """敏感接口签名（需求书 7.8）。"""
    msg = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]


def risk_check(uid: int, amount: float) -> str:
    """风控：近 10 分钟下单过于频繁 → 标记待审核。"""
    since = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    cnt = int(db.scalar("SELECT COUNT(*) FROM orders WHERE user_id=? AND created_at>=?", (uid, since), 0))
    flags = []
    if cnt >= 5:
        flags.append("高频下单")
    if amount >= 5000:
        flags.append("大额订单")
    return ",".join(flags)


def create_order(uid: int, product_ids: list[int], coupon_code: str = "",
                 use_points: int = 0, pay_method: str = "", is_flashsale: bool = False,
                 group_buy: bool = False) -> str:
    if not uid:
        raise auth.AuthError("请先登录")
    items = []
    for pid in product_ids:
        p = get_product(pid)
        if not p:
            raise auth.AuthError(f"商品 #{pid} 不存在")
        items.append(p)
    if not items:
        raise auth.AuthError("请先选择要购买的商品")

    amount = round(sum(float(p["price"]) for p in items), 2)
    coupon, discount, _msg = validate_coupon(uid, coupon_code, amount)
    after_coupon = round(max(amount - discount, 0), 2)
    max_pts = max_usable_points(uid, after_coupon)
    pts = max(0, min(int(use_points or 0), max_pts))
    pts_discount = points_discount(pts, after_coupon)
    final = round(max(after_coupon - pts_discount, 0), 2)

    risk = risk_check(uid, final)
    order_no = _order_no()
    oid = db.execute(
        """INSERT INTO orders(order_no,user_id,amount,discount,points_used,final_amount,status,
                              pay_method,coupon_id,is_flashsale,group_buy,risk_flag,created_at)
           VALUES(?,?,?,?,?,?,'pending',?,?,?,?,?,?)""",
        (order_no, uid, amount, round(discount + pts_discount, 2), pts, final,
         pay_method if pay_method in PAY_METHODS else "", (coupon or {}).get("id", 0),
         1 if is_flashsale else 0, 1 if group_buy else 0, risk, db.now_str()),
    )
    for p in items:
        db.execute("INSERT INTO order_items(order_id,product_id,title,price,qty) VALUES(?,?,?,?,1)",
                   (oid, p["id"], p["title"], p["price"]))
        db.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (uid, p["id"]))
    if pts:
        auth.add_points(uid, -pts, f"订单 {order_no} 积分抵扣")
    if coupon:
        db.execute("UPDATE coupons SET used_count=used_count+1 WHERE id=?", (coupon["id"],))
        db.execute("UPDATE user_coupons SET used=1 WHERE user_id=? AND coupon_id=?", (uid, coupon["id"]))
    auth.log(uid, "", "order_create", f"{order_no} ¥{final} 风控={risk or '正常'}")
    try:
        from . import ratelimit
        ratelimit.hit(f"order:{uid}", limit=10, window=600)
    except Exception:
        pass
    return order_no


def get_order(order_no: str):
    return db.query_one("SELECT * FROM orders WHERE order_no=?", (order_no,))


def order_items(oid: int) -> list:
    return db.query("SELECT * FROM order_items WHERE order_id=?", (oid,))


def list_orders(uid: int, status: str = "") -> list:
    sql = "SELECT * FROM orders WHERE user_id=?"
    params: list = [uid]
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY id DESC"
    return db.query(sql, tuple(params))


def pay_order(order_no: str, pay_method: str = "wechat", signature: str = "") -> dict:
    """支付回调：模拟支付成功后自动开通课程权限并发送通知（需求书 5.2.2）。"""
    o = get_order(order_no)
    if not o:
        raise auth.AuthError("订单不存在")
    if o["status"] == "paid":
        return {"ok": True, "msg": "订单已支付，请勿重复操作"}
    if o["status"] != "pending":
        raise auth.AuthError(f"当前订单状态为 {o['status']}，无法支付")
    if pay_method not in PAY_METHODS:
        raise auth.AuthError("不支持的支付方式")
    # 二次校验：敏感操作需要签名一致（演示模式下由前端页面自动生成）
    expect = sign_payload({"order_no": order_no, "amount": o["final_amount"], "method": pay_method})
    if signature and not hmac.compare_digest(signature, expect):
        raise auth.AuthError("支付签名校验失败，请重试")

    uid = o["user_id"]
    items = order_items(o["id"])
    for it in items:
        p = get_product(it["product_id"])
        if p and p["ptype"] == "course" and p["ref_id"]:
            courses.enroll(uid, p["ref_id"], order_id=o["id"], force=True)
        elif p and p["ptype"] == "live_ticket" and p["ref_id"]:
            from . import live as livemod
            try:
                livemod.reserve(p["ref_id"], uid)
            except Exception:
                pass
    db.execute("UPDATE orders SET status='paid', pay_method=?, paid_at=? WHERE id=?",
               (pay_method, db.now_str(), o["id"]))

    # 讲师收益 + 平台抽成
    for it in items:
        p = get_product(it["product_id"])
        if not p or p["ptype"] != "course" or not p["ref_id"]:
            continue
        c = courses.get_course(p["ref_id"])
        if not c:
            continue
        inst = auth.get_user(c["instructor_id"]) or {}
        rate = COMMISSION_BY_LEVEL.get(int(inst.get("instructor_level") or 1), 0.30)
        income = round(float(it["price"]) * (1 - rate), 2)
        commission = round(float(it["price"]) * rate, 2)
        db.execute("INSERT INTO transactions(user_id,ttype,amount,order_id,note,created_at) "
                   "VALUES(?,'income',?,?,?,?)", (c["instructor_id"], income, o["id"],
                                                 f"课程《{c['title']}》收益", db.now_str()))
        db.execute("INSERT INTO transactions(user_id,ttype,amount,order_id,note,created_at) "
                   "VALUES(0,'commission',?,?,?,?)", (commission, o["id"], "平台佣金", db.now_str()))
    db.execute("INSERT INTO transactions(user_id,ttype,amount,order_id,note,created_at) "
               "VALUES(?,'purchase',?,?,?,?)", (uid, -float(o["final_amount"]), o["id"],
                                               "订单支付", db.now_str()))
    notify.push(uid, "order", f"订单 {order_no} 支付成功，已为你开通相应课程。", link="my")
    auth.add_points(uid, auth.POINT_RULES["buy_course"], "支付订单")
    auth.log(uid, "", "pay", f"{order_no} ¥{o['final_amount']} via {pay_method}")
    return {"ok": True, "msg": "支付成功，课程已开通"}


def close_order(order_no: str) -> None:
    db.execute("UPDATE orders SET status='closed' WHERE order_no=? AND status='pending'", (order_no,))


def close_expired_orders() -> int:
    cutoff = (datetime.now() - timedelta(minutes=ORDER_TIMEOUT_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    with db.tx() as conn:
        cur = conn.execute("UPDATE orders SET status='closed' WHERE status='pending' AND created_at < ?",
                           (cutoff,))
        return cur.rowcount


# ============================ 退款 ============================
def refundable(order: dict) -> tuple[bool, str]:
    if order["status"] != "paid":
        return False, "仅已支付订单可申请退款"
    items = order_items(order["id"])
    for it in items:
        p = get_product(it["product_id"])
        if p and p["ptype"] == "course" and p["ref_id"]:
            e = courses.get_enrollment(order["user_id"], p["ref_id"])
            if e and float(e["progress"]) > REFUND_WATCH_LIMIT * 100:
                return False, f"《{p['title']}》学习进度已超过 {int(REFUND_WATCH_LIMIT*100)}%，不符合退款规则"
    exist = db.query_one("SELECT 1 FROM refunds WHERE order_id=? AND status='pending'", (order["id"],))
    if exist:
        return False, "该订单已有待处理的退款申请"
    return True, ""


def apply_refund(uid: int, order_no: str, reason: str) -> int:
    o = get_order(order_no)
    if not o or o["user_id"] != uid:
        raise auth.AuthError("订单不存在")
    ok, msg = refundable(o)
    if not ok:
        raise auth.AuthError(msg)
    if not (reason or "").strip():
        raise auth.AuthError("请填写退款原因")
    rid = db.execute(
        "INSERT INTO refunds(order_id,user_id,reason,amount,status,created_at) VALUES(?,?,?,?,'pending',?)",
        (o["id"], uid, reason.strip(), o["final_amount"], db.now_str()))
    auth.log(uid, "", "refund_apply", f"{order_no}: {reason[:30]}")
    return rid


def list_refunds(status: str = "") -> list:
    sql = """SELECT r.*, o.order_no, o.final_amount, u.username FROM refunds r
             LEFT JOIN orders o ON o.id=r.order_id LEFT JOIN users u ON u.id=r.user_id"""
    params: list = []
    if status:
        sql += " WHERE r.status=?"; params.append(status)
    sql += " ORDER BY r.id DESC"
    return db.query(sql, tuple(params))


def review_refund(rid: int, approve: bool, by: int = 0) -> None:
    r = db.query_one("SELECT * FROM refunds WHERE id=?", (rid,))
    if not r:
        raise auth.AuthError("退款申请不存在")
    if r["status"] != "pending":
        raise auth.AuthError("该申请已处理")
    if approve:
        o = db.query_one("SELECT * FROM orders WHERE id=?", (r["order_id"],))
        db.execute("UPDATE refunds SET status='approved', handled_at=? WHERE id=?", (db.now_str(), rid))
        if o:
            db.execute("UPDATE orders SET status='refunded' WHERE id=?", (o["id"],))
            # 撤销课程权限
            for it in order_items(o["id"]):
                p = get_product(it["product_id"])
                if p and p["ptype"] == "course" and p["ref_id"]:
                    db.execute("DELETE FROM enrollments WHERE user_id=? AND course_id=?",
                               (o["user_id"], p["ref_id"]))
                    db.execute("UPDATE courses SET sales=MAX(sales-1,0) WHERE id=?", (p["ref_id"],))
            # 冲销讲师收益与平台佣金
            for t in db.query("SELECT * FROM transactions WHERE order_id=? AND ttype IN ('income','commission')",
                              (o["id"],)):
                db.execute("INSERT INTO transactions(user_id,ttype,amount,order_id,note,created_at) "
                           "VALUES(?,'refund',?,?,?,?)", (t["user_id"], -float(t["amount"]), o["id"],
                                                        "退款冲销", db.now_str()))
            db.execute("INSERT INTO transactions(user_id,ttype,amount,order_id,note,created_at) "
                       "VALUES(?,'refund',?,?,?,?)", (o["user_id"], float(r["amount"]), o["id"],
                                                     "退款到账（原路退回）", db.now_str()))
            notify.push(o["user_id"], "order",
                        f"订单 {o['order_no']} 退款已通过，¥{r['amount']:.2f} 将原路退回。", link="my")
        auth.log(by, "", "refund_approve", f"退款 #{rid}")
    else:
        db.execute("UPDATE refunds SET status='rejected', handled_at=? WHERE id=?", (db.now_str(), rid))
        notify.push(r["user_id"], "order", "你的退款申请未通过审核，如有疑问请联系客服。", link="my")
        auth.log(by, "", "refund_reject", f"退款 #{rid}")


# ============================ 发票 ============================
def apply_invoice(uid: int, order_no: str, title: str, tax_no: str = "", email: str = "") -> int:
    o = get_order(order_no)
    if not o or o["user_id"] != uid:
        raise auth.AuthError("订单不存在")
    if o["status"] != "paid":
        raise auth.AuthError("仅已支付订单可申请发票")
    return db.execute(
        "INSERT INTO invoices(order_id,user_id,title,tax_no,email,status,created_at) "
        "VALUES(?,?,?,?,?,'pending',?)", (o["id"], uid, title, tax_no, email, db.now_str()))


def list_invoices(uid: int = 0) -> list:
    if uid:
        return db.query("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC", (uid,))
    return db.query("SELECT * FROM invoices ORDER BY id DESC")


# ============================ 收益 / 提现 / 对账 ============================
def instructor_balance(instructor_id: int) -> dict:
    income = float(db.scalar("SELECT COALESCE(SUM(amount),0) FROM transactions "
                             "WHERE user_id=? AND ttype='income'", (instructor_id,), 0.0))
    refunded = float(db.scalar("SELECT COALESCE(SUM(amount),0) FROM transactions "
                               "WHERE user_id=? AND ttype='refund'", (instructor_id,), 0.0))
    withdrawn = float(db.scalar("SELECT COALESCE(SUM(amount),0) FROM withdrawals "
                                "WHERE user_id=? AND status IN ('pending','paid')", (instructor_id,), 0.0))
    return {"income": round(income, 2), "refunded": round(refunded, 2),
            "withdrawn": round(withdrawn, 2), "available": round(income + refunded - withdrawn, 2)}


def revenue_report(instructor_id: int, period: str = "day") -> list:
    """日/周/月收益报表。"""
    fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}.get(period, "%Y-%m-%d")
    rows = db.query(
        "SELECT strftime(?, created_at) AS bucket, SUM(amount) AS total, COUNT(*) AS n "
        "FROM transactions WHERE user_id=? AND ttype='income' GROUP BY bucket ORDER BY bucket DESC LIMIT 60",
        (fmt, instructor_id))
    return [{"period": r["bucket"], "total": round(float(r["total"] or 0), 2), "orders": r["n"]} for r in rows]


def income_detail(instructor_id: int, limit: int = 100) -> list:
    return db.query(
        """SELECT t.*, o.order_no, oi.title FROM transactions t
           LEFT JOIN orders o ON o.id=t.order_id
           LEFT JOIN order_items oi ON oi.order_id=t.order_id
           WHERE t.user_id=? AND t.ttype='income' ORDER BY t.id DESC LIMIT ?""",
        (instructor_id, limit))


def apply_withdraw(uid: int, amount: float, account: str) -> int:
    if not auth.is_realname_ok(uid):
        raise auth.AuthError("提现需要先完成实名认证")
    bal = instructor_balance(uid)
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise auth.AuthError("提现金额必须大于 0")
    if amount > bal["available"]:
        raise auth.AuthError(f"可提现余额不足（当前可提现 ¥{bal['available']:.2f}）")
    if not (account or "").strip():
        raise auth.AuthError("请填写收款账户")
    wid = db.execute("INSERT INTO withdrawals(user_id,amount,account,status,created_at) "
                     "VALUES(?,?,?,'pending',?)", (uid, amount, account.strip(), db.now_str()))
    auth.log(uid, "", "withdraw_apply", f"¥{amount}")
    return wid


def list_withdrawals(status: str = "") -> list:
    sql = "SELECT w.*, u.username FROM withdrawals w LEFT JOIN users u ON u.id=w.user_id"
    params: list = []
    if status:
        sql += " WHERE w.status=?"; params.append(status)
    sql += " ORDER BY w.id DESC"
    return db.query(sql, tuple(params))


def review_withdraw(wid: int, approve: bool, by: int = 0) -> None:
    w = db.query_one("SELECT * FROM withdrawals WHERE id=?", (wid,))
    if not w or w["status"] != "pending":
        raise auth.AuthError("提现申请不存在或已处理")
    db.execute("UPDATE withdrawals SET status=?, handled_at=? WHERE id=?",
               ("paid" if approve else "rejected", db.now_str(), wid))
    if approve:
        db.execute("INSERT INTO transactions(user_id,ttype,amount,note,created_at) "
                   "VALUES(?,'withdraw',?,?,?)", (w["user_id"], -float(w["amount"]), "提现打款", db.now_str()))
        notify.push(w["user_id"], "order", f"提现 ¥{w['amount']:.2f} 已打款至 {w['account']}。", link="instructor")
    else:
        notify.push(w["user_id"], "order", "你的提现申请未通过审核。", link="instructor")
    auth.log(by, "", "withdraw_review", f"#{wid} {'通过' if approve else '驳回'}")


def platform_summary() -> dict:
    return {
        "gmv": round(float(db.scalar("SELECT COALESCE(SUM(final_amount),0) FROM orders WHERE status='paid'", (), 0.0)), 2),
        "commission": round(float(db.scalar("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE ttype='commission'", (), 0.0)), 2),
        "refunded": round(float(db.scalar("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE status='approved'", (), 0.0)), 2),
        "paid_orders": int(db.scalar("SELECT COUNT(*) FROM orders WHERE status='paid'", (), 0)),
        "pending_orders": int(db.scalar("SELECT COUNT(*) FROM orders WHERE status='pending'", (), 0)),
        "pending_refunds": int(db.scalar("SELECT COUNT(*) FROM refunds WHERE status='pending'", (), 0)),
        "pending_withdraws": int(db.scalar("SELECT COUNT(*) FROM withdrawals WHERE status='pending'", (), 0)),
        "risk_orders": int(db.scalar("SELECT COUNT(*) FROM orders WHERE risk_flag<>''", (), 0)),
    }


def order_flow(limit: int = 200) -> list:
    return db.query("""SELECT o.*, u.username FROM orders o LEFT JOIN users u ON u.id=o.user_id
                       ORDER BY o.id DESC LIMIT ?""", (limit,))
